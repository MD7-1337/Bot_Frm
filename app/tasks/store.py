"""Versioned SQLite task definitions and durable dispatch decisions.

Source snapshots are immutable per task revision. No trust or connection secrets
are persisted. Unknown in-flight results after restart require human inspection.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from contextlib import nullcontext
from datetime import datetime, timedelta, timezone
import hashlib
from functools import cached_property
import json
import math
from pathlib import Path
import sqlite3
from uuid import uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

UTC = timezone.utc
ACTIVE = ('queued', 'dispatching', 'running', 'cancelling')
TERMINAL = ('completed', 'failed', 'cancelled', 'uncertain', 'missed')


def stamp(value: datetime) -> float:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError('An aware datetime is required')
    return value.timestamp()


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Task:
    task_id: str
    name: str
    source: str
    serial: str
    project_root: str
    script_id: str = '<scheduled>'
    enabled: bool = True
    schedule: str = 'manual'
    timezone: str = 'UTC'
    at: str | None = None
    interval_seconds: int = 3600
    weekdays: tuple[int, ...] = (0,)
    priority: int = 0
    timeout_seconds: float = 300
    missed: str = 'skip'
    dependencies: tuple[str, ...] = ()
    max_retries: int = 0
    restart_safe: bool = False

    @cached_property
    def fingerprint(self) -> str:
        # Include every execution-affecting field, not only source text.
        fields = asdict(self)
        return hashlib.sha256(json.dumps(fields, ensure_ascii=True).encode()).hexdigest()

    def validate(self) -> 'Task':
        for key in ('task_id', 'name', 'serial', 'project_root', 'script_id', 'source'):
            value = getattr(self, key)
            if not isinstance(value, str) or not value or '\x00' in value:
                raise ValueError(f'{key} must be nonempty text without NUL')
        if len(self.task_id) > 128 or len(self.project_root) > 4096 or len(self.script_id) > 1024:
            raise ValueError('Task identity or path exceeds its supported size')
        if len(self.name) > 150 or len(self.serial) > 256 or self.serial.startswith('-') or any(c.isspace() for c in self.serial):
            raise ValueError('Invalid task name or device identity')
        if len(self.source.encode('utf-8')) > 1_000_000:
            raise ValueError('Task source exceeds 1 MB')
        if not Path(self.project_root).is_absolute():
            raise ValueError('Project root must be an absolute path')
        if self.schedule not in ('manual', 'once', 'interval', 'daily', 'weekly'):
            raise ValueError('Unsupported schedule')
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, TypeError):
            raise ValueError('Unknown IANA timezone') from None
        if type(self.enabled) is not bool or type(self.restart_safe) is not bool:
            raise ValueError('Enabled and restart safety must be booleans')
        if type(self.priority) is not int or not -100 <= self.priority <= 100:
            raise ValueError('Priority must be between -100 and 100')
        if type(self.interval_seconds) is not int or not 1 <= self.interval_seconds <= 31_536_000:
            raise ValueError('Interval must be between one second and one year')
        if isinstance(self.timeout_seconds, bool) or not isinstance(self.timeout_seconds, (float, int)) or not math.isfinite(self.timeout_seconds) or not 0 < self.timeout_seconds <= 86400:
            raise ValueError('Timeout must be finite, positive and at most one day')
        if self.missed not in ('skip', 'run_once'):
            raise ValueError('Missed-run behavior must be skip or run_once')
        if type(self.max_retries) is not int or not 0 <= self.max_retries <= 3 or (self.max_retries and not self.restart_safe):
            raise ValueError('At most three retries require explicit whole-script restart safety')
        if not isinstance(self.dependencies, (list, tuple)) or len(self.dependencies) > 100 or len(set(self.dependencies)) != len(self.dependencies):
            raise ValueError('Invalid dependencies')
        if self.task_id in self.dependencies or any(not isinstance(x, str) or not x or len(x)>128 for x in self.dependencies):
            raise ValueError('Invalid dependency identity')
        if not isinstance(self.weekdays, (tuple, list)) or not self.weekdays or any(type(x) is not int or x not in range(7) for x in self.weekdays):
            raise ValueError('Weekdays must be Monday=0 through Sunday=6')
        if self.schedule in ('daily', 'weekly'):
            try:
                parsed = datetime.strptime(self.at or '', '%H:%M')
            except (ValueError, TypeError):
                raise ValueError('Daily/weekly time must be HH:MM') from None
            if parsed.strftime('%H:%M') != self.at:
                raise ValueError('Daily/weekly time must be HH:MM')
        elif self.schedule == 'once':
            try:
                stamp(datetime.fromisoformat(self.at or ''))
            except (ValueError, TypeError):
                raise ValueError('One-time execution requires an ISO date with timezone offset') from None
        return self


def next_due(task: Task, after: datetime, *, inclusive: bool = False) -> float | None:
    """Find the next occurrence; one DST fold dispatch, nonexistent times skip.

    Interval cadence advances from its last durable decision, avoiding drift.
    """
    current = stamp(after)
    if task.schedule == 'manual':
        return None
    if task.schedule == 'once':
        value = stamp(datetime.fromisoformat(task.at))
        return value if value > current or inclusive and value == current else None
    if task.schedule == 'interval':
        return current + task.interval_seconds
    zone = ZoneInfo(task.timezone)
    local = after.astimezone(zone)
    hour, minute = map(int, task.at.split(':'))
    for days in range(9):
        date = local.date() + timedelta(days=days)
        if task.schedule == 'weekly' and date.weekday() not in task.weekdays:
            continue
        candidate = datetime(date.year, date.month, date.day, hour, minute, tzinfo=zone, fold=0)
        # ZoneInfo permits nonexistent wall times; explicitly reject them.
        roundtrip = candidate.astimezone(UTC).astimezone(zone)
        if roundtrip.replace(tzinfo=None) != candidate.replace(tzinfo=None):
            continue
        value = candidate.timestamp()
        if value > current or inclusive and value == current:
            return value
    raise ValueError('No schedule occurrence found')


class TaskStore:
    def __init__(self, path: str | Path):
        self.path = Path(path).expanduser().absolute()
        if self.path.is_symlink():
            raise ValueError('Task database must not overwrite a symbolic link')
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.path, timeout=2)
        self.db.row_factory = sqlite3.Row
        self._task_cache = None
        self._data_version = None
        self.db.execute('PRAGMA foreign_keys=ON')
        version = self.db.execute('PRAGMA user_version').fetchone()[0]
        if version not in (0, 1, 2):
            self.db.close()
            raise ValueError(f'Unsupported task database schema {version}; file preserved')
        try:
            if version == 1:
                # SQLite's backup API preserves a consistent pre-migration database.
                backup = self.path.with_name(self.path.name + '.v1-' + uuid4().hex + '.bak')
                with sqlite3.connect(backup) as saved:
                    self.db.backup(saved)
            with self.db:
                self.db.execute('BEGIN IMMEDIATE')
                self.db.execute('CREATE TABLE IF NOT EXISTS tasks (id TEXT PRIMARY KEY, definition TEXT NOT NULL, fingerprint TEXT NOT NULL, next_due REAL)')
                self.db.execute('CREATE TABLE IF NOT EXISTS executions (id TEXT PRIMARY KEY, task_id TEXT NOT NULL REFERENCES tasks(id), occurrence TEXT NOT NULL, source_hash TEXT NOT NULL, state TEXT NOT NULL, scheduled REAL NOT NULL, started REAL, finished REAL, request_id TEXT UNIQUE, run_id TEXT UNIQUE, message TEXT NOT NULL DEFAULT \'\', attempt INTEGER NOT NULL DEFAULT 0, UNIQUE(task_id, occurrence))')
                self.db.execute('CREATE TABLE IF NOT EXISTS device_groups (name TEXT PRIMARY KEY, members TEXT NOT NULL)')
                self.db.execute('CREATE TABLE IF NOT EXISTS workflows (id TEXT PRIMARY KEY, definition TEXT NOT NULL, next_due REAL)')
                self.db.execute("CREATE TABLE IF NOT EXISTS workflow_runs (id TEXT PRIMARY KEY, workflow_id TEXT NOT NULL REFERENCES workflows(id), occurrence TEXT NOT NULL, state TEXT NOT NULL, scheduled REAL NOT NULL, finished REAL, message TEXT NOT NULL DEFAULT '', UNIQUE(workflow_id,occurrence))")
                self.db.execute('CREATE TABLE IF NOT EXISTS workflow_steps (workflow_run TEXT NOT NULL REFERENCES workflow_runs(id), position INTEGER NOT NULL, task_id TEXT NOT NULL REFERENCES tasks(id), source_hash TEXT NOT NULL, execution_id TEXT REFERENCES executions(id), PRIMARY KEY(workflow_run,position))')
                self.db.execute('PRAGMA user_version=2')
                self.db.execute("UPDATE workflow_runs SET state='uncertain',finished=?,message='Application closed before confirmed workflow outcome; approve a new run after inspection' WHERE state='running'", (stamp(utcnow()),))
                self.db.execute("UPDATE workflow_runs SET state='cancelled',finished=?,message='Pending workflow cancelled after restart' WHERE state='queued'", (stamp(utcnow()),))
                self.db.execute("UPDATE executions SET state='uncertain', finished=?, message='Application stopped before a confirmed result; inspect device before restarting' WHERE state IN ('dispatching','running','cancelling')", (stamp(utcnow()),))
                self.db.execute("UPDATE executions SET state='cancelled', finished=?, message='Pending task cancelled after application restart; authorize a fresh run' WHERE state='queued'", (stamp(utcnow()),))
        except BaseException:
            self.db.close()
            raise

    def close(self):
        self.db.close()

    @staticmethod
    def _task(row):
        values = json.loads(row['definition'])
        values['dependencies'] = tuple(values.get('dependencies', ()))
        values['weekdays'] = tuple(values.get('weekdays', (0,)))
        return Task(**values).validate()

    def tasks(self) -> list[Task]:
        version = self.db.execute('PRAGMA data_version').fetchone()[0]
        if self._task_cache is None or self._data_version != version:
            tasks = [self._task(row) for row in self.db.execute('SELECT * FROM tasks ORDER BY id')]
            self._task_cache = {task.task_id:task for task in tasks}
            self._data_version = version
        return list(self._task_cache.values())

    def get(self, task_id: str) -> Task:
        self.tasks()
        return self._task_cache[task_id]

    def save(self, task: Task, *, now: datetime | None = None):
        task.validate()
        existing = {item.task_id: item for item in self.tasks()}
        if task.task_id not in existing and len(existing) >= 1000:
            raise ValueError('At most 1000 task definitions are supported')
        existing[task.task_id] = task
        visiting, visited = set(), set()
        def visit(identity):
            if identity in visiting:
                raise ValueError('Task dependency cycle')
            if identity in visited:
                return
            if identity not in existing:
                raise ValueError('Task dependency does not exist')
            visiting.add(identity)
            for dependency in existing[identity].dependencies:
                visit(dependency)
            visiting.remove(identity)
            visited.add(identity)
        visit(task.task_id)
        initial_due = stamp(datetime.fromisoformat(task.at)) if task.schedule == 'once' else next_due(task, now or utcnow(), inclusive=True)
        with self.db:
            if self.db.execute("SELECT 1 FROM executions WHERE task_id=? AND state IN ('dispatching','running','cancelling')", (task.task_id,)).fetchone():
                raise ValueError('Stop the active execution before editing this task')
            self.db.execute("UPDATE executions SET state='cancelled', finished=?, message='Task definition changed' WHERE task_id=? AND state='queued'", (stamp(now or utcnow()), task.task_id))
            self.db.execute('INSERT INTO tasks VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition, fingerprint=excluded.fingerprint, next_due=excluded.next_due',
                            (task.task_id, json.dumps(asdict(task), allow_nan=False), task.fingerprint, initial_due))
        self._task_cache = None

    def export_definitions(self, project_root):
        """Portable definitions only: no execution state or session approval."""
        root = Path(project_root).resolve()
        selected = [task for task in self.tasks() if Path(task.project_root).resolve() == root]
        selected_ids = {task.task_id for task in selected}
        output = []
        for task in selected:
            if any(identity not in selected_ids for identity in task.dependencies):
                raise ValueError('Project task depends on a task outside this project')
            fields = asdict(task)
            script = Path(task.script_id)
            if script.is_absolute():
                resolved = script.resolve()
                if not resolved.is_relative_to(root):
                    raise ValueError('Cannot export task whose script is outside this project')
                fields['script_id'] = resolved.relative_to(root).as_posix()
            elif task.script_id.startswith('<') and task.script_id.endswith('>'):
                fields['script_id'] = '<scheduled>'
            elif '..' in script.parts or '\\' in task.script_id or ':' in task.script_id:
                raise ValueError('Unsafe task script path')
            fields['project_root'] = '.'
            output.append(fields)
        return output

    def import_definitions(self, definitions, project_root, *, _within_transaction=False):
        """Import fresh disabled identities atomically; never grant approval."""
        if not isinstance(definitions, list) or len(definitions) > 1000:
            raise ValueError('Task definitions must be a list of at most 1000 entries')
        if len(self.tasks()) + len(definitions) > 1000:
            raise ValueError('Imported tasks exceed the 1000 task limit')
        root = Path(project_root).resolve()
        identities = {}
        for fields in definitions:
            if not isinstance(fields, dict) or not isinstance(fields.get('task_id'), str) or not fields['task_id'] or fields['task_id'] in identities:
                raise ValueError('Duplicate or invalid imported task identity')
            identities[fields['task_id']] = uuid4().hex
        tasks = []
        for original in definitions:
            fields = dict(original)
            if fields.get('project_root') != '.':
                raise ValueError('Imported task project path must be relative root')
            script_id = fields.get('script_id')
            if not isinstance(script_id,str):
                raise ValueError('Invalid imported script identity')
            if script_id != '<scheduled>':
                path = Path(script_id)
                if path.is_absolute() or '..' in path.parts or '\\' in script_id or ':' in script_id or not path.parts:
                    raise ValueError('Unsafe imported task script path')
                target = (root / path).resolve()
                if not target.is_relative_to(root):
                    raise ValueError('Imported script escapes project')
                fields['script_id'] = str(target)
            dependencies = fields.get('dependencies', [])
            if not isinstance(dependencies, (tuple,list)) or any(x not in identities for x in dependencies):
                raise ValueError('Imported dependency is missing from project')
            fields.update(task_id=identities[fields['task_id']], project_root=str(root),
                          enabled=False, dependencies=tuple(identities[x] for x in dependencies))
            fields['weekdays'] = tuple(fields.get('weekdays', (0,)))
            tasks.append(Task(**fields).validate())
        mapped = {task.task_id:task for task in tasks}
        visiting, visited = set(), set()
        def visit(identity):
            if identity in visiting:
                raise ValueError('Imported dependency cycle')
            if identity in visited:
                return
            visiting.add(identity)
            for dependency in mapped[identity].dependencies:
                visit(dependency)
            visiting.remove(identity)
            visited.add(identity)
        for identity in mapped:
            visit(identity)
        with (nullcontext() if _within_transaction else self.db):
            for task in tasks:
                # Disabled imports have no due trigger until explicitly enabled.
                self.db.execute('INSERT INTO tasks VALUES(?,?,?,NULL)',
                                (task.task_id,json.dumps(asdict(task),allow_nan=False),task.fingerprint))
        self._task_cache = None
        return tasks

    def delete(self, task_id):
        if any(task_id in workflow.task_ids for workflow in self.workflows()):
            raise ValueError('Remove the task from saved workflows first')
        if any(task_id in task.dependencies for task in self.tasks()):
            raise ValueError('Remove dependent tasks first')
        with self.db:
            if self.db.execute("SELECT 1 FROM executions WHERE task_id=? AND state IN ('dispatching','running','cancelling')", (task_id,)).fetchone():
                raise ValueError('Stop the active execution before deleting this task')
            self.db.execute('DELETE FROM executions WHERE task_id=?', (task_id,))
            self.db.execute('DELETE FROM tasks WHERE id=?', (task_id,))
        self._task_cache = None

    def history(self, task_id=None, *, limit=200):
        if type(limit) is not int or not 1 <= limit <= 1000:
            raise ValueError('History limit must be 1..1000')
        sql = 'SELECT * FROM executions'
        args = []
        if task_id is not None:
            sql += ' WHERE task_id=?'
            args.append(task_id)
        return [dict(row) for row in self.db.execute(sql + ' ORDER BY scheduled DESC, rowid DESC LIMIT ?', (*args, limit))]

    def active(self):
        return [dict(row) for row in self.db.execute(
            "SELECT * FROM executions WHERE state IN ('queued','dispatching','running','cancelling') ORDER BY scheduled,id")]

    def enqueue(self, task_id: str, *, now: datetime | None = None) -> str:
        task = self.get(task_id)
        if not task.enabled:
            raise ValueError('Enable the task before running it')
        if len(self.active()) >= 256:
            raise ValueError('Pending execution queue is full (256)')
        when = stamp(now or utcnow())
        identity = uuid4().hex
        with self.db:
            self.db.execute('INSERT INTO executions(id,task_id,occurrence,source_hash,state,scheduled) VALUES(?,?,?,?,?,?)', (identity, task_id, 'manual:'+identity, task.fingerprint, 'queued', when))
        return identity

    def materialize_due(self, now: datetime):
        when = stamp(now)
        with self.db:
            for row in self.db.execute('SELECT * FROM tasks WHERE next_due<=?', (when,)).fetchall():
                task = self._task(row)
                due = row['next_due']
                if not task.enabled:
                    continue
                # A five-second delivery window accommodates timer jitter. Larger
                # lateness follows the stored missed-run policy and coalesces.
                state = 'queued' if (when-due <= 5 or task.missed == 'run_once') and len(self.active()) < 256 else 'missed'
                self.db.execute('INSERT OR IGNORE INTO executions(id,task_id,occurrence,source_hash,state,scheduled,finished,message) VALUES(?,?,?,?,?,?,?,?)',
                                (uuid4().hex, task.task_id, f'schedule:{due:.6f}', task.fingerprint, state, due, when if state=='missed' else None, 'Missed execution skipped' if state=='missed' else ''))
                if task.schedule == 'interval':
                    following = due + (int((when-due)//task.interval_seconds)+1)*task.interval_seconds
                else:
                    following = next_due(task, now)
                self.db.execute('UPDATE tasks SET next_due=? WHERE id=?', (following, task.task_id))

    def transition(self, execution_id, state, *, allowed=ACTIVE, now=None, **fields):
        if state not in ACTIVE + TERMINAL:
            raise ValueError('Unknown execution state')
        if set(fields) - {'message','request_id','run_id','started','finished','scheduled','attempt'}:
            raise ValueError('Unknown execution field')
        row = self.db.execute('SELECT state FROM executions WHERE id=?', (execution_id,)).fetchone()
        if row is None or row['state'] not in allowed:
            return False
        transitions = {
            'queued': {'dispatching','cancelled'},
            'dispatching': {'dispatching','running','cancelling','failed','uncertain'},
            'running': {'completed','failed','cancelled','cancelling','uncertain'},
            'cancelling': {'cancelling','completed','failed','cancelled','uncertain'},
        }
        if state not in transitions.get(row['state'], set()):
            raise ValueError(f'Invalid execution transition {row["state"]} -> {state}')
        allowed = (row['state'],)
        if 'message' in fields:
            fields['message'] = str(fields['message'])[:4000]
        if state in TERMINAL:
            fields.setdefault('finished', stamp(now or utcnow()))
        fields['state'] = state
        placeholders = ','.join('?' for _ in allowed)
        query = 'UPDATE executions SET '+','.join(key+'=?' for key in fields)+f' WHERE id=? AND state IN ({placeholders})'
        with self.db:
            return bool(self.db.execute(query, (*fields.values(), execution_id, *allowed)).rowcount)

    def groups(self):
        return {row['name']: tuple(json.loads(row['members'])) for row in self.db.execute('SELECT * FROM device_groups ORDER BY name')}

    def save_group(self, name, members):
        from .workflows import device_members
        if not isinstance(name,str) or not name.strip() or len(name)>80 or '\x00' in name:
            raise ValueError('Group name needs 1..80 characters')
        members = device_members(members)
        with self.db:
            if name not in self.groups() and len(self.groups()) >= 100:
                raise ValueError('At most 100 device groups are supported')
            self.db.execute('INSERT INTO device_groups VALUES(?,?) ON CONFLICT(name) DO UPDATE SET members=excluded.members', (name.strip(),json.dumps(members)))

    def delete_group(self, name):
        with self.db:
            self.db.execute('DELETE FROM device_groups WHERE name=?',(name,))

    def expand_group(self, name, template: Task):
        """Save fresh explicit-serial tasks; never approve or dispatch them."""
        members = self.groups()[name]
        if len(self.tasks()) + len(members) > 1000:
            raise ValueError('Group expansion exceeds task limit')
        if template.dependencies:
            raise ValueError('Group copies require no dependencies; sequence copies in a workflow afterward')
        created = [replace(template, task_id=uuid4().hex, name=(template.name+' · '+serial)[:150], serial=serial).validate() for serial in members]
        with self.db:
            for task in created:
                due = stamp(datetime.fromisoformat(task.at)) if task.schedule == 'once' else next_due(task,utcnow(),inclusive=True)
                self.db.execute('INSERT INTO tasks VALUES(?,?,?,?)',(task.task_id,json.dumps(asdict(task),allow_nan=False),task.fingerprint,due))
        self._task_cache = None
        return created

    def workflows(self):
        from .workflows import Workflow
        result = []
        for row in self.db.execute('SELECT definition FROM workflows ORDER BY id'):
            fields = json.loads(row[0]); fields['task_ids'] = tuple(fields['task_ids']); fields['weekdays'] = tuple(fields.get('weekdays',(0,)))
            result.append(Workflow(**fields).validate())
        return result

    def workflow(self, identity):
        return next(item for item in self.workflows() if item.workflow_id==identity)

    def save_workflow(self, workflow, *, now=None):
        workflow.validate()
        tasks = {task.task_id:task for task in self.tasks()}
        prior = set()
        for identity in workflow.task_ids:
            task = tasks.get(identity)
            if task is None:
                raise ValueError('Workflow step task does not exist')
            if task.schedule != 'manual':
                raise ValueError('Workflow steps must use manual tasks; schedule the whole workflow instead')
            if not set(task.dependencies) <= prior:
                raise ValueError('Each workflow dependency must appear before its dependent task in this workflow')
            prior.add(identity)
        if workflow.workflow_id not in {item.workflow_id for item in self.workflows()} and len(self.workflows())>=100:
            raise ValueError('At most 100 workflows are supported')
        with self.db:
            if self.db.execute("SELECT 1 FROM workflow_runs WHERE workflow_id=? AND state IN ('queued','running')",(workflow.workflow_id,)).fetchone():
                raise ValueError('Cancel active workflow occurrences before editing')
            due = stamp(datetime.fromisoformat(workflow.at)) if workflow.schedule=='once' else next_due(workflow,now or utcnow(),inclusive=True)
            self.db.execute('INSERT INTO workflows VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET definition=excluded.definition,next_due=excluded.next_due',
                            (workflow.workflow_id,json.dumps(asdict(workflow),allow_nan=False),due))

    def delete_workflow(self, identity):
        with self.db:
            if self.db.execute("SELECT 1 FROM workflow_runs WHERE workflow_id=? AND state IN ('queued','running')",(identity,)).fetchone():
                raise ValueError('Cancel active workflow occurrences before deleting')
            self.db.execute('DELETE FROM workflow_steps WHERE workflow_run IN (SELECT id FROM workflow_runs WHERE workflow_id=?)',(identity,))
            self.db.execute('DELETE FROM workflow_runs WHERE workflow_id=?',(identity,))
            self.db.execute('DELETE FROM workflows WHERE id=?',(identity,))

    def _enqueue_workflow(self, workflow, when, occurrence):
        if not workflow.enabled:
            raise ValueError('Enable the workflow before running')
        if self.db.execute("SELECT count(*) FROM workflow_runs WHERE state IN ('queued','running')").fetchone()[0] >= 64:
            raise ValueError('Workflow queue is full (64)')
        identity = uuid4().hex
        self.db.execute('INSERT OR IGNORE INTO workflow_runs(id,workflow_id,occurrence,state,scheduled) VALUES(?,?,?,?,?)', (identity,workflow.workflow_id,occurrence,'queued',when))
        if self.db.execute('SELECT 1 FROM workflow_runs WHERE id=?',(identity,)).fetchone() is None:
            return None
        for position, task_id in enumerate(workflow.task_ids):
            task = self.get(task_id)
            self.db.execute('INSERT INTO workflow_steps VALUES(?,?,?,?,NULL)',(identity,position,task_id,task.fingerprint))
        return identity

    def enqueue_workflow(self, identity, *, now=None):
        workflow = self.workflow(identity)
        with self.db:
            return self._enqueue_workflow(workflow,stamp(now or utcnow()),'manual:'+uuid4().hex)

    def materialize_workflows(self, now):
        when=stamp(now)
        workflows={item.workflow_id:item for item in self.workflows()}
        with self.db:
            for row in self.db.execute('SELECT id,next_due FROM workflows WHERE next_due<=?',(when,)).fetchall():
                workflow=workflows[row['id']]; due=row['next_due']
                if not workflow.enabled:
                    continue
                if when-due <= 5 or workflow.missed=='run_once':
                    self._enqueue_workflow(workflow, due, f'schedule:{due:.6f}')
                else:
                    self.db.execute('INSERT OR IGNORE INTO workflow_runs(id,workflow_id,occurrence,state,scheduled,finished,message) VALUES(?,?,?,?,?,?,?)',
                                    (uuid4().hex,workflow.workflow_id,f'schedule:{due:.6f}','missed',due,when,'Missed workflow skipped'))
                following=due+(int((when-due)//workflow.interval_seconds)+1)*workflow.interval_seconds if workflow.schedule=='interval' else next_due(workflow,now)
                self.db.execute('UPDATE workflows SET next_due=? WHERE id=?',(following,workflow.workflow_id))

    def workflow_history(self, identity=None, *, active=False):
        query='SELECT * FROM workflow_runs'
        clauses=[];arguments=[]
        if identity is not None:
            clauses.append('workflow_id=?');arguments.append(identity)
        if active:
            clauses.append("state IN ('queued','running')")
        if clauses:query+=' WHERE '+' AND '.join(clauses)
        return [dict(row) for row in self.db.execute(query+' ORDER BY scheduled DESC,rowid DESC LIMIT 200',arguments)]

    def workflow_steps(self, run_id):
        return [dict(row) for row in self.db.execute('SELECT s.*, e.state AS execution_state FROM workflow_steps s LEFT JOIN executions e ON e.id=s.execution_id WHERE s.workflow_run=? ORDER BY s.position',(run_id,))]

    def workflow_step(self, execution_id):
        row=self.db.execute('SELECT * FROM workflow_steps WHERE execution_id=?',(execution_id,)).fetchone()
        return dict(row) if row else None

    def finish_workflow(self, run_id, state, message=''):
        if state not in ('running','completed','failed','cancelled','uncertain'):
            raise ValueError('Invalid workflow state')
        with self.db:
            return bool(self.db.execute("UPDATE workflow_runs SET state=?,finished=?,message=? WHERE id=? AND state IN ('queued','running')",
                    (state,None if state=='running' else stamp(utcnow()),message[:4000],run_id)).rowcount)

    def export_workflows(self, project_root):
        """Preserve sequence/schedule definitions, not occurrence state or approval."""
        root=Path(project_root).resolve()
        result=[]
        for workflow in self.workflows():
            roots=[Path(self.get(identity).project_root).resolve() for identity in workflow.task_ids]
            if root not in roots: continue
            if any(candidate!=root for candidate in roots):
                raise ValueError('Workflow crosses project boundaries; cannot export an incomplete workflow')
            result.append(asdict(workflow))
        return result

    def import_workflows(self, definitions, identity_map, *, _within_transaction=False):
        from .workflows import Workflow
        if not isinstance(definitions,list) or len(definitions)>100 or not isinstance(identity_map,dict):
            raise ValueError('Invalid portable workflow definitions')
        if len(self.workflows())+len(definitions)>100:
            raise ValueError('Workflow import exceeds limit')
        candidates=[];identities=set()
        for definition in definitions:
            if not isinstance(definition,dict) or not isinstance(definition.get('workflow_id'),str) or definition['workflow_id'] in identities:
                raise ValueError('Invalid or duplicate portable workflow identity')
            identities.add(definition['workflow_id'])
            fields=dict(definition)
            steps=fields.get('task_ids')
            if not isinstance(steps,(tuple,list)) or any(identity not in identity_map for identity in steps):
                raise ValueError('Portable workflow task is missing from imported definitions')
            fields.update(workflow_id=uuid4().hex,task_ids=tuple(identity_map[identity] for identity in steps),enabled=False)
            fields['weekdays']=tuple(fields.get('weekdays',(0,)))
            candidate=Workflow(**fields).validate()
            prior=set()
            for identity in candidate.task_ids:
                task=self.get(identity)
                if task.schedule!='manual' or not set(task.dependencies)<=prior:
                    raise ValueError('Invalid imported workflow step/dependency ordering')
                prior.add(identity)
            candidates.append(candidate)
        with (nullcontext() if _within_transaction else self.db):
            for workflow in candidates:
                self.db.execute('INSERT INTO workflows VALUES(?,?,NULL)',(workflow.workflow_id,json.dumps(asdict(workflow),allow_nan=False)))
        return candidates

    def import_project_definitions(self, tasks, workflows, project_root):
        """Import one project's task/sequence graph in a single transaction."""
        try:
            with self.db:
                imported=self.import_definitions(tasks,project_root,_within_transaction=True)
                mapping={original['task_id']:item.task_id for original,item in zip(tasks,imported)}
                sequences=self.import_workflows(workflows,mapping,_within_transaction=True)
                return imported,sequences
        finally:
            self._task_cache=None
