"""Core abstractions for zeus generators.

Every use case is a subclass of :class:`BaseGenerator`. A generator declares
a ``name``, optionally a ``description``, and implements ``generate()`` which
yields plain-dict records. Everything else (seeding, output formats, CLI
wiring) is handled by the framework.
"""

from __future__ import annotations

import abc
import random
from dataclasses import dataclass, field
from typing import Any, Iterator

from faker import Faker


@dataclass
class GeneratorConfig:
    """Runtime knobs shared by all generators."""

    count: int = 100
    seed: int | None = None
    locale: str = "en_US"
    # Free-form per-use-case options, passed through from the CLI as key=value.
    options: dict[str, Any] = field(default_factory=dict)


class BaseGenerator(abc.ABC):
    """Contract for a pluggable data generator.

    Subclasses must set ``name`` and implement :meth:`generate`.
    """

    #: Unique registry key, e.g. ``"support_tickets"``.
    name: str = ""
    #: One-line human description shown in ``zeus list``.
    description: str = ""

    def __init__(self, config: GeneratorConfig) -> None:
        if not self.name:
            raise ValueError(f"{type(self).__name__} must define a `name`")
        self.config = config
        self.rng = random.Random(config.seed)
        self.faker = Faker(config.locale)
        if config.seed is not None:
            self.faker.seed_instance(config.seed)

    def generate(self) -> Iterator[dict[str, Any]]:
        """Yield records for single-table use cases.

        Multi-table generators should override :meth:`generate_tables`
        instead and may leave this unimplemented.
        """
        raise NotImplementedError(
            f"{type(self).__name__} implements generate_tables(); "
            "call that instead of generate()."
        )

    def generate_tables(self) -> dict[str, list[dict[str, Any]]]:
        """Return ``{table_name: [records]}``.

        Default wraps :meth:`generate` as a single table named after the
        generator. Raw-source use cases (multiple related tables destined
        for an ETL/ELT pipeline) override this to emit several tables with
        consistent foreign keys.
        """
        return {self.name: list(self.generate())}

    # Convenience -----------------------------------------------------------

    def opt(self, key: str, default: Any = None) -> Any:
        """Read a per-use-case option supplied on the CLI."""
        return self.config.options.get(key, default)
