"""Durable exact-device groups and occurrence-correlated sequential workflows."""
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from pathlib import Path
import sqlite3
import time

import pytest

from app.tasks import Task,TaskStore,TaskScheduler
from app.tasks.workflows import Workflow

NOW=datetime(2026,10,31,9,tzinfo=timezone.utc)

@pytest.fixture
def store(tmp_path):
    instance=TaskStore(tmp_path/'tasks.sqlite')
    yield instance
    instance.close()


def task(root,identity='one',serial='phone-one',**kw):
    return Task(identity,identity,'print(1)',serial,str(root),**kw)


def prepare(store,tmp_path):
    a=task(tmp_path);b=task(tmp_path,'two',dependencies=('one',))
    store.save(a);store.save(b)
    wf=Workflow('sequence','Sequential workflow',(a.task_id,b.task_id))
    store.save_workflow(wf)
    submitted=[];cancelled=[]
    def dispatch(item):
        submitted.append(item.task_id);return f'req-{len(submitted)}'
    engine=TaskScheduler(store,dispatch,cancelled.append,lambda serial:True)
    for item in (a,b):engine.authorize(item.task_id)
    engine.authorize_workflow(wf.workflow_id);engine.resume()
    return engine,wf,submitted,cancelled


def complete(engine,number,state='completed'):
    engine.handle_event({'event':'request','command':'start','request_id':f'req-{number}','run_id':f'run-{number}'})
    engine.handle_event({'event':'status','run_id':f'run-{number}','state':state})


def test_named_group_expansion_is_atomic_and_exact_without_approval(store,tmp_path):
    store.save_group('lab',['phone-one','sim://explicit-phone'])
    copies=store.expand_group('lab',task(tmp_path))
    assert {item.serial for item in copies}=={'phone-one','sim://explicit-phone'}
    assert len({item.task_id for item in copies})==2
    engine=TaskScheduler(store,lambda _:None,lambda _:None,lambda _:True)
    assert not any(engine.is_authorized(item) for item in copies)
    for members in ([],['-d'],['a b'],['a','a'],['a\x00b']):
        with pytest.raises(ValueError):store.save_group('bad',members)
    store.delete_group('lab')
    assert len(store.tasks())==2 and not store.groups()


def test_group_expansion_rolls_back_failed_second_copy(store,tmp_path):
    store.save_group('lab',['phone-one','phone-two'])
    with store.db:
        store.db.execute("CREATE TRIGGER reject_second BEFORE INSERT ON tasks WHEN json_extract(NEW.definition,'$.serial')='phone-two' BEGIN SELECT RAISE(ABORT,'test write failure'); END")
    with pytest.raises(sqlite3.IntegrityError):store.expand_group('lab',task(tmp_path))
    assert store.tasks()==[]


def test_workflow_order_and_scope_do_not_reuse_prior_success(store,tmp_path):
    engine,wf,submitted,_=prepare(store,tmp_path)
    first=engine.run_workflow(wf.workflow_id);engine.tick()
    assert submitted==['one']
    complete(engine,1);engine.tick();assert submitted==['one','two']
    complete(engine,2);engine.tick()
    assert store.workflow_history()[0]['state']=='completed'
    second=engine.run_workflow(wf.workflow_id);engine.tick()
    assert submitted==['one','two','one']
    # The successful step-two from the previous occurrence cannot unlock step2.
    assert store.workflow_steps(second)[1]['execution_id'] is None
    engine.tick();assert submitted==['one','two','one']
    complete(engine,3);engine.tick();assert submitted==['one','two','one','two']
    assert first!=second


def test_workflow_failed_step_never_runs_successor(store,tmp_path):
    engine,wf,submitted,_=prepare(store,tmp_path)
    engine.run_workflow(wf.workflow_id);engine.tick();complete(engine,1,'failed');engine.tick()
    assert submitted==['one']
    assert store.workflow_history()[0]['state']=='failed'


def test_workflow_disconnect_emergency_and_pending_cancellation(store,tmp_path):
    engine,wf,submitted,cancelled=prepare(store,tmp_path)
    first=engine.run_workflow(wf.workflow_id);engine.tick()
    engine.handle_event({'event':'request','command':'start','request_id':'req-1','run_id':'run-1'})
    engine.revoke_device('phone-one')
    assert cancelled==['run-1']
    assert store.workflow_history()[0]['state']=='cancelled'
    engine.tick();assert submitted==['one']
    with pytest.raises(PermissionError):engine.run_workflow(wf.workflow_id)
    for item in store.tasks():engine.authorize(item.task_id)
    engine.authorize_workflow(wf.workflow_id)
    second=engine.run_workflow(wf.workflow_id)
    engine.emergency_stop()
    assert engine.paused and not engine.authorized_workflows
    assert {row['state'] for row in store.workflow_history()}=={'cancelled'}


def test_workflow_source_or_configuration_changes_revoke_approval(store,tmp_path):
    engine,wf,_,_=prepare(store,tmp_path)
    for changes in ({'source':'print(2)'},{'dependencies':()},{'timeout_seconds':10},{'schedule':'interval'}):
        original=store.get('two');store.save(replace(original,**changes))
        assert not engine.workflow_authorized(wf)
        store.save(original)
    store.save_workflow(replace(wf,task_ids=('one','two','one')))
    with pytest.raises(PermissionError):engine.run_workflow(wf.workflow_id)


