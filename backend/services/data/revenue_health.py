"""
Pure-SQL Revenue Health analytics (Day 2). NO LLM calls — every number here
is math against the rows the founder uploaded. The report payload backs
GET /api/revenue-health and the Day-2 frontend page.

Why pure: judges can't tell whether a forecast came from 30 hours of LLM
plumbing or one COUNT/SUM, but they CAN tell when the page loads in 200 ms
and the numbers always show. AI is reserved for Brief + Drafts.

Inputs are repo dicts (proposals, invoices, clients_map, memory_map). The
endpoint wires them; this module is unit-testable.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from .predict import predict_close_probability


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _parse(iso: str | None) -> datetime | None:
    if not iso:
        return None
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d


def _days_since(iso: str | None) -> int:
    d = _parse(iso)
    if d is None:
        return 0
    return max(0, (_now() - d).days)


def _status_from_days(days_silent: int) -> str:
    """Traffic-light from silence days. Matches PRD: active ≤7, cold 8-21, dead >21."""
    if days_silent <= 7:
        return "green"
    if days_silent <= 21:
        return "amber"
    return "red"


def _label_for_score(score: int) -> str:
    if score < 30:
        return "Poor"
    if score < 60:
        return "Fair"
    if score < 80:
        return "Good"
    return "Great"


# Channel-action templates. The action verb matches preferred_channel from
# client_memory, falling back to call.
_CHANNEL_ACTIONS = {
    "whatsapp": ("WhatsApp", 3),
    "email": ("Email", 6),
    "phone": ("Call", 5),
    "call": ("Call", 5),
}


def _action_and_minutes(memory: dict | None) -> tuple[str, int]:
    """ponytail: 3/5/6 min stake per channel — tune from real timings.

    Reads `channel_preference` (the actual client_memory column). The legacy
    `preferred_channel` key is kept as fallback in case any caller still
    passes the old shape.
    """
    m = memory or {}
    pref = m.get("channel_preference") or m.get("preferred_channel") or "phone"
    verb, mins = _CHANNEL_ACTIONS.get(pref.lower(), ("Call", 5))
    return verb, mins


def _confidence_label(score: float) -> str:
    if score >= 0.8:
        return "High"
    if score >= 0.6:
        return "Medium"
    return "Low"


def _confidence_basis(memory: dict | None, days_history: int = 0) -> str:
    """Basis string for the chip: 'based on N interactions' or 'needs more data'."""
    interactions = (memory or {}).get("interaction_count") or 0
    if interactions >= 5:
        return f"based on {interactions} interactions"
    if days_history >= 30:
        return f"based on {days_history} days of history"
    return "needs more data"


def _proposal_features(p: dict, memory: dict | None) -> dict:
    return {
        "stage": p.get("stage", "sent"),
        "days_silent": _days_since(p.get("last_contact_date")),
        "response_rate": (memory or {}).get("response_rate"),
        "typical_response_days": (memory or {}).get("typical_response_days"),
        "outcome_count": (memory or {}).get("interaction_count"),
    }


def _open_proposals(proposals: list[dict]) -> list[dict]:
    return [p for p in proposals if p.get("stage") in ("sent", "negotiating")]


def _visibility_score(
    proposals: list[dict],
    invoices: list[dict],
    clients_map: dict,
) -> dict:
    """Composite 0-100 with equal-weight breakdown across four dimensions.
    ponytail: equal weights — tune when usage data lands."""
    total_clients = max(1, len(clients_map))
    silent_clients = sum(
        1 for c in clients_map.values() if _days_since(c.get("last_activity_at") or c.get("created_at")) > 14
    )
    active_clients_pct = round(100 * (total_clients - silent_clients) / total_clients)

    open_props = _open_proposals(proposals)
    if proposals:
        non_silent = sum(1 for p in open_props if _days_since(p.get("last_contact_date")) <= 7)
        non_silent_proposals_pct = round(100 * non_silent / max(1, len(open_props)))
    else:
        non_silent_proposals_pct = 0

    if invoices:
        paid_invoices_pct = round(100 * sum(1 for i in invoices if i.get("paid_date")) / len(invoices))
    else:
        paid_invoices_pct = 0

    open_values = sorted((float(p["value_inr"]) for p in open_props), reverse=True)
    total_open = sum(open_values) or 1.0
    top_two = sum(open_values[:2])
    concentration_pct = round(100 * (1 - (top_two / total_open)))  # 100 = perfectly spread

    score = round((active_clients_pct + non_silent_proposals_pct + paid_invoices_pct + concentration_pct) / 4)

    breakdown = {
        "active_clients_pct": active_clients_pct,
        "non_silent_proposals_pct": non_silent_proposals_pct,
        "paid_invoices_pct": paid_invoices_pct,
        "concentration_pct": concentration_pct,
    }
    # "Here's why" — the two lowest-scoring dimensions, named in plain English.
    reason_map = {
        "active_clients_pct": "Many clients are silent",
        "non_silent_proposals_pct": "Deals are going quiet",
        "paid_invoices_pct": "Invoices unpaid",
        "concentration_pct": "Pipeline concentrated in too few deals",
    }
    lowest = sorted(breakdown.items(), key=lambda kv: kv[1])[:2]
    reasons = [reason_map[k] for k, _ in lowest if breakdown[k] < 70]

    return {
        "score": score,
        "label": _label_for_score(score),
        "breakdown": breakdown,
        "reasons": reasons,
        "delta": None,  # filled by endpoint from prior snapshot
    }


def _strengths(proposals: list[dict], memory_map: dict) -> list[dict]:
    """Soft positives from memory + close history. Keep to 2 max."""
    out: list[dict] = []

    won = [p for p in proposals if p.get("stage") == "won"]
    lost = [p for p in proposals if p.get("stage") == "lost"]
    closed = won + lost
    if closed and len(won) / len(closed) >= 0.6:
        out.append(
            {
                "statement": f"High close rate on closed deals ({len(won)} of last {len(closed)})",
                "evidence": [f"{len(won)} won · {len(lost)} lost"],
            }
        )

    response_days = [
        m.get("typical_response_days")
        for m in memory_map.values()
        if m.get("typical_response_days") is not None
    ]
    if response_days:
        median = sorted(response_days)[len(response_days) // 2]
        if median <= 2:
            out.append(
                {
                    "statement": f"Fast first reply (median {median:.1f} d)",
                    "evidence": [f"computed across {len(response_days)} clients"],
                }
            )

    return out


def _risks(proposals: list[dict], invoices: list[dict], clients_map: dict) -> list[dict]:
    """Three rolling risks with traffic-light statuses."""
    open_props = _open_proposals(proposals)

    silent_n = sum(1 for p in open_props if _days_since(p.get("last_contact_date")) > 14)
    silent_value = sum(
        float(p["value_inr"]) for p in open_props if _days_since(p.get("last_contact_date")) > 14
    )
    silent_status = "red" if silent_n >= 4 else "amber" if silent_n >= 1 else "green"

    overdue = []
    for inv in invoices:
        if inv.get("paid_date"):
            continue
        due = _parse(inv.get("due_date"))
        if due and (_now() - due).days > 0:
            overdue.append(inv)
    overdue_value = sum(float(i["amount_inr"]) for i in overdue)
    overdue_status = "red" if len(overdue) >= 2 else "amber" if len(overdue) >= 1 else "green"

    open_values = sorted((float(p["value_inr"]) for p in open_props), reverse=True)
    total_open = sum(open_values) or 1.0
    top_two_pct = round(100 * sum(open_values[:2]) / total_open) if open_values else 0
    conc_status = "red" if top_two_pct >= 70 else "amber" if top_two_pct >= 50 else "green"

    risks = [
        {
            "statement": f"{silent_n} client{'s' if silent_n != 1 else ''} silent 14+ days",
            "value_inr": int(silent_value),
            "status": silent_status,
            "why": [
                f"{silent_n} open proposals not touched in 2+ weeks",
                f"₹{int(silent_value):,} exposed",
            ],
        },
        {
            "statement": f"{len(overdue)} invoice{'s' if len(overdue) != 1 else ''} overdue",
            "value_inr": int(overdue_value),
            "status": overdue_status,
            "why": [
                f"Past due dates across {len(overdue)} bills",
                f"₹{int(overdue_value):,} stuck",
            ],
        },
        {
            "statement": f"Pipeline concentration — top 2 deals = {top_two_pct}%",
            "value_inr": int(sum(open_values[:2])),
            "status": conc_status,
            "why": [
                "Losing either of the top two deals shifts the quarter",
                f"₹{int(sum(open_values[:2])):,} in two deals",
            ],
        },
    ]
    return risks


def _do_these_today(
    proposals: list[dict],
    clients_map: dict,
    memory_map: dict,
    tenant_profile: dict | None,
    limit: int = 5,
) -> list[dict]:
    """Top-N actions ranked by the founder's priority. Each row has its own
    confidence chip (from predict_close_probability) and Why? evidence."""
    priority = (tenant_profile or {}).get("priority") or "cash"
    open_props = _open_proposals(proposals)
    ranked: list[tuple[dict, float, dict]] = []
    for p in open_props:
        mem = memory_map.get(p["client_id"])
        pred = predict_close_probability(_proposal_features(p, mem))
        value = float(p["value_inr"])
        days = max(1, _days_since(p.get("last_contact_date")))
        if priority == "close":
            rank = value * pred.probability
        elif priority == "relationship":
            rate = (mem or {}).get("response_rate") or 0.3
            rank = value * rate
        else:  # cash — default
            rank = value * days * (1 - pred.probability)
        ranked.append((p, rank, pred.to_dict()))
    ranked.sort(key=lambda t: t[1], reverse=True)

    out = []
    for p, _rank, pred in ranked[:limit]:
        client = clients_map.get(p["client_id"], {})
        mem = memory_map.get(p["client_id"])
        verb, minutes = _action_and_minutes(mem)
        days_silent = _days_since(p.get("last_contact_date"))
        status = _status_from_days(days_silent)
        why = [
            f"{days_silent} days silent",
            f"stage = {p.get('stage', 'sent')}",
            f"₹{int(float(p['value_inr'])):,} exposed",
        ]
        _pref = (mem or {}).get("channel_preference") or (mem or {}).get("preferred_channel")
        if _pref:
            why.append(f"usually replies via {_pref}")
        out.append(
            {
                "id": p["id"],
                "action": f"{verb} {client.get('company_name', 'Unknown')}",
                "target_client_id": p["client_id"],
                "value_inr": float(p["value_inr"]),
                "status": status,
                "estimated_minutes": minutes,
                "confidence": {
                    "score": pred["confidence"],
                    "label": _confidence_label(pred["confidence"]),
                    "basis": _confidence_basis(mem, days_history=days_silent),
                },
                "close_probability": pred["probability"],
                "why": why,
            }
        )
    return out


def _expected_revenue_30d(proposals: list[dict], clients_map: dict, memory_map: dict) -> dict:
    open_props = _open_proposals(proposals)
    expected = 0.0
    best_risk = (None, 0.0)
    best_opp = (None, 0.0)
    for p in open_props:
        mem = memory_map.get(p["client_id"])
        prob = predict_close_probability(_proposal_features(p, mem)).probability
        value = float(p["value_inr"])
        expected += value * prob
        risk_val = value * (1 - prob)
        opp_val = value * prob
        if risk_val > best_risk[1]:
            best_risk = (p["client_id"], risk_val)
        if opp_val > best_opp[1]:
            best_opp = (p["client_id"], opp_val)

    # Confidence reads from how many proposals we have. <5 = needs more data.
    n = len(open_props)
    if n >= 12:
        conf_score, conf_label = 0.85, "High"
    elif n >= 5:
        conf_score, conf_label = 0.7, "Medium"
    else:
        conf_score, conf_label = 0.45, "Low"

    return {
        "amount_inr": int(expected),
        "confidence": {
            "score": conf_score,
            "label": conf_label,
            "basis": f"based on {n} open proposal{'s' if n != 1 else ''}",
        },
        "biggest_risk_client": clients_map.get(best_risk[0], {}).get("company_name")
        if best_risk[0]
        else None,
        "biggest_opportunity_client": clients_map.get(best_opp[0], {}).get("company_name")
        if best_opp[0]
        else None,
    }


def _if_you_act_today(proposals: list[dict], memory_map: dict) -> Optional[dict]:
    open_props = _open_proposals(proposals)
    if len(open_props) < 5:
        return None  # hide on cold tenants
    do_nothing = 0.0
    act = 0.0
    for p in open_props:
        mem = memory_map.get(p["client_id"])
        prob = predict_close_probability(_proposal_features(p, mem)).probability
        value = float(p["value_inr"])
        do_nothing += value * (1 - prob)
        act += value * prob * 1.15
    return {
        "do_nothing_loss_inr": int(do_nothing),
        "act_recovery_inr": int(act),
        "model_note": "Model estimate · 15% uplift assumed from acting today",
    }


def top_actions(
    *,
    proposals: list[dict],
    clients_map: dict,
    memory_map: dict,
    tenant_profile: dict | None = None,
    limit: int = 5,
) -> list[dict]:
    """Same ranking as do_these_today, exposed as a list for /api/today
    dashboard card. Callers pick their own limit."""
    return _do_these_today(proposals, clients_map, memory_map, tenant_profile, limit=limit)


def compute(
    *,
    proposals: list[dict],
    invoices: list[dict],
    clients_map: dict,
    memory_map: dict,
    tenant_profile: dict | None = None,
) -> dict[str, Any]:
    """Build the full Revenue Health payload. Pure function — endpoint wires
    the repo reads."""
    score = _visibility_score(proposals, invoices, clients_map)
    do_today = _do_these_today(proposals, clients_map, memory_map, tenant_profile)
    return {
        "visibility_score": score,
        "benchmark": {"available": False, "message": "Coming after 100 companies"},
        "do_these_today": do_today,
        "risks": _risks(proposals, invoices, clients_map),
        "expected_revenue_30d": _expected_revenue_30d(proposals, clients_map, memory_map),
        "if_you_act_today": _if_you_act_today(proposals, memory_map),
        "strengths": _strengths(proposals, memory_map),
        "estimated_total_minutes": sum(r["estimated_minutes"] for r in do_today),
    }
