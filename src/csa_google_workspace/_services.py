"""Lazily builds the four Google API clients. Opening a Sheet never builds the Docs client."""
from googleapiclient.discovery import build as _default_build

_SPECS = {"drive": "v3", "docs": "v1", "sheets": "v4", "slides": "v1"}


class ServiceRegistry:
    def __init__(self, credentials, builder=_default_build):
        self._credentials = credentials
        self._builder = builder
        self._cache: dict[str, object] = {}

    def _get(self, name: str):
        if name not in self._cache:
            self._cache[name] = self._builder(name, _SPECS[name], credentials=self._credentials)
        return self._cache[name]

    @property
    def drive(self):
        return self._get("drive")

    @property
    def docs(self):
        return self._get("docs")

    @property
    def sheets(self):
        return self._get("sheets")

    @property
    def slides(self):
        return self._get("slides")
