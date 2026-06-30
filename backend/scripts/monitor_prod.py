"""Production health monitor — runs every minute (or on cron / UptimeRobot
HTTP-only checks) and only prints when something regresses.

Default: quiet on success, loud on failure. Suitable for piping into
`alert`, Pushover, or a Discord webhook. Intentionally NOT a noisy
status page — silence is golden, alerts are alerts.

Checks:
  1. /api/ returns 200 in < 30 s (covers Render cold-start)
  2. /api/auth/login with founder creds returns 200
  3. /api/admin/audit-log/verify returns ok=True
  4. /api/brief/today source is 'llm' (not template_fallback —
     Anthropic key issue is the highest-risk regression)

Exit codes:
  0 — all green (silent unless --verbose)
  1 — at least one check failed (prints the failures)
  2 — environment misconfigured (missing creds)

Usage:
  python -m scripts.monitor_prod
  python -m scripts.monitor_prod --verbose
  python -m scripts.monitor_prod --backend https://...onrender.com
  PROD_ADMIN_PASSWORD=xxx python -m scripts.monitor_prod
"""

from __future__ import annotations

import argparse
import os
import sys
import time

import requests

DEFAULT_BACKEND = "https://revora-backend-1in4.onrender.com"
DEFAULT_ADMIN_EMAIL = "founder@bytehubble.com"


def check(backend: str, admin_email: str, admin_password: str, verbose: bool) -> int:
    api = f"{backend.rstrip('/')}/api"
    failures: list[str] = []
    notes: list[str] = []

    # 1. backend reachable (allow cold-start)
    t0 = time.time()
    for attempt in range(6):
        try:
            r = requests.get(f"{api}/", timeout=20)
            if r.status_code == 200:
                notes.append(f"reachable in {time.time() - t0:.1f}s (attempt {attempt + 1})")
                break
        except requests.RequestException as e:
            notes.append(f"transport error attempt {attempt + 1}: {type(e).__name__}")
        time.sleep(5)
    else:
        failures.append("backend not reachable after 6 attempts (cold-start exceeded 30 s)")
        return _report(failures, notes, verbose)

    # 2. admin login
    try:
        r = requests.post(
            f"{api}/auth/login",
            json={"email": admin_email, "password": admin_password},
            timeout=30,
        )
        if r.status_code != 200:
            failures.append(f"admin login {r.status_code}: {r.text[:200]}")
            return _report(failures, notes, verbose)
        token = r.json()["token"]
        h = {"Authorization": f"Bearer {token}"}
        notes.append("admin login ok")
    except requests.RequestException as e:
        failures.append(f"login transport: {e}")
        return _report(failures, notes, verbose)

    # 3. audit chain verifies
    try:
        v = requests.get(f"{api}/admin/audit-log/verify", headers=h, timeout=30).json()
        if not v.get("ok"):
            failures.append(
                f"audit chain broken: ok={v.get('ok')} "
                f"records_checked={v.get('records_checked')} "
                f"issues={(v.get('issues') or [])[:3]}"
            )
        else:
            notes.append(f"audit chain ok (n={v.get('records_checked')})")
    except requests.RequestException as e:
        failures.append(f"audit verify transport: {e}")

    # 4. brief is live LLM (template_fallback = ANTHROPIC_API_KEY regression)
    try:
        br = requests.get(f"{api}/brief/today", headers=h, timeout=120).json()
        src = br.get("source")
        if src == "llm":
            notes.append("brief.source=llm")
        elif src == "template_fallback":
            failures.append(
                "brief.source=template_fallback — LLM call failing. "
                "Most likely: ANTHROPIC_API_KEY missing/wrong on Render, "
                "or anthropic SDK uninstalled. Check Render logs."
            )
        else:
            failures.append(f"brief.source={src!r} (expected 'llm' or 'template_fallback')")
    except requests.RequestException as e:
        failures.append(f"brief transport: {e}")

    return _report(failures, notes, verbose)


def _report(failures: list[str], notes: list[str], verbose: bool) -> int:
    if failures:
        ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        print(f"[{ts}] REVORA PROD: {len(failures)} regression(s)", file=sys.stderr)
        for f in failures:
            print(f"  ✗ {f}", file=sys.stderr)
        if verbose and notes:
            for n in notes:
                print(f"  · {n}", file=sys.stderr)
        return 1
    if verbose:
        ts = time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())
        print(f"[{ts}] revora prod: green")
        for n in notes:
            print(f"  · {n}")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--backend", default=os.environ.get("BACKEND_URL", DEFAULT_BACKEND))
    ap.add_argument("--admin-email", default=os.environ.get("PROD_ADMIN_EMAIL", DEFAULT_ADMIN_EMAIL))
    ap.add_argument("--admin-password", default=os.environ.get("PROD_ADMIN_PASSWORD"))
    ap.add_argument("--verbose", "-v", action="store_true")
    args = ap.parse_args()
    if not args.admin_password:
        print(
            "ERROR: set PROD_ADMIN_PASSWORD env var (or --admin-password). "
            "The script does NOT hardcode the password.",
            file=sys.stderr,
        )
        sys.exit(2)
    sys.exit(check(args.backend, args.admin_email, args.admin_password, args.verbose))
