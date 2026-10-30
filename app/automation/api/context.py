"""Imported short functions resolve a context-local Device, never a global serial."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import signature
from typing import Iterator, get_type_hints

from app.automation.api.device import API_METHOD_NAMES, Device
from app.automation.api.errors import NoExecutionContext

_current: ContextVar[Device | None] = ContextVar("automation_device", default=None)


def get_current_device() -> Device:
    device = _current.get()
    if device is None:
        raise NoExecutionContext("Run this API inside an assigned automation context")
    return device


@contextmanager
def use_device(device: Device) -> Iterator[Device]:
    """Bind one Device for imported short functions; restore nested context on exit."""
    if not isinstance(device, Device):
        raise TypeError("use_device requires a Device")
    token = _current.set(device)
    try:
        yield device
    finally:
        _current.reset(token)


def _short_function(name):
    method = getattr(Device, name)

    @wraps(method)
    def function(*args, **kwargs):
        return getattr(get_current_device(), name)(*args, **kwargs)

    # functools.wraps normally exposes the unbound Device method's signature,
    # including ``self``. The public short function has no device parameter.
    # Resolve annotations in the original method's globals before installing
    # them on a wrapper whose globals belong to this context module instead.
    hints = get_type_hints(method)
    parameters = [parameter.replace(annotation=hints.get(parameter.name, parameter.annotation))
                  for parameter in signature(method).parameters.values()
                  if parameter.name != "self"]
    result_type = hints.get("return", signature(method).return_annotation)
    function.__signature__ = signature(method).replace(
        parameters=parameters,
        return_annotation=None if result_type is type(None) else result_type,
    )
    function.__annotations__ = {key: value for key, value in hints.items() if key != "self"}
    function.__qualname__ = name
    return function


for _name in API_METHOD_NAMES:
    globals()[_name] = _short_function(_name)
