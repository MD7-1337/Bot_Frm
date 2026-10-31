"""Data-only named device groups and ordered workflow definitions."""
from dataclasses import dataclass
from pathlib import Path

from .store import Task


def device_members(values):
    if not isinstance(values, (list, tuple)) or not 1 <= len(values) <= 32:
        raise ValueError('A device group needs 1..32 explicit device identities')
    if any(not isinstance(value, str) or not value or len(value)>256 or '\x00' in value or value.startswith('-') or any(c.isspace() for c in value) for value in values):
        raise ValueError('Invalid explicit device identity')
    if len(set(values)) != len(values):
        raise ValueError('A device group cannot contain duplicate devices')
    return tuple(values)


@dataclass(frozen=True)
class Workflow:
    workflow_id: str
    name: str
    task_ids: tuple[str, ...]
    enabled: bool = True
    schedule: str = 'manual'
    timezone: str = 'UTC'
    at: str | None = None
    interval_seconds: int = 3600
    weekdays: tuple[int, ...] = (0,)
    missed: str = 'skip'

    def validate(self):
        if not isinstance(self.task_ids, (tuple,list)) or not 1 <= len(self.task_ids) <= 100:
            raise ValueError('A workflow needs 1..100 ordered task steps')
        if any(not isinstance(identity,str) or not identity or len(identity)>128 for identity in self.task_ids):
            raise ValueError('Invalid workflow task identity')
        # Reuse schedule validation without persisting or dispatching a synthetic task.
        Task(self.workflow_id,self.name,'pass','workflow-validation',str(Path.cwd().resolve()),
             enabled=self.enabled,schedule=self.schedule,timezone=self.timezone,at=self.at,
             interval_seconds=self.interval_seconds,weekdays=self.weekdays,missed=self.missed).validate()
        return self
