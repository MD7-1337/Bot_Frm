"""Real offline state, rendered pixels and spawned execution; no Android involved."""
import time

import cv2
import numpy as np
import pytest

from app.automation.api import Device, DeviceDisconnected
from app.automation.runtime import RuntimeCoordinator
from app.devices.adb import AdbClient, validate_serial
from app.devices.registry import DeviceRegistry
from app.projects.library import AssetLibrary
from app.simulation.model import SimulationManager, SimulationClient, BUTTON, MENU_BUTTON, LABEL
from app.simulation.project import create_project, SOURCES
from test_script_runtime import completed, drain_until


@pytest.fixture
def simulation(tmp_path):
    manager = SimulationManager()
    info = manager.create()
    root, _ = create_project(tmp_path, info.serial, "image")
    try:
        yield manager, info, root
    finally:
        manager.close()


def test_real_image_matching_click_changes_shared_simulation_state(simulation):
    manager, info, root = simulation
    client = manager.client(info.serial)
    device = Device(client, AssetLibrary(root))
    assert client.state()["screen"] == "start"
    assert device.click("start.png").x == 180
    assert client.state()["screen"] == "dashboard"
    assert device.exists("continue.png") is not None
    device.click("continue.png")
    assert client.state()["screen"] == "complete"


def test_recorded_scenario_and_swipe_are_meaningful(simulation):
    manager, info, root = simulation
    manager.reset(info.serial, "recorder", 1)
    device = Device(manager.client(info.serial), AssetLibrary(root))
    device.click("start.png")
    assert manager.client(info.serial).state()["screen"] == "menu"
    device.swipe(180,430,180,220,.1)
    assert manager.client(info.serial).state()["scroll"] == 1
    device.click("task_b.png")
    device.click("complete.png")
    assert manager.client(info.serial).state()["screen"] == "complete"


def test_delay_reset_and_old_context_revocation(simulation):
    manager, info, root = simulation
    old = manager.client(info.serial)
    manager.reset(info.serial, "wait", .15)
    with pytest.raises(DeviceDisconnected):
        old.capture()
    device = Device(manager.client(info.serial), AssetLibrary(root))
    started = time.monotonic()
    match = device.waitImage("reward.png", timeout=2, poll_interval=.03)
    assert match.device_serial == info.serial
    assert time.monotonic() - started >= .1
    device.click(match)
    assert manager.client(info.serial).state()["screen"] == "complete"


def test_simulation_cannot_route_to_adb_or_masquerade_as_discovery(simulation, monkeypatch):
    manager, info, root = simulation
    run = lambda *a, **k: pytest.fail("Simulation touched ADB subprocess")
    monkeypatch.setattr("app.devices.adb.subprocess.run", run)
    with pytest.raises(ValueError):
        validate_serial(info.serial)
    with pytest.raises(ValueError):
        AdbClient().tap(info.serial, 1,2)
    registry = DeviceRegistry()
    from app.devices.adb import DeviceInfo
    with pytest.raises(ValueError):
        registry.update([DeviceInfo(info.serial, "device")])
    device = Device(manager.client(info.serial), AssetLibrary(root))
    device.click("start.png")
    assert registry.snapshot() == []
    with RuntimeCoordinator() as runtime:
        with pytest.raises(ValueError):
            runtime.start("pass", info.serial, backend="adb", trusted=True, project_root=root)


def test_capabilities_are_bound_to_identity_generation_and_secret(simulation):
    manager, info, root = simulation
    config = manager.config(info.serial)
    other = manager.create()
    with pytest.raises(DeviceDisconnected):
        SimulationClient(other.serial, config).capture()
    forged = {**config, "token": "0" * 64}
    with pytest.raises(DeviceDisconnected):
        SimulationClient(info.serial, forged).capture()
    manager.stop(info.serial)
    with pytest.raises(DeviceDisconnected):
        SimulationClient(info.serial, config).capture()


def test_two_spawned_scripts_change_independent_sessions(simulation, tmp_path):
    manager, one, root = simulation
    two = manager.create("recorder")
    with RuntimeCoordinator(max_workers=2) as runtime:
        first = runtime.start(SOURCES["image"], one.serial, backend="simulation", trusted=True, project_root=root, simulation_config=manager.config(one.serial))
        second = runtime.start(SOURCES["recorder"], two.serial, backend="simulation", trusted=True, project_root=root, simulation_config=manager.config(two.serial))
        events = completed(runtime, [first, second])
        assert all(run.state == "completed" for run in runtime.snapshot()), events
        assert len({run.pid for run in runtime.snapshot()}) == 2
        assert manager.client(one.serial).state()["screen"] == "dashboard"
        assert manager.client(two.serial).state()["screen"] == "complete"
        assert {event['backend'] for event in events} == {'simulation'}


def test_reset_invalidates_running_worker_without_replaying(simulation):
    manager, info, root = simulation
    with RuntimeCoordinator() as runtime:
        run = runtime.start("while True:\n    capture()\n    sleep(.02)\n", info.serial, backend="simulation", trusted=True, project_root=root, simulation_config=manager.config(info.serial))
        drain_until(runtime, lambda e, r: any(x.get('state')=='running' for x in e))
        manager.reset(info.serial, "image", 1)
        events = completed(runtime, [run])
        assert runtime.snapshot()[0].state == "failed"
        assert any(event.get('error_type') == 'DeviceDisconnected' for event in events)
        assert manager.client(info.serial).state()["screen"] == 'start'


def test_wait_timeout_missing_asset_pause_and_cancellation(simulation):
    from app.automation.api import RecognitionTimeout, AssetNotFound
    manager,info,root=simulation
    manager.reset(info.serial,'wait',60)
    device=Device(manager.client(info.serial),AssetLibrary(root))
    with pytest.raises(RecognitionTimeout):device.waitImage('reward.png',timeout=.05,poll_interval=.01)
    with pytest.raises(AssetNotFound):device.waitImage('missing.png',timeout=1)
    with RuntimeCoordinator() as runtime:
        run=runtime.start('waitImage("reward.png", timeout=50)\nclick("reward.png")\n',info.serial,
                          backend='simulation',simulation_config=manager.config(info.serial),trusted=True,project_root=root)
        drain_until(runtime,lambda e,r:any(x.get('state')=='running' for x in e))
        runtime.pause(run);drain_until(runtime,lambda e,r:r[0].state=='paused')
        assert manager.client(info.serial).state()['actions']==0
        runtime.resume(run);drain_until(runtime,lambda e,r:any(x.get('state')=='running' for x in e))
        runtime.cancel(run,grace=.2)
        assert runtime.snapshot()[0].state=='cancelled'
        assert manager.client(info.serial).state()['actions']==0
