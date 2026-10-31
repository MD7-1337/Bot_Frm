"""Durable scheduling, failure decisions and actual isolated simulation execution."""
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import sqlite3
import time

import pytest

from app.tasks import Task, TaskStore, TaskScheduler
from app.tasks.store import next_due

UTC = timezone.utc
NOW = datetime(2026,10,31,9,tzinfo=UTC)


def definition(tmp_path, **changes):
    return replace(Task('task-one','Collect reward','print(42)','phone-one',str(tmp_path)), **changes)


@pytest.fixture
def store(tmp_path):
    instance = TaskStore(tmp_path/'tasks.sqlite')
    yield instance
    instance.close()


def scheduler(store, *, available=lambda serial: True, limit=4):
    submitted, cancelled = [], []
    def dispatch(task):
        submitted.append(task)
        return f'request-{len(submitted)}'
    engine = TaskScheduler(store,dispatch,cancelled.append,available,max_concurrency=limit)
    return engine,submitted,cancelled


def test_schema_roundtrip_source_and_session_trust(store,tmp_path):
    task=definition(tmp_path,schedule='interval',interval_seconds=10)
    store.save(task,now=NOW)
    engine,submitted,_=scheduler(store)
    engine.resume()
    engine.tick(NOW+timedelta(seconds=10))
    assert submitted==[]
    engine.authorize(task.task_id)
    engine.tick(NOW+timedelta(seconds=11))
    assert len(submitted)==1
    assert submitted[0].source=='print(42)'
    engine.tick(NOW+timedelta(seconds=12))
    assert len(submitted)==1
    assert store.db.execute('PRAGMA user_version').fetchone()[0]==2
    assert store.get(task.task_id)==task


def test_invalid_types_timezone_source_and_retry_policies(store,tmp_path):
    task=definition(tmp_path)
    for changes in ({'task_id':'a'*129}, {'script_id':'a'*1025}, {'serial':'-e'}, {'serial':'phone one'}, {'timeout_seconds':float('nan')}, {'timeout_seconds':True}, {'timezone':'No/Timezone'}, {'max_retries':1}, {'interval_seconds':True}, {'enabled':1}, {'source':'x'*1_000_001}, {'schedule':'once','at':'2026-11-01T09:00:00'}, {'project_root':'relative'}):
        with pytest.raises(ValueError):
            store.save(replace(task,**changes))
    assert store.tasks()==[]


def test_dependencies_cycles_and_failed_write_leave_prior_task(store,tmp_path):
    first=definition(tmp_path)
    second=replace(first,task_id='two',dependencies=('task-one',))
    store.save(first,now=NOW)
    store.save(second,now=NOW)
    with pytest.raises(ValueError,match='cycle'):
        store.save(replace(first,dependencies=('two',)),now=NOW)
    assert store.get(first.task_id)==first
    with pytest.raises(ValueError,match='dependent'):
        store.delete(first.task_id)
    with pytest.raises(ValueError,match='does not exist'):
        store.save(replace(first,dependencies=('missing',)))


def test_atomic_rollback_interrupted_sqlite_write(store,tmp_path):
    task=definition(tmp_path)
    store.save(task)
    with pytest.raises(RuntimeError):
        with store.db:
            store.db.execute('DELETE FROM tasks WHERE id=?',(task.task_id,))
            raise RuntimeError('injected interrupted transaction')
    assert store.get(task.task_id)==task


def test_unknown_migration_preserves_file(tmp_path):
    path=tmp_path/'future.sqlite'
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE sentinel(value TEXT)')
        db.execute("INSERT INTO sentinel VALUES('preserve me')")
        db.execute('PRAGMA user_version=42')
    with pytest.raises(ValueError,match='Unsupported'):
        TaskStore(path)
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT value FROM sentinel').fetchone()[0]=='preserve me'
        assert db.execute('PRAGMA user_version').fetchone()[0]==42


