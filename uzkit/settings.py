"""Oddiy, ishonchli JSON sozlamalar (atomik yozish bilan)."""
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from .paths import data_dir


class Settings:
    def __init__(self, app_slug: str, filename: str = "settings.json"):
        self.path: Path = data_dir(app_slug) / filename
        self._data: dict = {}
        self.load()

    def load(self) -> None:
        try:
            if self.path.exists():
                self._data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            # Buzilgan faylni zaxiraga olib, toza boshlaymiz
            try:
                self.path.replace(self.path.with_suffix(".broken.json"))
            except Exception:
                pass
            self._data = {}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(dir=str(self.path.parent), suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(self._data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.path)

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def set(self, key: str, value: Any, save: bool = True) -> None:
        self._data[key] = value
        if save:
            self.save()

    def __contains__(self, key: str) -> bool:
        return key in self._data

    @property
    def data(self) -> dict:
        return self._data
