"""Editor assistance generated from the actual public automation implementation.

This is an API catalog, not a general Python language server. Importing these
types never loads or executes a user's script.
"""
from __future__ import annotations

import inspect

from app.automation.api import API_METHOD_NAMES, Device, Location, Match, Offset, Pattern, Region, Screen


def _entry(name, value, kind, member_of=None):
    signature = inspect.signature(value)
    parameters = [parameter for parameter in signature.parameters.values() if parameter.name != "self"]
    signature = signature.replace(parameters=parameters)
    # Future annotations appear quoted in inspect output. These labels are
    # display metadata, never code passed to Python or JavaScript evaluation.
    label = name + str(signature).replace("'", "")
    return {"name": name, "signature": label, "documentation": inspect.getdoc(value) or "",
            "parameters": [{"name": p.name, "label": str(p).replace("'", "")} for p in parameters],
            "kind": kind, "member_of": member_of}


def api_catalog() -> list[dict]:
    """Return signatures/docs for functions, constructors and Pattern builders."""
    result = [_entry(name, getattr(Device, name), "function", "device") for name in API_METHOD_NAMES]
    for model in (Pattern, Region, Location, Offset, Match, Screen):
        result.append(_entry(model.__name__, model, "type"))
    for name in ("similar", "targetOffset", "inRegion"):
        result.append(_entry(name, getattr(Pattern, name), "method", "Pattern"))
    return result
