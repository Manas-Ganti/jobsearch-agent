"""Generic name → class registry with package auto-discovery.

Every extension point (sources, enrichers/stages, delivery channels) is one of
these. Auto-discovery is what makes "one new file + one decorator + one config
line" true: dropping a module into the package is enough to register it.
"""

from __future__ import annotations

import importlib
import pkgutil
from typing import Any, Callable, Generic, TypeVar

T = TypeVar("T")


class Registry(Generic[T]):
    def __init__(self, kind: str) -> None:
        self.kind = kind
        self._entries: dict[str, type[T]] = {}
        self._discovered: set[str] = set()

    def register(self, name: str) -> Callable[[type[T]], type[T]]:
        def decorator(cls: type[T]) -> type[T]:
            if name in self._entries and self._entries[name] is not cls:
                raise ValueError(f"duplicate {self.kind} {name!r}")
            cls.name = name  # type: ignore[attr-defined]
            self._entries[name] = cls
            return cls

        return decorator

    def discover(self, package: str) -> None:
        """Import every module in `package` so decorators run. Idempotent."""
        if package in self._discovered:
            return
        self._discovered.add(package)
        pkg = importlib.import_module(package)
        for mod in pkgutil.iter_modules(pkg.__path__):
            if not mod.name.startswith("_"):
                importlib.import_module(f"{package}.{mod.name}")

    def get(self, name: str) -> type[T]:
        try:
            return self._entries[name]
        except KeyError:
            known = ", ".join(sorted(self._entries)) or "<none>"
            raise KeyError(f"unknown {self.kind} {name!r}; registered: {known}") from None

    def create(self, name: str, *args: Any, **params: Any) -> T:
        return self.get(name)(*args, **params)  # type: ignore[call-arg]

    def names(self) -> list[str]:
        return sorted(self._entries)

    def __contains__(self, name: object) -> bool:
        return name in self._entries
