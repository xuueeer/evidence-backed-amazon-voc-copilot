from __future__ import annotations

import json
from typing import Any

from .models import ProjectWorkspace, SCHEMA_VERSION


def export_workspace_json(workspace: ProjectWorkspace) -> bytes:
    return json.dumps(
        workspace.as_dict(),
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ).encode("utf-8")


def import_workspace_json(data: bytes | str | dict[str, Any]) -> ProjectWorkspace:
    if isinstance(data, bytes):
        payload = json.loads(data.decode("utf-8"))
    elif isinstance(data, str):
        payload = json.loads(data)
    else:
        payload = data

    if not isinstance(payload, dict):
        raise ValueError("Workspace JSON must contain an object.")

    schema_version = str(payload.get("schema_version") or "")
    if schema_version and schema_version != SCHEMA_VERSION:
        raise ValueError(f"Unsupported workspace schema version: {schema_version}")

    return ProjectWorkspace.from_dict(payload)
