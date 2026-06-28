"""
Engine-dispatching repos.

Each repo module exposes function-level methods (no classes — callers don't
need to swap instances). Inside each function, we dispatch on
is_postgres() at call time. Default engine (mongo) keeps the legacy path
bit-identical; postgres routes through the RLS-aware asyncpg helper.
"""