def test_timezone_daily_weekly_and_dst_gap_fold(tmp_path):
    task=definition(tmp_path,schedule='daily',at='09:00',timezone='Europe/Paris')
    assert next_due(task,NOW)==datetime(2026,11,1,8,tzinfo=UTC).timestamp()
    task=replace(task,schedule='weekly',weekdays=(0,))
    assert next_due(task,NOW)==datetime(2026,11,2,8,tzinfo=UTC).timestamp()
    task=replace(task,schedule='daily',at='02:30')
    # Nonexistent 02:30 on spring transition is skipped, not shifted.
    assert next_due(task,datetime(2026,3,29,0,tzinfo=UTC))==datetime(2026,3,30,0,30,tzinfo=UTC).timestamp()
    # The repeated fall hour is dispatched once, using fold=0.
    occurrence=next_due(task,datetime(2026,10,25,0,tzinfo=UTC))
    assert occurrence==datetime(2026,10,25,0,30,tzinfo=UTC).timestamp()
    assert next_due(task,datetime.fromtimestamp(occurrence,UTC))==datetime(2026,10,26,1,30,tzinfo=UTC).timestamp()


def test_interval_missed_policy_coalesces_and_deduplicates(store,tmp_path):
    task=definition(tmp_path,schedule='interval',interval_seconds=10,missed='run_once')
    store.save(task,now=NOW)
    store.materialize_due(NOW+timedelta(seconds=101))
    store.materialize_due(NOW+timedelta(seconds=101))
    assert len(store.history())==1
    assert store.history()[0]['state']=='queued'
    assert store.db.execute('SELECT next_due FROM tasks').fetchone()[0]==(NOW+timedelta(seconds=110)).timestamp()
    store.save(replace(task,task_id='skip-task',missed='skip'),now=NOW)
    store.materialize_due(NOW+timedelta(seconds=100))
    assert store.history()[0]['state']=='missed'


def test_restart_marks_unknown_and_cancels_pending_without_authorization(store,tmp_path):
    task=definition(tmp_path)
    store.save(task)
    queued=store.enqueue(task.task_id)
    active=store.enqueue(task.task_id)
    store.transition(active,'dispatching',allowed=('queued',))
    reopened=TaskStore(store.path)
    assert {row['id']:row['state'] for row in reopened.history()}=={queued:'cancelled',active:'uncertain'}
    engine,submitted,_=scheduler(reopened)
    engine.resume();engine.tick()
    assert not submitted
    reopened.close()


def test_priority_device_arbitration_and_dependencies(store,tmp_path):
    first=definition(tmp_path,priority=1)
    higher=replace(first,task_id='higher',priority=10)
    dependent=replace(first,task_id='dependent',serial='phone-two',dependencies=('higher',))
    for task in (first,higher,dependent):store.save(task)
    engine,submitted,_=scheduler(store)
    for task in (first,higher,dependent):
        engine.authorize(task.task_id);engine.run_now(task.task_id)
    engine.resume();engine.tick()
    assert [task.task_id for task in submitted]==['higher']
    engine.handle_event({'event':'request','command':'start','request_id':'request-1','run_id':'run-1'})
    engine.handle_event({'event':'status','run_id':'run-1','state':'completed'})
    engine.tick()
    assert {task.task_id for task in submitted}=={'task-one','higher','dependent'}


def test_unavailable_device_cancel_emergency_and_source_approval(store,tmp_path):
    task=definition(tmp_path)
    store.save(task)
    engine,submitted,cancelled=scheduler(store,available=lambda serial:False)
    with pytest.raises(PermissionError):engine.run_now(task.task_id)
    engine.authorize(task.task_id)
    engine.run_now(task.task_id)
    engine.resume();engine.tick()
    assert not submitted
    engine.revoke_device(task.serial)
    assert store.history()[0]['state']=='cancelled'
    assert not engine.is_authorized(task)
    engine.authorize(task.task_id)
    store.save(replace(task,source='print(99)'))
    assert not engine.is_authorized(store.get(task.task_id))
    engine.emergency_stop()
    assert engine.paused and not engine.authorized


