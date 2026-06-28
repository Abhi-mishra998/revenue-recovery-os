"""
Direct-DB RLS proof. No HTTP. No fixtures from server.py.

These tests bypass the API entirely so a regression in `with_user()` (e.g.
someone removing `SET LOCAL ROLE revora_app`) fails here loudly even if the
API-level isolation tests happen to still pass for other reasons.

Skips cleanly if POSTGRES_URL isn't reachable.
"""

import asyncio
import os
import uuid

import pytest

POSTGRES_URL = os.environ.get("POSTGRES_URL")
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="POSTGRES_URL not set")


def _run(coro):
    return asyncio.run(coro)


# Each test acquires a fresh connection inside its own event loop — avoids the
# 'no current event loop' clash you get when reusing an asyncpg.Pool across
# asyncio.run() calls.


async def _connect():
    import asyncpg

    return await asyncpg.connect(POSTGRES_URL, timeout=5)


async def _set_role_and_user(conn, user_id: str) -> None:
    await conn.execute("SET LOCAL ROLE revora_app")
    await conn.execute(
        "SELECT set_config('app.current_user_id', $1, true)",
        user_id,
    )


async def _make_two_users() -> tuple[str, str]:
    u1, u2 = str(uuid.uuid4()), str(uuid.uuid4())
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute(
                "INSERT INTO users (id, email, created_at) VALUES "
                "($1::uuid, $2, '2026-06-28T00:00:00+00:00'), "
                "($3::uuid, $4, '2026-06-28T00:00:00+00:00')",
                u1,
                f"rls-{u1[:6]}@x",
                u2,
                f"rls-{u2[:6]}@x",
            )
    finally:
        await conn.close()
    return u1, u2


async def _drop_users(*user_ids: str) -> None:
    conn = await _connect()
    try:
        async with conn.transaction():
            await conn.execute("DELETE FROM users WHERE id = ANY($1::uuid[])", list(user_ids))
    finally:
        await conn.close()


async def _insert_client_as(user_id: str, label: str = "Co") -> str:
    cid = str(uuid.uuid4())
    conn = await _connect()
    try:
        async with conn.transaction():
            await _set_role_and_user(conn, user_id)
            await conn.execute(
                "INSERT INTO clients (id, owner_id, company_name, contact_name, "
                "language, created_at) VALUES ($1::uuid, $2::uuid, $3, 'Tester', "
                "'English', '2026-06-28T00:00:00+00:00')",
                cid,
                user_id,
                label,
            )
    finally:
        await conn.close()
    return cid


# ----------------------------------------------------------------------------


class TestClientsRls:
    def test_other_user_cannot_see_my_client(self):
        u1, u2 = _run(_make_two_users())
        try:
            cid = _run(_insert_client_as(u1, "u1-co"))

            async def count_as(user_id):
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, user_id)
                        return await conn.fetchval(
                            "SELECT count(*) FROM clients WHERE id = $1::uuid",
                            cid,
                        )
                finally:
                    await conn.close()

            assert _run(count_as(u2)) == 0
            assert _run(count_as(u1)) == 1
        finally:
            _run(_drop_users(u1, u2))

    def test_other_user_cannot_update_my_client(self):
        u1, u2 = _run(_make_two_users())
        try:
            cid = _run(_insert_client_as(u1, "u1-update-target"))

            async def u2_update():
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, u2)
                        return await conn.execute(
                            "UPDATE clients SET company_name = 'pwned' WHERE id = $1::uuid",
                            cid,
                        )
                finally:
                    await conn.close()

            assert "UPDATE 0" in _run(u2_update())

            async def name_as_u1():
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, u1)
                        return await conn.fetchval(
                            "SELECT company_name FROM clients WHERE id = $1::uuid",
                            cid,
                        )
                finally:
                    await conn.close()

            assert _run(name_as_u1()) == "u1-update-target"
        finally:
            _run(_drop_users(u1, u2))

    def test_other_user_cannot_delete_my_client(self):
        u1, u2 = _run(_make_two_users())
        try:
            cid = _run(_insert_client_as(u1, "u1-delete-target"))

            async def u2_delete():
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, u2)
                        return await conn.execute(
                            "DELETE FROM clients WHERE id = $1::uuid",
                            cid,
                        )
                finally:
                    await conn.close()

            assert "DELETE 0" in _run(u2_delete())

            async def still_there():
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, u1)
                        return await conn.fetchval(
                            "SELECT count(*) FROM clients WHERE id = $1::uuid",
                            cid,
                        )
                finally:
                    await conn.close()

            assert _run(still_there()) == 1
        finally:
            _run(_drop_users(u1, u2))

    def test_writing_with_wrong_owner_id_is_blocked(self):
        """WITH CHECK should reject INSERT where owner_id != current_user_id."""
        u1, u2 = _run(_make_two_users())
        try:
            cid = str(uuid.uuid4())
            import asyncpg.exceptions

            async def bad_insert():
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, u1)
                        await conn.execute(
                            "INSERT INTO clients (id, owner_id, company_name, contact_name, "
                            "language, created_at) VALUES ($1::uuid, $2::uuid, 'X', 'Y', "
                            "'English', '2026-06-28T00:00:00+00:00')",
                            cid,
                            u2,
                        )
                finally:
                    await conn.close()

            with pytest.raises(asyncpg.exceptions.InsufficientPrivilegeError):
                _run(bad_insert())
        finally:
            _run(_drop_users(u1, u2))


class TestProposalsRls:
    def test_proposals_isolated_too(self):
        u1, u2 = _run(_make_two_users())
        try:
            cid = _run(_insert_client_as(u1, "u1-proposal-host"))
            pid = str(uuid.uuid4())

            async def u1_insert():
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, u1)
                        await conn.execute(
                            "INSERT INTO proposals (id, owner_id, client_id, title, value_inr, "
                            "sent_date, last_contact_date, stage, created_at) "
                            "VALUES ($1::uuid, $2::uuid, $3::uuid, 'p', 1000, "
                            "'2026-06-28T00:00:00+00:00', '2026-06-28T00:00:00+00:00', "
                            "'sent', '2026-06-28T00:00:00+00:00')",
                            pid,
                            u1,
                            cid,
                        )
                finally:
                    await conn.close()

            _run(u1_insert())

            async def u2_count():
                conn = await _connect()
                try:
                    async with conn.transaction():
                        await _set_role_and_user(conn, u2)
                        return await conn.fetchval(
                            "SELECT count(*) FROM proposals WHERE id = $1::uuid",
                            pid,
                        )
                finally:
                    await conn.close()

            assert _run(u2_count()) == 0
        finally:
            _run(_drop_users(u1, u2))
