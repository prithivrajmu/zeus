"""Use case 1: customer support tickets.

Realistic ticket lifecycle data — customers, agents, priorities, statuses,
timestamps that respect causality (created ≤ first_response ≤ resolved).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Iterator

from zeus.core import BaseGenerator, register

CATEGORIES = ["billing", "login", "bug", "feature_request", "shipping", "refund", "account", "performance"]
PRIORITIES = ["low", "medium", "high", "urgent"]
PRIORITY_WEIGHTS = [0.35, 0.40, 0.18, 0.07]
STATUSES = ["open", "in_progress", "waiting_on_customer", "resolved", "closed"]
STATUS_WEIGHTS = [0.15, 0.20, 0.10, 0.30, 0.25]
CHANNELS = ["email", "chat", "phone", "web_form"]

SUBJECT_TEMPLATES = {
    "billing": ["Charged twice for {m} subscription", "Invoice #{n} doesn't match my plan", "Unexpected charge on my card"],
    "login": ["Can't log in after password reset", "2FA codes not arriving", "Account locked out since {m}"],
    "bug": ["App crashes when exporting reports", "Dashboard shows stale data", "Error 500 on the settings page"],
    "feature_request": ["Please add dark mode", "Need bulk export to CSV", "Request: SSO support for our team"],
    "shipping": ["Order #{n} hasn't arrived", "Wrong item delivered for order #{n}", "Tracking number not working"],
    "refund": ["Requesting refund for order #{n}", "Refund promised but not received", "Cancel and refund my {m} renewal"],
    "account": ["How do I change my email address?", "Delete my account and data", "Transfer ownership of workspace"],
    "performance": ["App extremely slow since last update", "Search takes over 30 seconds", "Timeouts during peak hours"],
}


@register
class SupportTickets(BaseGenerator):
    name = "support_tickets"
    description = "Customer support tickets with agents, priorities, SLAs, and lifecycle timestamps."

    def generate(self) -> Iterator[dict[str, Any]]:
        n_agents = int(self.opt("agents", 8))
        agents = [
            {"id": f"agent-{i+1:03d}", "name": self.faker.name()}
            for i in range(n_agents)
        ]

        for i in range(self.config.count):
            category = self.rng.choice(CATEGORIES)
            priority = self.rng.choices(PRIORITIES, weights=PRIORITY_WEIGHTS)[0]
            status = self.rng.choices(STATUSES, weights=STATUS_WEIGHTS)[0]
            created = self.faker.date_time_between("-180d", "-1d")

            subject = self.rng.choice(SUBJECT_TEMPLATES[category]).format(
                n=self.rng.randint(10000, 99999), m=created.strftime("%B")
            )

            first_response = created + timedelta(minutes=self.rng.randint(5, 720))
            resolved_at = None
            satisfaction = None
            if status in ("resolved", "closed"):
                resolved_at = first_response + timedelta(hours=self.rng.randint(1, 240))
                satisfaction = self.rng.choices([1, 2, 3, 4, 5], weights=[5, 7, 15, 38, 35])[0]

            agent = self.rng.choice(agents) if status != "open" else None

            yield {
                "ticket_id": f"TCK-{i+1:06d}",
                "subject": subject,
                "category": category,
                "priority": priority,
                "status": status,
                "channel": self.rng.choice(CHANNELS),
                "customer_name": self.faker.name(),
                "customer_email": self.faker.email(),
                "assigned_agent_id": agent["id"] if agent else None,
                "assigned_agent_name": agent["name"] if agent else None,
                "created_at": created.isoformat(),
                "first_response_at": first_response.isoformat() if status != "open" else None,
                "resolved_at": resolved_at.isoformat() if resolved_at else None,
                "satisfaction_rating": satisfaction,
                "sla_breached": self.rng.random() < (0.25 if priority in ("high", "urgent") else 0.08),
            }
