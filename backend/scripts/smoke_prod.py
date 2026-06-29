"""Production smoke test — exercises the demo path end-to-end against any URL.

Usage:
    python -m scripts.smoke_prod --backend https://revora-backend.onrender.com
    python -m scripts.smoke_prod  # defaults to localhost:8765

What it does (in order, with fresh per-run tenants):
  1. signup -> token
  2. /onboarding/state shows fresh tenant
  3. /import/seed-demo populates
  4. /revenue-health renders, snapshot written
  5. /today returns ranked rows
  6. /brief/today returns LLM or template_fallback
  7. /recommendations/{id}/feedback writes an event
  8. /learning/aggregate counts it
  9. /impact returns honest zeros (no real follow-ups yet)
 10. /admin/audit-log/verify returns ok=True (requires admin creds)

Exit 0 = green, 1 = any failure. Suitable for CI / cron / Render's
deploy-hook smoke check.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

import requests


def _step(name: str, ok: bool, body=None) -> None:
    mark = "✓" if ok else "✗"
    print(f"  {mark} {name}", f"-> {body}" if body else "")
    if not ok:
        sys.exit(1)


def run(backend: str, admin_email: str | None, admin_password: str | None) -> None:
    api = f"{backend.rstrip('/')}/api"
    print(f"\nSmoke against: {api}")

    # Wait briefly for cold-start (Render free spins down after 15 min idle)
    for attempt in range(6):
        try:
            r = requests.get(f"{api}/", timeout=20)
            if r.status_code == 200:
                break
        except requests.RequestException:
            pass
        print(f"  ...waiting for backend (attempt {attempt + 1})")
        time.sleep(5)
    else:
        _step("backend reachable", False, "timed out waiting for /api/")

    _step("backend reachable", True, r.json())

    # Fresh tenant per run
    email = f"smoke_{int(datetime.now().timestamp())}@x.com"
    r = requests.post(
        f"{api}/auth/register", json={"email": email, "password": "Pw1234!!XYz", "name": "Smoke"}, timeout=20
    )
    _step("signup", r.status_code == 200, r.json().get("user", {}).get("id"))
    h = {"Authorization": f"Bearer {r.json()['token']}"}

    r = requests.get(f"{api}/onboarding/state", headers=h, timeout=15).json()
    _step("fresh onboarding state", r["has_data"] is False)

    # ponytail: seed_demo_for_owner does ~60 sequential inserts; from a remote
    # laptop to AWS Neon this takes ~150 s. Render→Neon (same cloud) is <10 s.
    r = requests.post(f"{api}/import/seed-demo", headers=h, timeout=240).json()
    _step("seed-demo", r.get("clients", 0) > 0, r)

    r = requests.get(f"{api}/revenue-health", headers=h, timeout=30).json()
    _step("revenue-health renders", isinstance(r.get("visibility_score", {}).get("score"), int))
    _step("do_these_today rows", len(r.get("do_these_today", [])) >= 1)

    r = requests.get(f"{api}/today?limit=3", headers=h, timeout=15).json()
    _step("/today returns rows", len(r.get("rows", [])) >= 1)

    b = requests.get(f"{api}/brief/today", headers=h, timeout=90).json()
    _step(f"brief.source={b.get('source')}", b.get("source") in ("llm", "template_fallback"))
    _step("brief has paragraph", bool((b.get("brief") or {}).get("paragraph")))

    ids = [row["id"] for row in r["rows"]]
    fb = requests.post(
        f"{api}/recommendations/{ids[0]}/feedback", headers=h, json={"thumb": "up"}, timeout=15
    )
    _step("feedback up", fb.status_code == 200)

    agg = requests.get(f"{api}/learning/aggregate", headers=h, timeout=15).json()
    _step(f"aggregate up={agg['thumbs_up_count']}", agg["thumbs_up_count"] >= 1)

    imp = requests.get(f"{api}/impact", headers=h, timeout=15).json()
    _step(
        "impact returns shape",
        all(
            k in imp
            for k in (
                "followups_generated_week",
                "hours_saved_week",
                "revenue_protected_week",
                "response_rate_week",
            )
        ),
    )

    if admin_email and admin_password:
        admin = requests.post(
            f"{api}/auth/login", json={"email": admin_email, "password": admin_password}, timeout=20
        )
        if admin.status_code == 200:
            ah = {"Authorization": f"Bearer {admin.json()['token']}"}
            v = requests.get(f"{api}/admin/audit-log/verify", headers=ah, timeout=30).json()
            _step(f"audit chain verify (n={v.get('records_checked')})", v.get("ok") is True)
        else:
            _step("admin login (skipping audit verify)", False, admin.text)
    else:
        print("  ⤿ skip audit verify (no admin creds)")

    print("\n=== SMOKE: GREEN ===")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=os.environ.get("BACKEND_URL", "http://127.0.0.1:8765"))
    ap.add_argument("--admin-email", default=os.environ.get("ADMIN_EMAIL"))
    ap.add_argument("--admin-password", default=os.environ.get("ADMIN_PASSWORD"))
    args = ap.parse_args()
    run(args.backend, args.admin_email, args.admin_password)
