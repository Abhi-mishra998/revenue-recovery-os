"""
Shared mongo db accessor. Lazy import to avoid the
  services.db.repos -> server -> services.db.repos
circular dependency that would otherwise show up at module load.
"""

from __future__ import annotations


def db():
    """Returns the motor `db` handle from server.py."""
    from server import db as _db  # local import is intentional — see module docstring

    return _db
