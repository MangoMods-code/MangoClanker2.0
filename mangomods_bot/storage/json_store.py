from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any, Dict

class JSONStore:
    """
    Small async-safe JSON store with atomic writes.
    """
    def __init__(self, path: str, default: Dict[str, Any]) -> None:
        self.path = Path(path)
        self.default = default
        self._lock = asyncio.Lock()

        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_sync(self.default)

    def _write_sync(self, data: Dict[str, Any]) -> None:
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)

    async def read(self) -> Dict[str, Any]:
        async with self._lock:
            try:
                raw = self.path.read_text(encoding="utf-8")
                data = json.loads(raw)
                if not isinstance(data, dict):
                    return dict(self.default)
                return data
            except Exception:
                return dict(self.default)

    async def write(self, data: Dict[str, Any]) -> None:
        async with self._lock:
            self._write_sync(data)
