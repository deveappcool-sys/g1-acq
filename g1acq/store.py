"""Tiny key/value store with ``$persistentStore`` semantics.

Shadowrocket's ``$persistentStore`` keeps opaque strings and returns ``None``
(or ``False`` on write) instead of raising.  Keeping that contract makes the
collection and report logic a line-for-line port and lets the tests use an
in-memory map instead of a real file.
"""

from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Mapping, Protocol, runtime_checkable


@runtime_checkable
class Store(Protocol):
    def read(self, key: str) -> str | None: ...

    def write(self, value: str, key: str) -> bool: ...


class MemoryStore:
    """In-memory store used by the tests and by ``python -m g1acq``."""

    def __init__(self, data: Mapping[str, str] | None = None) -> None:
        self._data: dict[str, str] = dict(data or {})

    def read(self, key: str) -> str | None:
        return self._data.get(key)

    def write(self, value: str, key: str) -> bool:
        self._data[key] = value
        return True

    def as_dict(self) -> dict[str, str]:
        return dict(self._data)


class FileStore:
    """Single JSON document holding ``key -> raw string`` pairs.

    Writes go through a temporary file in the same directory followed by
    ``os.replace``, so a crash mid-write cannot truncate the history.  A
    process-wide lock keeps concurrent worker threads from interleaving.
    """

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self.path = Path(path).expanduser()
        self._lock = threading.Lock()

    # -- helpers ---------------------------------------------------------
    def _load(self) -> dict[str, str]:
        try:
            raw = self.path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return {}
        except OSError:
            return {}
        try:
            data = json.loads(raw)
        except (ValueError, TypeError):
            # A corrupt state file must not break traffic; start clean.
            return {}
        if not isinstance(data, dict):
            return {}
        return {str(key): str(value) for key, value in data.items()}

    def _save(self, data: dict[str, str]) -> bool:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            fd, tmp = tempfile.mkstemp(
                dir=str(self.path.parent), prefix=self.path.name + ".", suffix=".tmp"
            )
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    handle.write(payload)
                    handle.flush()
                    os.fsync(handle.fileno())
                os.replace(tmp, self.path)
            except BaseException:
                try:
                    os.unlink(tmp)
                except OSError:
                    pass
                raise
            return True
        except OSError:
            return False

    # -- Store protocol --------------------------------------------------
    def read(self, key: str) -> str | None:
        with self._lock:
            return self._load().get(key)

    def write(self, value: str, key: str) -> bool:
        with self._lock:
            data = self._load()
            data[str(key)] = str(value)
            return self._save(data)


def load_json(store: Store, key: str) -> dict:
    """Read ``key`` and return the parsed object when it matches the schema."""
    try:
        value = store.read(key)
        parsed = json.loads(value or "{}")
    except Exception:
        return {}
    if not isinstance(parsed, dict):
        return {}
    schema = parsed.get("schemaVersion")
    # ``true`` and ``"1"`` must not pass, exactly as the original strict check.
    if isinstance(schema, bool) or not isinstance(schema, int) or schema != 1:
        return {}
    return parsed
