"""Nonblocking scheduler decisions over the existing isolated worker service.

``dispatch`` must validate the current device generation and submit to the real
RuntimeService, returning its request ID. It must never reconnect a device or
run source itself. This class owns no ADB transport and never calls allow_device.
All methods are called on the Qt/UI owner thread; IPC remains in RuntimeService.
"""
from __future__ import annotations

from datetime import datetime
from dataclasses import asdict
import hashlib
import json
import time
from uuid import uuid4

from .store import ACTIVE, Task, TaskStore, stamp, utcnow


class TaskScheduler:
    def __init__(self, store: TaskStore, dispatch, cancel, available, *, max_concurrency=4):
        if type(max_concurrency) is not int or not 1 <= max_concurrency <= 8:
            raise ValueError('Concurrency must be 1..8')
        self.store = store
        self.dispatch = dispatch
        self.cancel_run = cancel
        self.available = available
        self.max_concurrency = max_concurrency
        self.paused = True
        self.authorized = {}
        self.authorized_workflows = {}
        self.busy_serials = set()
        self._deadlines = {}
        self._errors = {}

    def authorize(self, task_id):
        """Host-only after displaying the exact source and target for approval."""
        self.authorized[task_id] = self.store.get(task_id).fingerprint

    def revoke(self, task_id):
        self.authorized.pop(task_id, None)
        for workflow in self.store.workflows():
            if task_id in workflow.task_ids:
                self.authorized_workflows.pop(workflow.workflow_id,None)

    def is_authorized(self, task):
        return self.authorized.get(task.task_id) == task.fingerprint

    def revoke_device(self, serial):
        """Disconnect invalidates queued work and session authorization."""
        for task in self.store.tasks():
            if task.serial == serial:
                self.revoke(task.task_id)
                self.cancel_task(task.task_id)

    def set_busy_serials(self, runs):
        for run in runs:
            if run.state in ('completed','failed','cancelled') and run.exitcode is not None:
                self.handle_event({'event':'status','run_id':run.run_id,'state':run.state})
        self.busy_serials = {run.serial for run in runs if run.state not in ('completed','failed','cancelled') or run.exitcode is None}

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def emergency_stop(self):
        self.pause()
        self.authorized.clear()
        self.authorized_workflows.clear()
        for run in self.store.workflow_history(active=True):
            self.cancel_workflow_run(run['id'])
        for execution in self.store.active():
            if execution['state'] == 'queued':
                self.store.transition(execution['id'], 'cancelled', allowed=('queued',), message='Emergency stop')
        # RuntimeService.emergency_stop remains the authority for active workers.

    def cancel_task(self, task_id):
        for run in self.store.workflow_history(active=True):
            if any(step['task_id']==task_id for step in self.store.workflow_steps(run['id'])):
                self.cancel_workflow_run(run['id'])
        for execution in self.store.active():
            if execution['task_id'] != task_id:
                continue
            if execution['state'] == 'queued':
                self.store.transition(execution['id'], 'cancelled', allowed=('queued',), message='Cancelled by user')
            elif execution['state'] in ('running', 'dispatching'):
                if execution['run_id']:
                    self.cancel_run(execution['run_id'])
                # A pending request has no run ID yet. Mark cancellation now;
                # handle_event will cancel it immediately once acknowledged.
                self.store.transition(execution['id'], 'cancelling', allowed=('running','dispatching'), message='Cancellation requested')

    def run_now(self, task_id, *, now=None):
        task = self.store.get(task_id)
        if not self.is_authorized(task):
            raise PermissionError('Approve this exact task source and device first')
        return self.store.enqueue(task_id, now=now)

    def workflow_fingerprint(self, workflow):
        fields=(asdict(workflow),[(identity,self.store.get(identity).fingerprint) for identity in workflow.task_ids])
        return hashlib.sha256(json.dumps(fields,sort_keys=True).encode()).hexdigest()

    def authorize_workflow(self, identity):
        workflow=self.store.workflow(identity)
        if not all(self.is_authorized(self.store.get(task_id)) for task_id in workflow.task_ids):
            raise PermissionError('Approve every workflow source/device first')
        self.authorized_workflows[identity]=self.workflow_fingerprint(workflow)

    def workflow_authorized(self, workflow):
        return (self.authorized_workflows.get(workflow.workflow_id)==self.workflow_fingerprint(workflow)
                and all(self.is_authorized(self.store.get(task_id)) for task_id in workflow.task_ids))

    def run_workflow(self, identity, *, now=None):
        workflow=self.store.workflow(identity)
        if not self.workflow_authorized(workflow):
            raise PermissionError('Approve this ordered workflow and every source/device first')
        return self.store.enqueue_workflow(identity,now=now)

    def cancel_workflow_run(self, run_id, *, state='cancelled', message='Cancelled by user; already-sent actions cannot be undone'):
        for step in self.store.workflow_steps(run_id):
            if step['execution_id'] is None:
                continue
            row=self.store.db.execute('SELECT * FROM executions WHERE id=?',(step['execution_id'],)).fetchone()
            if row['state']=='queued':
                self.store.transition(row['id'],'cancelled',allowed=('queued',),message='Workflow cancelled')
            elif row['state'] in ('dispatching','running'):
                if row['run_id']: self.cancel_run(row['run_id'])
                self.store.transition(row['id'],'cancelling',allowed=('dispatching','running'),message='Workflow cancellation requested')
        self.store.finish_workflow(run_id,state,message)

    def cancel_workflow(self, identity):
        for run in self.store.workflow_history(identity,active=True):
            self.cancel_workflow_run(run['id'])

    def _advance_workflows(self, now):
        for run in self.store.workflow_history(active=True):
            workflow=self.store.workflow(run['workflow_id'])
            steps=self.store.workflow_steps(run['id'])
            if any(self.store.get(step['task_id']).fingerprint != step['source_hash'] for step in steps):
                self.cancel_workflow_run(run['id'],state='failed',message='A task source/configuration changed; approve a fresh workflow')
                continue
            failed=next((step for step in steps if step['execution_state'] in ('failed','cancelled','uncertain','missed')),None)
            if failed:
                state=failed['execution_state']
                self.store.finish_workflow(run['id'],state if state in ('cancelled','uncertain') else 'failed','A workflow step did not complete successfully')
                continue
            if not self.workflow_authorized(workflow):
                continue
            for step in steps:
                state=step['execution_state']
                if state=='completed': continue
                if state in ('failed','cancelled','uncertain','missed'):
                    self.store.finish_workflow(run['id'],state if state in ('cancelled','uncertain') else 'failed','A workflow step did not complete successfully')
                    break
                if step['execution_id'] is None:
                    task=self.store.get(step['task_id'])
                    if not workflow.enabled or not task.enabled: break
                    if len(self.store.active())>=256: break
                    execution=uuid4().hex
                    with self.store.db:
                        self.store.db.execute('INSERT INTO executions(id,task_id,occurrence,source_hash,state,scheduled) VALUES(?,?,?,?,?,?)',
                            (execution,task.task_id,'workflow:'+run['id']+':'+str(step['position']),task.fingerprint,'queued',stamp(now)))
                        self.store.db.execute('UPDATE workflow_steps SET execution_id=? WHERE workflow_run=? AND position=?',(execution,run['id'],step['position']))
                    self.store.finish_workflow(run['id'],'running')
                break
            else:
                self.store.finish_workflow(run['id'],'completed')

    def _dependencies_ready(self, task, execution=None):
        step=self.store.workflow_step(execution['id']) if execution else None
        if step:
            parent=self.store.db.execute('SELECT state FROM workflow_runs WHERE id=?',(step['workflow_run'],)).fetchone()
            if parent is None or parent['state'] not in ('queued','running'):
                return False
            previous=self.store.workflow_steps(step['workflow_run'])[:step['position']]
            return all(any(item['task_id']==dependency and item['execution_state']=='completed' for item in previous) for dependency in task.dependencies)

        for dependency in task.dependencies:
            # An old success cannot satisfy a currently failed dependency.
            history = self.store.history(dependency, limit=1)
            if not history or history[0]['state'] != 'completed':
                return False
        return True

    def tick(self, now: datetime | None = None):
        now = now or utcnow()
        current = stamp(now)
        monotonic = time.monotonic()
        for execution in self.store.active():
            if execution['state'] == 'running' and execution['run_id'] in self._deadlines and monotonic >= self._deadlines[execution['run_id']]:
                self.cancel_run(execution['run_id'])
                self.store.transition(execution['id'], 'cancelling', allowed=('running',), message='Task timeout; stop requested')
        if self.paused:
            return
        self.store.materialize_due(now)
        self.store.materialize_workflows(now)
        self._advance_workflows(now)
        history = self.store.active()
        active = [item for item in history if item['state'] in ('dispatching','running','cancelling')]
        occupied = self.busy_serials | {self.store.get(item['task_id']).serial for item in active}
        slots = max(0, self.max_concurrency - len(occupied))
        tasks = {task.task_id: task for task in self.store.tasks()}
        queued = [item for item in history if item['state']=='queued' and item['scheduled']<=current]
        queued.sort(key=lambda row: (-tasks[row['task_id']].priority, row['scheduled'], row['id']))
        for execution in queued:
            task = tasks[execution['task_id']]
            if not slots:
                break
            if (not task.enabled or not self.is_authorized(task) or task.fingerprint != execution['source_hash'] or task.serial in occupied or not self.available(task.serial) or not self._dependencies_ready(task,execution)):
                continue
            if not self.store.transition(execution['id'], 'dispatching', allowed=('queued',), started=current):
                continue
            try:
                request_id = self.dispatch(task)
                if not isinstance(request_id, str) or not request_id:
                    raise RuntimeError('Dispatcher did not return a request ID')
                self.store.transition(execution['id'], 'dispatching', allowed=('dispatching',), request_id=request_id)
            except Exception as error:
                # Submission failure never automatically retries a possibly
                # accepted command. A new run remains an explicit decision.
                self.store.transition(execution['id'], 'failed', allowed=('dispatching',), message=f'Dispatch failed: {type(error).__name__}: {error}')
                continue
            occupied.add(task.serial)
            slots -= 1

    def handle_event(self, event):
        kind = event.get('event')
        history = self.store.active()
        if kind in ('request', 'request_error') and event.get('command') == 'start':
            execution = next((item for item in history if item['request_id'] and item['request_id'] == event.get('request_id')), None)
            if execution is None:
                return
            if kind == 'request_error':
                self.store.transition(execution['id'], 'failed', allowed=('dispatching','cancelling'), message=event.get('message', 'Start rejected'))
            else:
                run_id = event['run_id']
                cancelling = execution['state'] == 'cancelling'
                self.store.transition(execution['id'], 'cancelling' if cancelling else 'running', allowed=('dispatching','cancelling'), run_id=run_id)
                self._deadlines[run_id] = time.monotonic() + self.store.get(execution['task_id']).timeout_seconds
                if cancelling:
                    self.cancel_run(run_id)
            return
        execution = next((item for item in history if item['run_id'] and item['run_id'] == event.get('run_id')), None)
        if execution is None:
            return
        if kind == 'error':
            self._errors[execution['run_id']] = event
        state = event.get('state')
        if kind == 'status' and state in ('completed','failed','cancelled'):
            message = execution['message'] if execution['state']=='cancelling' else ''
            failure = self._errors.pop(execution['run_id'], {})
            if state == 'failed':
                message = str(failure.get('message') or failure.get('error') or 'Worker failed; inspect Activity & Logs')
            self.store.transition(execution['id'], state, allowed=('running','cancelling'), message=message)
            self._deadlines.pop(execution['run_id'], None)
            task = self.store.get(execution['task_id'])
            # Only an explicitly approved whole-script idempotency policy may
            # restart. Transport/disconnect outcomes remain uncertain and revoke
            # authorization, even when such a policy exists.
            category = failure.get('failure', {}).get('category') or failure.get('recovery', {}).get('category')
            unsafe = category in ('device_connection','input_outcome_unknown') or failure.get('error_type') in ('DeviceDisconnected','DeviceOffline','DeviceUnauthorized','CommandTimeout','CommandFailed')
            if unsafe:
                self.revoke(task.task_id)
            elif state == 'failed' and execution['state'] != 'cancelling' and task.restart_safe and self.is_authorized(task) and execution['attempt'] < task.max_retries:
                attempt = execution['attempt'] + 1
                due = stamp(utcnow()) + min(30, 2 ** (attempt-1))
                retry_id=uuid4().hex
                step=self.store.workflow_step(execution['id'])
                with self.store.db:
                    self.store.db.execute('INSERT INTO executions(id,task_id,occurrence,source_hash,state,scheduled,attempt,message) VALUES(?,?,?,?,?,?,?,?)',
                                          (retry_id, task.task_id, execution['occurrence']+f':retry:{attempt}', task.fingerprint, 'queued', due, attempt, 'Explicit idempotent whole-script restart policy'))

                    if step:
                        self.store.db.execute('UPDATE workflow_steps SET execution_id=? WHERE workflow_run=? AND position=?',(retry_id,step['workflow_run'],step['position']))
