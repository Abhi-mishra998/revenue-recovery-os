#!/usr/bin/env python3
"""
One-command demo reset for ByteHubble.

Usage (from /app/backend):
    python scripts/reset_demo.py               # wipe + reseed
    python scripts/reset_demo.py --wipe-only   # wipe, no reseed
    python scripts/reset_demo.py --email user@example.com   # target a non-default user

Notes
-----
Only the demo content (clients, proposals, invoices, activities) for the target
owner is touched. The user account itself is preserved so you can log in immediately.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT))

from motor.motor_asyncio import AsyncIOMotorClient  # noqa: E402

from services.seed import reset_demo_data_for_owner, seed_demo_for_owner  # noqa: E402


async def main():
    parser = argparse.ArgumentParser(description="Reset ByteHubble demo data.")
    parser.add_argument("--wipe-only", action="store_true", help="Delete demo data, don't reseed.")
    default_email = (
        (os.environ.get("ADMIN_EMAILS") or os.environ.get("ADMIN_EMAIL") or "founder@bytehubble.com")
        .split(",")[0]
        .strip()
    )
    parser.add_argument("--email", default=default_email)
    args = parser.parse_args()

    mongo_url = os.environ["MONGO_URL"]
    db_name = os.environ["DB_NAME"]
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    user = await db.users.find_one({"email": args.email.lower()})
    if not user:
        print(
            f"[reset_demo] No user found with email {args.email!r}. Run the server once first to seed the admin."
        )
        return 1

    owner_id = user["id"]
    print(f"[reset_demo] Target user: {args.email}  (id={owner_id[:8]}…)")

    counts = await reset_demo_data_for_owner(db, owner_id)
    print(f"[reset_demo] Wiped: {counts}")

    if not args.wipe_only:
        result = await seed_demo_for_owner(db, owner_id, force=True)
        print(f"[reset_demo] Seeded: {result}")

    client.close()
    print("[reset_demo] Done.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()) or 0)
