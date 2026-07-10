"""Example generator — a template for the two real use cases.

Copy this file, rename the class and `name`, define your schema in
`generate()`, and add the import in `generators/__init__.py`.
"""

from __future__ import annotations

from typing import Any, Iterator

from zeus.core import BaseGenerator, register


@register
class ExampleUsers(BaseGenerator):
    name = "example_users"
    description = "Template generator: fake user profiles (replace me)."

    def generate(self) -> Iterator[dict[str, Any]]:
        domain = self.opt("domain", "example.com")
        for i in range(self.config.count):
            first = self.faker.first_name()
            last = self.faker.last_name()
            yield {
                "id": i + 1,
                "name": f"{first} {last}",
                "email": f"{first}.{last}@{domain}".lower(),
                "city": self.faker.city(),
                "signup_date": self.faker.date_between("-2y", "today").isoformat(),
                "plan": self.rng.choice(["free", "pro", "enterprise"]),
            }
