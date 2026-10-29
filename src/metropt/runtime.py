"""Runtime configuration shared by local and hosted application runs."""

from __future__ import annotations

import os
from collections.abc import Mapping, MutableMapping
from typing import Any


SECRET_ENV_KEYS = ("DATABASE_URL", "METROPT_DEMO_MODE")
TRUE_VALUES = {"1", "true", "yes", "on"}


def apply_secret_environment(
    secrets: Mapping[str, Any],
    environ: MutableMapping[str, str] | None = None,
) -> None:
    target = os.environ if environ is None else environ
    for key in SECRET_ENV_KEYS:
        if key in target:
            continue
        value = secrets.get(key)
        if value is not None:
            target[key] = str(value)


def is_demo_mode(value: str | None) -> bool:
    if value is None:
        return False
    return value.strip().lower() in TRUE_VALUES


def demo_mode_from_environment() -> bool:
    return is_demo_mode(os.getenv("METROPT_DEMO_MODE"))