def test_workflow_validation_manual_steps_dependencies_and_task_deletion(store,tmp_path):
    engine,wf,_,_=prepare(store,tmp_path)
    with pytest.raises(ValueError,match='before'):store.save_workflow(replace(wf,task_ids=('two','one')))
    with pytest.raises(ValueError,match='does not exist'):store.save_workflow(replace(wf,task_ids=('missing',)))
    with pytest.raises(ValueError,match='workflows'):store.delete('one')
    scheduled=task(tmp_path,'scheduled',schedule='interval');store.save(scheduled)
    with pytest.raises(ValueError,match='manual'):store.save_workflow(replace(wf,task_ids=('scheduled',)))


def test_workflow_interval_trigger_deduplicates_and_restart_revokes(store,tmp_path):
    engine,wf,submitted,_=prepare(store,tmp_path)
    wf=replace(wf,schedule='interval',interval_seconds=10,missed='run_once')
    store.save_workflow(wf,now=NOW)
    engine.authorize_workflow(wf.workflow_id)
    store.materialize_workflows(NOW+timedelta(seconds=100))
    store.materialize_workflows(NOW+timedelta(seconds=100))
    assert len(store.workflow_history())==1
    reopened=TaskStore(store.path)
    try:
        assert reopened.workflow_history()[0]['state']=='cancelled'
        assert reopened.workflows()==[wf]
        fresh=TaskScheduler(reopened,lambda _:None,lambda _:None,lambda _:True)
        assert not fresh.workflow_authorized(wf)
    finally:reopened.close()


def test_v1_migration_preserves_backup_and_task_data(tmp_path):
    path=tmp_path/'tasks.sqlite'
    old=TaskStore(path);old.save(task(tmp_path));old.close()
    with sqlite3.connect(path) as db:
        for name in ('workflow_steps','workflow_runs','workflows','device_groups'):db.execute(f'DROP TABLE {name}')
        db.execute('PRAGMA user_version=1')
    migrated=TaskStore(path)
    try:
        assert migrated.get('one').source=='print(1)'
        assert migrated.db.execute('PRAGMA user_version').fetchone()[0]==2
        backups=list(tmp_path.glob('tasks.sqlite.v1-*.bak'));assert len(backups)==1
        with sqlite3.connect(backups[0]) as backup:
            assert backup.execute('PRAGMA user_version').fetchone()[0]==1
            assert backup.execute('SELECT id FROM tasks').fetchone()[0]=='one'
    finally:migrated.close()


def test_actual_two_device_group_workflow_workers_change_independent_screens(store,tmp_path):
    from app.automation.runtime import RuntimeCoordinator
    from app.simulation.model import SimulationManager
    from app.simulation.project import create_project
    manager=SimulationManager();phones=[manager.create(),manager.create()]
    root,_=create_project(tmp_path/'project',phones[0].serial,'image')
    store.save_group('demo-pair',[phone.serial for phone in phones])
    tasks=store.expand_group('demo-pair',Task('template','Click start','click("start.png")',phones[0].serial,str(root)))
    workflow=Workflow('pair','Two independently routed phones',tuple(item.task_id for item in tasks));store.save_workflow(workflow)
    try:
        with RuntimeCoordinator(max_workers=2) as runtime:
            submitted=[]
            def dispatch(item):
                run=runtime.start(item.source,item.serial,backend='simulation',trusted=True,project_root=item.project_root,simulation_config=manager.config(item.serial))
                request=f'req-{len(submitted)+1}';submitted.append((request,run));return request
            engine=TaskScheduler(store,dispatch,runtime.cancel,lambda serial:True)
            for item in tasks:engine.authorize(item.task_id)
            engine.authorize_workflow(workflow.workflow_id);engine.run_workflow(workflow.workflow_id);engine.resume()
            deadline=time.monotonic()+15;acked=set()
            while time.monotonic()<deadline:
                engine.tick()
                for request,run in submitted:
                    if request not in acked:
                        engine.handle_event({'event':'request','command':'start','request_id':request,'run_id':run});acked.add(request)
                for event in runtime.poll():engine.handle_event(event)
                engine.set_busy_serials(runtime.snapshot())
                if store.workflow_history()[0]['state']=='completed':break
                time.sleep(.01)
            assert store.workflow_history()[0]['state']=='completed'
            assert len(submitted)==2
            assert all(manager.client(phone.serial).state()['screen']=='dashboard' for phone in phones)
    finally:manager.close()