def test_cancel_during_start_ack_cancels_actual_owned_run(store,tmp_path):
    task=definition(tmp_path);store.save(task)
    engine,submitted,cancelled=scheduler(store)
    engine.authorize(task.task_id);engine.run_now(task.task_id);engine.resume();engine.tick()
    engine.cancel_task(task.task_id)
    assert store.history()[0]['state']=='cancelling'
    engine.handle_event({'event':'request','command':'start','request_id':'request-1','run_id':'late-run'})
    assert cancelled==['late-run']
    engine.handle_event({'event':'status','run_id':'late-run','state':'cancelled'})
    assert store.history()[0]['state']=='cancelled'


def test_timeout_and_force_stopped_snapshot_reconciliation(store,tmp_path):
    from app.automation.runtime import RunInfo
    task=definition(tmp_path);store.save(task)
    engine,submitted,cancelled=scheduler(store)
    engine.authorize(task.task_id);engine.run_now(task.task_id);engine.resume();engine.tick()
    engine.handle_event({'event':'request','command':'start','request_id':'request-1','run_id':'owned'})
    engine._deadlines['owned']=time.monotonic()-1
    engine.tick()
    assert cancelled==['owned']
    engine.set_busy_serials([RunInfo('owned',task.serial,task.script_id,'mock',state='cancelled',exitcode=-15)])
    assert store.history()[0]['state']=='cancelled'


def test_transport_failure_never_retries_even_explicit_restart_policy(store,tmp_path):
    task=definition(tmp_path,max_retries=3,restart_safe=True);store.save(task)
    engine,_,_=scheduler(store)
    engine.authorize(task.task_id);engine.run_now(task.task_id);engine.resume();engine.tick()
    engine.handle_event({'event':'request','command':'start','request_id':'request-1','run_id':'run'})
    engine.handle_event({'event':'error','run_id':'run','error_type':'CommandTimeout','message':'unknown outcome','failure':{'category':'input_outcome_unknown'}})
    engine.handle_event({'event':'status','run_id':'run','state':'failed'})
    assert len(store.history())==1 and not engine.is_authorized(task)


def test_explicit_safe_restart_is_bounded(store,tmp_path):
    task=definition(tmp_path,max_retries=1,restart_safe=True);store.save(task)
    engine,_,_=scheduler(store)
    engine.authorize(task.task_id);engine.run_now(task.task_id);engine.resume();engine.tick()
    engine.handle_event({'event':'request','command':'start','request_id':'request-1','run_id':'run'})
    engine.handle_event({'event':'error','run_id':'run','error_type':'RecognitionTimeout','message':'no target','failure':{'category':'recognition'}})
    engine.handle_event({'event':'status','run_id':'run','state':'failed'})
    history=store.history()
    assert len(history)==2
    assert history[0]['state']=='queued' and history[0]['attempt']==1
    engine.tick(datetime.now(UTC)+timedelta(seconds=3))
    engine.handle_event({'event':'request','command':'start','request_id':'request-2','run_id':'run2'})
    engine.handle_event({'event':'status','run_id':'run2','state':'failed'})
    assert len(store.history())==2


