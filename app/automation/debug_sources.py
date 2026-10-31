"""Bounded, inert project source snapshots for trusted debug runs.

This is a debugging consistency boundary, not a Python security sandbox. Imports
outside the captured project, native extensions and user-installed import hooks
retain ordinary trusted Python behavior.
"""
from contextlib import contextmanager
import importlib.abc
import importlib.machinery
import importlib.util
import linecache
import io
import os
from pathlib import Path
import sys
import tokenize

MAX_FILES = 200
MAX_FILE_BYTES = 1_000_000
MAX_TOTAL_BYTES = 8_000_000
EXCLUDED = {'.git', '.venv', '.tools', '__pycache__', 'vendor', 'node_modules', 'build', 'dist'}


def validate_sources(sources, root, script_id, source):
    if not isinstance(sources, dict) or len(sources) > MAX_FILES:
        raise ValueError('Debug sources require at most 200 source files')
    if sources.get(script_id) != source:
        raise ValueError('Debug sources must include the exact approved main script')
    root = Path(root).resolve(strict=True)
    output = {}
    total = 0
    for name, text in sources.items():
        if not isinstance(name, str) or len(name) > 1024 or not isinstance(text, str):
            raise ValueError('Debug source paths/text are invalid')
        size = len(text.encode('utf-8'))
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES:
            raise ValueError('Debug sources exceed the supported size')
        if name == script_id:
            if text != source:
                raise ValueError('Main debug source must match the approved source')
            output[name] = text
            continue
        path = Path(name)
        if (not path.is_absolute() or path.suffix != '.py' or path.is_symlink()
                or not path.resolve().is_relative_to(root)):
            raise ValueError('Debug sources must be contained project Python files')
        canonical = str(path.resolve())
        if canonical in output:
            raise ValueError('Duplicate canonical debug source')
        output[canonical] = text
    output[script_id] = source
    return output


def snapshot_sources(project_root, script_id, source):
    """Read source without importing/compiling it; reject oversized snapshots."""
    root = Path(project_root).resolve(strict=True)
    sources = {script_id: source}
    entries = 0
    for index, (directory, folders, files) in enumerate(os.walk(root, followlinks=False)):
        entries += len(folders) + len(files)
        if index >= 2000 or entries > 10000:
            raise ValueError('Project traversal exceeds debug snapshot limits; choose a smaller project root')
        folders[:] = sorted(name for name in folders if name not in EXCLUDED
                            and not name.startswith('.') and not (Path(directory) / name).is_symlink())
        for name in sorted(files):
            path = Path(directory) / name
            if path.suffix != '.py' or path.is_symlink():
                continue
            canonical = str(path.resolve())
            if canonical == script_id:
                continue
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError('A project Python source exceeds the debug snapshot size limit')
            with path.open('rb') as stream:
                data = stream.read(MAX_FILE_BYTES + 1)
            if len(data) > MAX_FILE_BYTES:
                raise ValueError('A project Python source exceeds the debug snapshot size limit')
            encoding, _ = tokenize.detect_encoding(io.BytesIO(data).readline)
            sources[canonical] = data.decode(encoding).replace('\r\n', '\n').replace('\r', '\n')
            if len(sources) > MAX_FILES:
                raise ValueError('Project exceeds 200 debug sources; choose a smaller project root')
    return validate_sources(sources, root, script_id, source)


class _Loader(importlib.machinery.SourceFileLoader):
    def __init__(self, fullname, path, source):
        super().__init__(fullname, path)
        self.source = source

    def get_code(self, fullname):
        return compile(self.source, self.path, 'exec')

    def get_source(self, fullname):
        return self.source


class _Finder(importlib.abc.MetaPathFinder):
    def __init__(self, sources):
        self.sources = {os.path.normcase(path): (path, source) for path, source in sources.items()
                        if not path.startswith('<')}

    def find_spec(self, fullname, path=None, target=None):
        # Resolve approved source candidates even if the on-disk Python file
        # was edited or removed after approval. Normal import path order stays
        # intact; uncaptured/native modules use Python's ordinary machinery.
        name = fullname.rsplit('.', 1)[-1]
        for directory in path if path is not None else sys.path:
            spec = importlib.machinery.PathFinder.find_spec(fullname, [directory], target)
            if spec is not None and spec.origin:
                item = self.sources.get(os.path.normcase(str(Path(spec.origin).resolve())))
                if item is None:
                    return None
                filename, source = item
                return importlib.util.spec_from_file_location(fullname, filename,
                    loader=_Loader(fullname, filename, source),
                    submodule_search_locations=list(spec.submodule_search_locations)
                        if spec.submodule_search_locations is not None else None)
            for candidate, package in ((Path(directory) / name / '__init__.py', True),
                                       (Path(directory) / (name + '.py'), False)):
                item = self.sources.get(os.path.normcase(str(candidate.resolve())))
                if item is not None:
                    filename, source = item
                    return importlib.util.spec_from_file_location(fullname, filename,
                        loader=_Loader(fullname, filename, source),
                        submodule_search_locations=[str(Path(filename).parent)] if package else None)
        spec = importlib.machinery.PathFinder.find_spec(fullname, path, target)
        if spec is None or not spec.origin:
            return None
        item = self.sources.get(os.path.normcase(str(Path(spec.origin).resolve())))
        if item is None:
            return None
        filename, source = item
        return importlib.util.spec_from_file_location(fullname, filename, loader=_Loader(fullname, filename, source),
            submodule_search_locations=list(spec.submodule_search_locations)
                if spec.submodule_search_locations is not None else None)


@contextmanager
def imported_sources(sources, *, keep_cache=False):
    """Freeze captured module imports in this worker and restore tracing caches."""
    finder = _Finder(sources)
    missing = object()
    previous = {path: linecache.cache.get(path, missing) for path in sources}
    for path, source in sources.items():
        linecache.cache[path] = (len(source), None, source.splitlines(keepends=True), path)
    sys.meta_path.insert(0, finder)
    try:
        yield
    finally:
        if finder in sys.meta_path:
            sys.meta_path.remove(finder)
        for path, old in (() if keep_cache else previous.items()):
            if old is missing:
                linecache.cache.pop(path, None)
            else:
                linecache.cache[path] = old
