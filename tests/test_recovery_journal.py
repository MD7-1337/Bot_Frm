"""Transactional user-owned failure history and optional private PNG evidence."""
import hashlib
import json
import sqlite3

import cv2
import numpy as np
import pytest

from app.automation.recording import ScreenshotEvidence
from app.automation.recovery_journal import RecoveryJournal


def event(**changes):
    original = {"event": "error", "run_id": "run-one", "serial": "phone-one",
                "error_type": "RecognitionTimeout", "message": "target missing",
                "source_path": "scripts/main.py", "source_line": 2,
                "traceback": "Traceback\n  File scripts/main.py, line 2\nRecognitionTimeout: target missing",
                "failure": {"category": "recognition", "advice": "Inspect the screen", "automatic_retry": False},
                "timestamp": 1780000000.}
    return {**original, **changes}


def evidence(serial="phone-one"):
    image = np.random.default_rng(2).integers(0, 255, (30, 40, 3), dtype=np.uint8)
    return ScreenshotEvidence(serial, cv2.imencode(".png", image)[1].tobytes(), (40, 30))


def test_persists_actual_error_details_across_reopen(tmp_path):
    path = tmp_path / "user-data" / "failures.sqlite3"
    journal = RecoveryJournal(path)
    record_id = journal.record_event(event())
    restored = RecoveryJournal(path)
    recent = restored.recent()
    assert len(recent) == 1 and recent[0]["id"] == record_id
    detail = restored.detail(record_id)
    assert detail["source_line"] == 2
    assert "Traceback" in detail["traceback"] and detail["advice"] == "Inspect the screen"
    assert not detail["has_screenshot"] and "screenshot" not in detail
    assert json.loads(restored.export_report(record_id))["error_type"] == "RecognitionTimeout"


def test_only_errors_persist_and_duplicate_events_are_deduplicated(tmp_path):
    journal = RecoveryJournal(tmp_path / "history.sqlite3")
    assert journal.record_event({"event": "status", "state": "running"}) is None
    first = journal.record_event(event(source_line=None))
    second = journal.record_event(event(source_line=None))
    assert first == second and len(journal.recent()) == 1
    assert journal.record_event(event(source_line=3)) != first
    assert len(journal.recent()) == 2


def test_explicit_screen_evidence_matches_identity_and_export_omits_pixels(tmp_path):
    journal = RecoveryJournal(tmp_path / "history.sqlite3")
    screen = evidence()
    record_id = journal.record_event(event(), screen)
    detail = journal.detail(record_id, include_screenshot=True)
    assert detail["screenshot"] == screen.png
    assert detail["width"] == 40 and detail["height"] == 30
    report = json.loads(journal.export_report(record_id))
    assert "screenshot" not in report and report["has_screenshot"]
    with pytest.raises(ValueError, match="failed device"):
        journal.record_event(event(run_id="other"), evidence("other-phone"))
    assert len(journal.recent()) == 1


def test_later_capture_can_fill_empty_evidence_without_replacing_original(tmp_path):
    journal = RecoveryJournal(tmp_path / "history.sqlite3")
    record_id = journal.record_event(event())
    screen = evidence()
    assert journal.record_event(event(), screen) == record_id
    assert len(journal.recent()) == 1
    assert journal.detail(record_id, include_screenshot=True)["screenshot"] == screen.png


@pytest.mark.parametrize("change", [
    {"serial": "phone\nother"}, {"serial": None}, {"run_id": ""},
    {"timestamp": float("nan")}, {"timestamp": True}, {"timestamp": 10**400},
    {"source_line": True}, {"source_line": 0}, {"source_line": "2"},
    {"failure": "bad"}, {"message": ["not text"]},
])
def test_invalid_data_cannot_modify_previous_history(change, tmp_path):
    journal = RecoveryJournal(tmp_path / "history.sqlite3")
    record_id = journal.record_event(event())
    with pytest.raises((ValueError, TypeError)):
        journal.record_event(event(**change))
    assert len(journal.recent()) == 1 and journal.recent()[0]["id"] == record_id


def test_retention_deletes_only_oldest_events_in_same_transaction(tmp_path):
    journal = RecoveryJournal(tmp_path / "history.sqlite3", retention=2)
    ids = [journal.record_event(event(run_id=f"run-{n}", timestamp=1780000000+n)) for n in range(3)]
    assert [row["id"] for row in journal.recent()] == list(reversed(ids[1:]))
    assert journal.detail(ids[0]) is None


def test_interrupted_retention_write_rolls_back_the_new_error_and_deletion(tmp_path):
    path = tmp_path / "history.sqlite3"
    journal = RecoveryJournal(path, retention=1)
    first = journal.record_event(event())
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TRIGGER stop_delete BEFORE DELETE ON failures BEGIN SELECT RAISE(ABORT,'injected failure'); END")
    with pytest.raises(sqlite3.IntegrityError):
        journal.record_event(event(run_id="run-two", timestamp=1780000001))
    assert [row["id"] for row in journal.recent()] == [first]


def test_future_schema_is_rejected_without_rewriting_data(tmp_path):
    path = tmp_path / "future.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE preserve(value TEXT)")
        connection.execute("INSERT INTO preserve VALUES ('important')")
        connection.execute("PRAGMA user_version=99")
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    with pytest.raises(ValueError, match="Unsupported"):
        RecoveryJournal(path)
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest


def test_text_and_screenshot_retention_budgets_are_bounded(tmp_path, monkeypatch):
    import app.automation.recovery_journal as module
    monkeypatch.setattr(module, "MAX_STORED_SCREENSHOTS", len(evidence().png))
    journal = RecoveryJournal(tmp_path / "history.sqlite3")
    one = journal.record_event(event(message="x"*5000, traceback="t"*20000), evidence())
    two = journal.record_event(event(run_id="run-two", timestamp=1780000001), evidence())
    assert len(journal.detail(one)["message"]) == 4000
    assert len(journal.detail(one)["traceback"]) == 16000
    assert not journal.detail(one)["has_screenshot"]
    assert journal.detail(two)["has_screenshot"]


def test_symbolic_link_history_does_not_overwrite_user_file(tmp_path):
    target = tmp_path / "keep.txt"
    target.write_text("keep", encoding="utf-8")
    alias = tmp_path / "history.sqlite3"
    try:
        alias.symlink_to(target)
    except (OSError, NotImplementedError):
        pytest.skip("Local filesystem does not support symlink fixture")
    with pytest.raises(ValueError, match="symbolic link"):
        RecoveryJournal(alias)
    assert target.read_text() == "keep"