def test_real_scheduled_simulation_worker_changes_screen(store,tmp_path):
    from app.simulation.model import SimulationManager
    from app.simulation.project import create_project
    from app.automation.runtime import RuntimeCoordinator
    manager=SimulationManager()
    phone=manager.create()
    root,_=create_project(tmp_path/'project',phone.serial,'image')
    task=definition(root,source='click("start.png")\nprint("scheduled success")',serial=phone.serial)
    store.save(task)
    with RuntimeCoordinator() as runtime:
        def dispatch(item):
            # Real coordinator integration: the Qt adapter performs the same
            # start request/ack mapping without substituting the worker.
            run=runtime.start(item.source,item.serial,backend='simulation',trusted=True,project_root=item.project_root,simulation_config=manager.config(item.serial))
            submitted.append(run)
            return 'request-real'
        submitted=[]
        engine=TaskScheduler(store,dispatch,runtime.cancel,lambda serial:True)
        engine.authorize(task.task_id);engine.run_now(task.task_id);engine.resume();engine.tick()
        engine.handle_event({'event':'request','command':'start','request_id':'request-real','run_id':submitted[0]})
        deadline=time.monotonic()+10
        while time.monotonic()<deadline:
            for event in runtime.poll():engine.handle_event(event)
            engine.set_busy_serials(runtime.snapshot())
            if store.history()[0]['state']=='completed':break
            time.sleep(.01)
        assert store.history()[0]['state']=='completed'
        assert manager.client(phone.serial).state()['screen']=='dashboard'
    manager.close()


def test_portable_task_definitions_import_disabled_without_approval(store,tmp_path):
    root=tmp_path/'old-project';root.mkdir()
    script=root/'scripts'/'collect.py';script.parent.mkdir();script.write_text('print(42)')
    first=definition(root,script_id=str(script))
    second=replace(first,task_id='dependent',dependencies=(first.task_id,))
    store.save(first);store.save(second)
    definitions=store.export_definitions(root)
    assert all(item['project_root']=='.' for item in definitions)
    assert definitions[0]['script_id']=='scripts/collect.py'
    destination=tmp_path/'imported';destination.mkdir()
    imported=store.import_definitions(definitions,destination)
    assert len(imported)==2 and all(not task.enabled for task in imported)
    assert all(task.task_id not in {'task-one','dependent'} for task in imported)
    assert {task.project_root for task in imported}=={str(destination)}
    assert all(task.script_id==str(destination/'scripts/collect.py') for task in imported)
    identities={task.task_id for task in imported}
    assert any(set(task.dependencies)<=identities and task.dependencies for task in imported)
    engine,_,_=scheduler(store)
    assert not any(engine.is_authorized(task) for task in imported)


def test_import_path_traversal_symlink_and_cycle_rejected_without_writes(store,tmp_path):
    task=definition(tmp_path);store.save(task)
    definitions=store.export_definitions(tmp_path)
    for script in ('../escape.py','/tmp/escape.py','C:\\escape.py','scripts/../../escape.py'):
        malformed=[{**definitions[0],'script_id':script}]
        with pytest.raises(ValueError):store.import_definitions(malformed,tmp_path)
        assert len(store.tasks())==1
    root=tmp_path/'project';root.mkdir()
    outside=tmp_path/'outside';outside.mkdir()
    (root/'scripts').symlink_to(outside,target_is_directory=True)
    with pytest.raises(ValueError,match='escapes'):
        store.import_definitions([{**definitions[0],'script_id':'scripts/escape.py'}],root)
    with pytest.raises(ValueError,match='dependency'):
        store.import_definitions([{**definitions[0],'dependencies':['missing']}],tmp_path)
    a={**definitions[0],'task_id':'a','dependencies':['b']}
    b={**definitions[0],'task_id':'b','dependencies':['a']}
    with pytest.raises(ValueError,match='cycle'):
        store.import_definitions([a,b],tmp_path)
    assert len(store.tasks())==1


def test_import_transaction_rolls_back_on_sql_failure(store,tmp_path):
    task=definition(tmp_path);store.save(task)
    definitions=store.export_definitions(tmp_path)
    definitions.append({**definitions[0],'task_id':'other','name':'FAIL INSERT'})
    with store.db:
        store.db.execute("CREATE TRIGGER reject_import BEFORE INSERT ON tasks WHEN json_extract(NEW.definition,'$.name')='FAIL INSERT' BEGIN SELECT RAISE(ABORT, 'injected write failure'); END")
    with pytest.raises(sqlite3.IntegrityError):store.import_definitions(definitions,tmp_path)
    assert store.tasks()==[task]


