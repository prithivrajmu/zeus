"""Registry mapping use-case names to generator classes.

New use cases self-register via the :func:`register` decorator:

    @register
    class MyGenerator(BaseGenerator):
        name = "my_use_case"
        ...
"""

from __future__ import annotations

from typing import Type

from .base import BaseGenerator

_REGISTRY: dict[str, Type[BaseGenerator]] = {}


def register(cls: Type[BaseGenerator]) -> Type[BaseGenerator]:
    if not cls.name:
        raise ValueError(f"{cls.__name__} must define a `name` before registering")
    if cls.name in _REGISTRY:
        raise ValueError(f"Duplicate generator name: {cls.name!r}")
    _REGISTRY[cls.name] = cls
    return cls


def get(name: str) -> Type[BaseGenerator]:
    try:
        return _REGISTRY[name]
    except KeyError:
        available = ", ".join(sorted(_REGISTRY)) or "<none>"
        raise KeyError(f"Unknown generator {name!r}. Available: {available}") from None


def all_generators() -> dict[str, Type[BaseGenerator]]:
    return dict(_REGISTRY)
