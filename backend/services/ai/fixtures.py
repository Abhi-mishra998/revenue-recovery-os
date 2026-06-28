"""
Sample proposals used by the eval harness. Realistic Indian B2B mix.
Keep this list small and stable — the harness compares prompts/models
*across* these fixtures, so changing fixtures invalidates prior results.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ProposalFixture:
    id: str
    sender_name: str
    recipient_contact: str
    recipient_company: str
    industry: str
    title: str
    value_inr: float
    days_silent: int


FIXTURES: list[ProposalFixture] = [
    ProposalFixture(
        id="cold_low_value",
        sender_name="Rohan",
        recipient_contact="Priya",
        recipient_company="Nexora Retail",
        industry="E-commerce",
        title="Catalog redesign sprint",
        value_inr=180000,
        days_silent=10,
    ),
    ProposalFixture(
        id="cold_mid_value",
        sender_name="Rohan",
        recipient_contact="Kunal",
        recipient_company="FinKart",
        industry="Fintech",
        title="FinKart mobile app v2 - KYC + UPI flows",
        value_inr=620000,
        days_silent=14,
    ),
    ProposalFixture(
        id="dead_high_value",
        sender_name="Rohan",
        recipient_contact="Arjun",
        recipient_company="Hyderabad Heritage Hotels",
        industry="Hospitality",
        title="Hotel booking engine + channel manager",
        value_inr=7500000,  # ₹75L — triggers COMPLEX tier
        days_silent=28,
    ),
    ProposalFixture(
        id="active_recent",
        sender_name="Rohan",
        recipient_contact="Meera",
        recipient_company="Bloom Wellness",
        industry="D2C Wellness",
        title="Bloom CRM customization + WhatsApp integration",
        value_inr=145000,
        days_silent=3,
    ),
]


def by_id(fixture_id: str) -> ProposalFixture:
    for f in FIXTURES:
        if f.id == fixture_id:
            return f
    raise KeyError(fixture_id)
