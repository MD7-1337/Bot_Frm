"""User-owned SQLite failure history; no device commands or automatic execution."""
from __future__ import annotations

from contextlib import closing
import json
import math
from pathlib import Path
import sqlite3
import time
from uuid import uuid4

from app.automation.recording import ScreenshotEvidence

SCHEMA_VERSION = 1
MAX_SCREENSHOT_BYTES = 2_000_000
MAX_STORED_SCREENSHOTS = 20_000_000


def _text(value, name, maximum, *, optional=False):
    if optional and value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    return value[:maximum]


class RecoveryJournal:
    """Persist bounded diagnostic events and explicitly supplied PNG evidence.

    Evidence is a caller-selected current screenshot, never inferred from an old
    preview. This class does not fetch the screen, reconnect or replay anything.
    Local records may contain device identity, paths and private screen content.
    """

    def __init__(self, path, *, retention=500):
        self.path = Path(path).expanduser().absolute()
        if type(retention) is not int or not 1 <= retention <= 5000:
            raise ValueError("retention must be an integer from 1 to 5000")
        self.retention = retention
        if self.path.is_symlink():
            raise ValueError("Failure history must not overwrite a symbolic link")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection, connection:
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, SCHEMA_VERSION):
                raise ValueError(f"Unsupported failure-history schema {version}")
            if version == 0:
                connection.execute("""CREATE TABLE failures (
                    id TEXT PRIMARY KEY, created REAL NOT NULL, run_id TEXT NOT NULL,
                    serial TEXT NOT NULL, error_type TEXT NOT NULL, category TEXT NOT NULL,
                    message TEXT NOT NULL, source_path TEXT NOT NULL, source_line INTEGER,
                    traceback TEXT NOT NULL, advice TEXT NOT NULL, screenshot BLOB,
                    width INTEGER, height INTEGER,
                    UNIQUE(run_id, error_type, source_path, source_line, message)
                )""")
                connection.execute("CREATE INDEX failures_created ON failures(created)")
                connection.execute("""CREATE UNIQUE INDEX failure_event ON failures(
                    run_id,error_type,source_path,IFNULL(source_line,-1),message)""")
                connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")

    def _connect(self):
        connection = sqlite3.connect(self.path, timeout=2)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        return connection

    def record_event(self, event, screenshot: ScreenshotEvidence | None = None):
        """Store one worker error, returning its ID; other event types are ignored.

        Screenshot must carry the exact event serial. Capturing/lease/generation
        freshness belongs to the host; do not pass an old preview as evidence.
        """
        if not isinstance(event, dict):
            raise ValueError("Failure event must be a dictionary")
        if event.get("event") != "error":
            return None
        from app.devices.adb import validate_serial
        from app.simulation.model import is_simulation, validate_identity
        serial = event.get("serial")
        (validate_identity if is_simulation(serial) else validate_serial)(serial)
        run_id = _text(event.get("run_id"), "run_id", 200)
        if not run_id:
            raise ValueError("Failure event needs its run ID")
        failure = event.get("failure", {})
        if not isinstance(failure, dict):
            raise ValueError("Failure advice must be structured")
        timestamp = event.get("timestamp", time.time())
        if (isinstance(timestamp, bool) or not isinstance(timestamp, (int, float))
                or not 0 <= timestamp <= 253402300799 or not math.isfinite(timestamp)):
            raise ValueError("Failure timestamp must be finite Unix seconds")
        source_line = event.get("source_line")
        if source_line is not None and (type(source_line) is not int or not 1 <= source_line <= 10_000_000):
            raise ValueError("Failure line must be a positive integer")
        if screenshot is not None and (not isinstance(screenshot, ScreenshotEvidence) or screenshot.serial != serial):
            raise ValueError("Failure screenshot must identify the failed device")
        record_id = uuid4().hex
        values = (record_id, float(timestamp), run_id, serial,
                  _text(event.get("error_type", "Unknown"), "error_type", 200),
                  _text(failure.get("category", "python"), "category", 100),
                  _text(event.get("message", ""), "message", 4000),
                  _text(event.get("source_path", event.get("script_id", "")), "source_path", 4096),
                  source_line, _text(event.get("traceback", ""), "traceback", 16000),
                  _text(failure.get("advice", "Inspect the failure before explicitly restarting."), "advice", 4000),
                  screenshot.png if screenshot else None,
                  screenshot.size[0] if screenshot else None,
                  screenshot.size[1] if screenshot else None)
        with closing(self._connect()) as connection, connection:
            connection.execute("INSERT OR IGNORE INTO failures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", values)
            existing = connection.execute(
                "SELECT id FROM failures WHERE run_id=? AND error_type=? AND source_path=? AND source_line IS ? AND message=?",
                (values[2], values[4], values[7], values[8], values[6])).fetchone()
            # An event loop may deliver the same error twice. Update only absent
            # evidence, so late capture cannot replace the original screenshot.
            if existing is not None:
                record_id = existing["id"]
                if screenshot is not None:
                    connection.execute("UPDATE failures SET screenshot=?,width=?,height=? WHERE id=? AND screenshot IS NULL",
                                       (screenshot.png, screenshot.size[0], screenshot.size[1], record_id))
            connection.execute("DELETE FROM failures WHERE id NOT IN (SELECT id FROM failures ORDER BY created DESC,rowid DESC LIMIT ?)",
                               (self.retention,))
            total = connection.execute("SELECT COALESCE(SUM(length(screenshot)),0) FROM failures").fetchone()[0]
            if total > MAX_STORED_SCREENSHOTS:
                for row in connection.execute("SELECT id,length(screenshot) AS bytes FROM failures WHERE screenshot IS NOT NULL ORDER BY created,rowid").fetchall():
                    connection.execute("UPDATE failures SET screenshot=NULL,width=NULL,height=NULL WHERE id=?", (row["id"],))
                    total -= row["bytes"]
                    if total <= MAX_STORED_SCREENSHOTS:
                        break
        return record_id

    def recent(self, *, limit=100):
        if type(limit) is not int or not 1 <= limit <= 500:
            raise ValueError("limit must be an integer from 1 to 500")
        with closing(self._connect()) as connection:
            rows = connection.execute("""SELECT id,created,run_id,serial,error_type,category,
                message,source_path,source_line,advice,(screenshot IS NOT NULL) AS has_screenshot
                FROM failures ORDER BY created DESC,rowid DESC LIMIT ?""", (limit,)).fetchall()
            return [dict(row) for row in rows]

    def detail(self, record_id, *, include_screenshot=False):
        if not isinstance(record_id, str) or len(record_id) > 200:
            raise ValueError("Failure record ID must be text")
        with closing(self._connect()) as connection:
            row = connection.execute("SELECT * FROM failures WHERE id=?", (record_id,)).fetchone()
        if row is None:
            return None
        record = dict(row)
        record["has_screenshot"] = record["screenshot"] is not None
        if not include_screenshot:
            record.pop("screenshot")
        return record

    def export_report(self, record_id):
        """JSON diagnostic text without screenshot pixels; no network upload."""
        record = self.detail(record_id)
        if record is None:
            raise ValueError("Failure record no longer exists")
        return json.dumps(record, ensure_ascii=False, indent=2, allow_nan=False)