def test_one_time_past_schedule_honors_missed_policy(store,tmp_path):
    task=definition(tmp_path,schedule='once',at='2026-10-30T09:00:00+00:00',missed='run_once')
    store.save(task,now=NOW)
    store.materialize_due(NOW)
    assert store.history()[0]['state']=='queued'
    store.materialize_due(NOW)
    assert len(store.history())==1


def test_migration_failure_rolls_back_schema_and_version(monkeypatch,tmp_path):
    # Fail the second migration statement in a real SQLite transaction.
    original=sqlite3.connect
    class FailingConnection(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if sql.startswith('CREATE TABLE IF NOT EXISTS executions'):
                raise sqlite3.OperationalError('injected schema failure')
            return super().execute(sql,*args,**kwargs)
    def failing(*args,**kwargs):
        return original(*args,**kwargs,factory=FailingConnection)
    monkeypatch.setattr(sqlite3,'connect',failing)
    path=tmp_path/'migration.sqlite'
    with pytest.raises(sqlite3.OperationalError):TaskStore(path)
    with original(path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==0
        assert db.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()==[]


def test_four_real_scheduled_devices_and_independent_results(store,tmp_path):
    from app.simulation.model import SimulationManager
    from app.simulation.project import create_project
    from app.automation.runtime import RuntimeCoordinator
    manager=SimulationManager()
    phones=[manager.create() for _ in range(4)]
    root,_=create_project(tmp_path/'project',phones[0].serial,'image')
    tasks=[definition(root,task_id=f'task-{index}',source='click("start.png")',serial=phone.serial) for index,phone in enumerate(phones)]
    for task in tasks:store.save(task)
    try:
        with RuntimeCoordinator(max_workers=4) as runtime:
            submitted=[]
            def dispatch(item):
                run=runtime.start(item.source,item.serial,backend='simulation',trusted=True,project_root=item.project_root,simulation_config=manager.config(item.serial))
                request=f'request-{len(submitted)}'
                submitted.append((request,run))
                return request
            engine=TaskScheduler(store,dispatch,runtime.cancel,lambda serial:True,max_concurrency=4)
            for task in tasks:engine.authorize(task.task_id);engine.run_now(task.task_id)
            engine.resume();engine.tick()
            assert len(submitted)==4
            for request,run in submitted:engine.handle_event({'event':'request','command':'start','request_id':request,'run_id':run})
            deadline=time.monotonic()+15
            while time.monotonic()<deadline:
                for event in runtime.poll():engine.handle_event(event)
                engine.set_busy_serials(runtime.snapshot())
                if all(item['state']=='completed' for item in store.history()):break
                time.sleep(.01)
            assert len(store.history())==4
            assert all(item['state']=='completed' for item in store.history()),store.history()
            assert len({run.pid for run in runtime.snapshot()})==4
            assert all(manager.client(phone.serial).state()['screen']=='dashboard' for phone in phones)
    finally:
        manager.close()


def test_execution_state_machine_rejects_regressions_and_stale_changes(store,tmp_path):
    task=definition(tmp_path);store.save(task)
    identity=store.enqueue(task.task_id)
    with pytest.raises(ValueError,match='transition'):
        store.transition(identity,'completed')
    assert store.transition(identity,'dispatching',allowed=('queued',))
    assert not store.transition(identity,'cancelled',allowed=('queued',))
    assert store.transition(identity,'running',allowed=('dispatching',))
    with pytest.raises(ValueError,match='transition'):
        store.transition(identity,'queued')
    assert store.transition(identity,'completed',allowed=('running',))
    assert not store.transition(identity,'running')


def test_database_symlink_is_rejected_and_target_preserved(tmp_path):
    actual=tmp_path/'user-file';actual.write_bytes(b'preserve unrelated bytes')
    link=tmp_path/'tasks.sqlite';link.symlink_to(actual)
    with pytest.raises(ValueError,match='symbolic link'):TaskStore(link)
    assert link.is_symlink() and actual.read_bytes()==b'preserve unrelated bytes'
