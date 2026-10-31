"""Inert per-file breakpoints; persistence never grants execution trust."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


class BreakpointStore:
    def __init__(self, directory):
        self.directory = Path(directory)

    @staticmethod
    def _identity(path, project):
        project = Path(project).resolve(strict=True)
        path = Path(path).resolve()
        if path.suffix != '.py' or not path.is_relative_to(project):
            raise ValueError('Persistent breakpoints require a contained Python file')
        identity = str(project) + '\n' + path.relative_to(project).as_posix()
        return hashlib.sha256(identity.encode('utf-8')).hexdigest()

    def load(self, path, project, source):
        target = self.directory / (self._identity(path, project) + '.json')
        if not target.exists():
            return None
        if target.is_symlink() or target.stat().st_size > 16384:
            raise ValueError('Invalid breakpoint persistence file')
        record = json.loads(target.read_text(encoding='utf-8'))
        if not isinstance(record, dict) or record.get('version') != 1:
            raise ValueError('Unsupported breakpoint persistence format')
        if record.get('source_hash') != hashlib.sha256(source.encode('utf-8')).hexdigest():
            return []  # Never apply stale line numbers to a changed source.
        from app.automation.debugger import validate_breakpoints
        return validate_breakpoints(record.get('lines'), source)

    def save(self, path, project, source, lines):
        from app.automation.debugger import validate_breakpoints
        lines = validate_breakpoints(lines, source)
        identity = self._identity(path, project)
        self.directory.mkdir(parents=True, exist_ok=True)
        target = self.directory / (identity + '.json')
        if target.is_symlink():
            raise ValueError('Breakpoint persistence target is a symbolic link')
        data = json.dumps({'version': 1, 'source_hash': hashlib.sha256(source.encode('utf-8')).hexdigest(),
                           'lines': lines}, allow_nan=False).encode('utf-8')
        descriptor, temporary = tempfile.mkstemp(prefix='.breakpoints-', dir=self.directory)
        try:
            with os.fdopen(descriptor, 'wb') as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
