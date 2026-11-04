"""Runtime data shared between the config entry and its entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .api import CloudApiClient
    from .coordinator import CloudCoordinator


@dataclass
class CloudRuntimeData:
    """Objects associated with a loaded config entry."""

    client: CloudApiClient
    coordinator: CloudCoordinator
    device_metadata: dict[str, str] = field(default_factory=dict)