def test_project_import_keeps_workflow_order_disabled_and_rolls_back_bad_graph(store,tmp_path):
    engine,wf,_,_=prepare(store,tmp_path)
    definitions=store.export_definitions(tmp_path);workflows=store.export_workflows(tmp_path)
    imported,sequences=store.import_project_definitions(definitions,workflows,tmp_path/'restored')
    assert len(imported)==2 and len(sequences)==1
    assert not sequences[0].enabled and not any(item.enabled for item in imported)
    mapping={old['task_id']:new.task_id for old,new in zip(definitions,imported)}
    assert sequences[0].task_ids==tuple(mapping[item] for item in wf.task_ids)
    assert not engine.workflow_authorized(sequences[0])
    prior=len(store.tasks());prior_workflows=len(store.workflows())
    with pytest.raises(ValueError,match='missing'):
        store.import_project_definitions(definitions,[{**workflows[0],'task_ids':['absent']}],tmp_path/'bad')
    assert len(store.tasks())==prior and len(store.workflows())==prior_workflows


def test_workflow_child_enqueue_and_link_are_one_atomic_write(store,tmp_path):
    engine,wf,submitted,_=prepare(store,tmp_path)
    engine.run_workflow(wf.workflow_id)
    with store.db:
        store.db.execute("CREATE TRIGGER reject_link BEFORE UPDATE ON workflow_steps BEGIN SELECT RAISE(ABORT,'injected link failure'); END")
    with pytest.raises(sqlite3.IntegrityError):engine.tick()
    assert not store.active() and not submitted
    assert store.workflow_steps(store.workflow_history()[0]['id'])[0]['execution_id'] is None


def test_workflow_safe_retry_stays_bound_to_the_same_occurrence(store,tmp_path):
    engine,wf,submitted,_=prepare(store,tmp_path)
    first=replace(store.get('one'),max_retries=1,restart_safe=True)
    store.save(first);engine.authorize(first.task_id);engine.authorize_workflow(wf.workflow_id)
    identity=engine.run_workflow(wf.workflow_id);engine.tick()
    engine.handle_event({'event':'request','command':'start','request_id':'req-1','run_id':'run-1'})
    engine.handle_event({'event':'error','run_id':'run-1','error_type':'RecognitionTimeout','message':'no target','failure':{'category':'recognition'}})
    engine.handle_event({'event':'status','run_id':'run-1','state':'failed'})
    engine.tick(datetime.now(timezone.utc)+timedelta(seconds=3))
    assert submitted==['one','one']
    assert store.workflow_steps(identity)[1]['execution_id'] is None
    complete(engine,2);engine.tick()
    assert submitted==['one','one','two']
    complete(engine,3);engine.tick()
    assert store.workflow_history()[0]['state']=='completed'


def test_interrupted_v1_migration_rolls_back_and_keeps_backup(monkeypatch,tmp_path):
    path=tmp_path/'migration.sqlite'
    original=TaskStore(path);original.save(task(tmp_path));original.close()
    with sqlite3.connect(path) as connection:
        for name in ('workflow_steps','workflow_runs','workflows','device_groups'):connection.execute(f'DROP TABLE {name}')
        connection.execute('PRAGMA user_version=1')
    connect=sqlite3.connect
    class FailingConnection(sqlite3.Connection):
        def execute(self,sql,*args,**kwargs):
            if sql.startswith('CREATE TABLE IF NOT EXISTS workflows'):
                raise sqlite3.OperationalError('Injected workflow migration interruption')
            return super().execute(sql,*args,**kwargs)
    def failing(*args,**kwargs):
        return connect(*args,**kwargs,factory=FailingConnection)
    monkeypatch.setattr(sqlite3,'connect',failing)
    with pytest.raises(sqlite3.OperationalError):TaskStore(path)
    with connect(path) as connection:
        assert connection.execute('PRAGMA user_version').fetchone()[0]==1
        assert connection.execute('SELECT id FROM tasks').fetchone()[0]=='one'
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='device_groups'").fetchone() is None
    assert len(list(tmp_path.glob('migration.sqlite.v1-*.bak')))==1


def test_source_change_cancels_queued_workflow_child_before_dispatch(store,tmp_path):
    engine,wf,submitted,_=prepare(store,tmp_path)
    engine.available=lambda serial:False
    identity=engine.run_workflow(wf.workflow_id);engine.tick()
    assert not submitted and store.active()[0]['state']=='queued'
    store.save(replace(store.get('two'),source='print("changed")'))
    engine.available=lambda serial:True;engine.tick()
    assert not submitted and not store.active()
    assert store.workflow_history()[0]['state']=='failed'


def test_cancelled_worker_failure_never_uses_safe_retry_policy(store,tmp_path):
    engine,wf,submitted,cancelled=prepare(store,tmp_path)
    first=replace(store.get('one'),max_retries=1,restart_safe=True)
    store.save(first);engine.authorize(first.task_id);engine.authorize_workflow(wf.workflow_id)
    engine.run_workflow(wf.workflow_id);engine.tick()
    engine.handle_event({'event':'request','command':'start','request_id':'req-1','run_id':'run-1'})
    engine.cancel_workflow(wf.workflow_id)
    engine.handle_event({'event':'error','run_id':'run-1','error_type':'RecognitionTimeout','message':'late failure during cancellation'})
    engine.handle_event({'event':'status','run_id':'run-1','state':'failed'})
    engine.tick(datetime.now(timezone.utc)+timedelta(seconds=10))
    assert submitted==['one'] and not store.active()
    assert len(store.history())==1 and cancelled==['run-1']
