import hashlib
from pathlib import Path

import pytest

from app.automation.debug_sources import snapshot_sources, validate_sources
from app.automation.runtime import RuntimeCoordinator
from app.editor.breakpoints import BreakpointStore
from test_debugger import command, finished, stopped


def test_imported_source_is_frozen_and_breakpoints_map_to_each_snapshot(tmp_path):
    package = tmp_path / 'helpers'
    package.mkdir()
    (package / '__init__.py').write_text('')
    helper = package / 'maths.py'
    helper_source = 'def calculate(value):\n    inside = value + 2\n    return inside\n'
    helper.write_text(helper_source)
    script = tmp_path / 'main.py'
    source = 'from helpers.maths import calculate\nresult = calculate(40)\ntap(result, 3)\n'
    script.write_text(source)
    sources = snapshot_sources(tmp_path, str(script), source)
    with RuntimeCoordinator() as runtime:
        run = runtime.start(source, 'fixture-imported', trusted=True, project_root=tmp_path,
            script_id=str(script), debug=True, breakpoints=[1], debug_sources=sources,
            file_breakpoints={str(helper): [2]})
        assert stopped(runtime)['source_path'] == str(script)
        helper.write_text('raise RuntimeError("later unapproved disk edit")\n')
        command(runtime, run, 'continue')
        event = stopped(runtime)
        assert event['source_path'] == str(helper) and event['line'] == 2
        assert event['source_hash'] == hashlib.sha256(helper_source.encode()).hexdigest()
        assert event['main_source_hash'] == hashlib.sha256(source.encode()).hexdigest()
        assert event['stack'][1]['source_hash'] == event['main_source_hash']
        assert {v['name']: v['value'] for v in event['locals']}['value'] == '40'
        command(runtime, run, 'set_breakpoints', source_path=str(helper), lines=[3])
        command(runtime, run, 'step_over')
        event = stopped(runtime)
        assert event['source_path'] == str(helper) and event['line'] == 3
        assert {v['name']: v['value'] for v in event['locals']}['inside'] == '42'
        command(runtime, run, 'continue')
        events = finished(runtime, run)
        assert runtime.snapshot()[0].state == 'completed'
        assert any(e.get('command') == 'tap' and e['arguments']['x'] == 42 for e in events)


def test_import_snapshot_does_not_execute_source_and_rejects_external_files(tmp_path):
    marker = tmp_path / 'executed'
    helper = tmp_path / 'helper.py'
    helper.write_text(f'open({str(marker)!r}, "w").write("wrong")\n')
    snapshots = snapshot_sources(tmp_path, '<editor>', 'pass\n')
    assert str(helper) in snapshots and not marker.exists()
    with pytest.raises(ValueError, match='contained'):
        validate_sources({'<editor>':'pass\n', str(tmp_path.parent / 'outside.py'):'pass'}, tmp_path, '<editor>', 'pass\n')
    with RuntimeCoordinator() as runtime:
        with pytest.raises(ValueError, match='approved source'):
            runtime.start('pass', 'fixture', trusted=True, project_root=tmp_path, debug=True,
                          file_breakpoints={str(helper):[1]})
        assert not runtime.snapshot()


def test_snapshot_limits_and_symlink_escape(tmp_path):
    with pytest.raises(ValueError, match='size'):
        validate_sources({'<editor>': 'x' * 1_000_001}, tmp_path, '<editor>', 'x' * 1_000_001)
    external = tmp_path.parent / 'external-module.py'
    external.write_text('pass')
    link = tmp_path / 'linked.py'
    try:
        link.symlink_to(external)
    except OSError:
        return  # Windows developer mode is not required for ordinary users.
    assert str(link) not in snapshot_sources(tmp_path, '<editor>', 'pass')


def test_breakpoints_reopen_only_on_matching_source_and_remain_inert(tmp_path):
    script = tmp_path / 'main.py'
    source = 'x = 1\ny = 2\n'
    script.write_text(source)
    store = BreakpointStore(tmp_path / 'user-state')
    store.save(script, tmp_path, source, [2])
    assert BreakpointStore(tmp_path / 'user-state').load(script, tmp_path, source) == [2]
    assert store.load(script, tmp_path, 'pass\n') == []
    assert len(list((tmp_path / 'user-state').glob('*.json'))) == 1
    with pytest.raises(ValueError, match='contained'):
        store.save(tmp_path.parent / 'external.py', tmp_path, source, [1])


def test_breakpoint_corruption_preserved_and_no_symlink_overwrite(tmp_path):
    script = tmp_path / 'main.py'
    store = BreakpointStore(tmp_path / 'state')
    store.save(script, tmp_path, 'pass', [1])
    target = next((tmp_path / 'state').glob('*.json'))
    target.write_text('not-json')
    with pytest.raises(ValueError):
        store.load(script, tmp_path, 'pass')
    assert target.read_text() == 'not-json'
