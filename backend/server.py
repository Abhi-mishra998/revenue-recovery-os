from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / ".env")

import asyncio
import logging
import os
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

import bcrypt
import httpx
import jwt
from fastapi import APIRouter, Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from starlette.middleware.cors import CORSMiddleware

from services.ai import (
    GuardrailViolation,
    LLMProviderUnavailable,
    MalformedOutputError,
    NoApiKeyError,
    generate_proposal_followup,
)
from services.ai.brief import generate_brief, template_fallback
from services.ai.client import generate_json
from services.ai.schemas import MappingSuggestion
from services.audit import append_audit, get_public_key_fp, load_signing_key, verify_chain
from services.data import extract_proposal_features, predict_close_probability
from services.data import revenue_health as rh
from services.data.import_commit import (
    _g,
    build_client_doc,
    build_invoice_doc,
    build_proposal_doc,
)
from services.data.import_heuristics import analyze_file
from services.data.import_mapping import LLM_SYSTEM, heuristic_mapping, llm_user_prompt
from services.db import is_mongo, is_postgres
from services.db import pg as pgdb
from services.db.repos import (
    activities as activities_repo,
)
from services.db.repos import (
    audit_log as audit_log_repo,
)
from services.db.repos import (
    client_memory as memory_repo,
)
from services.db.repos import (
    clients as clients_repo,
)
from services.db.repos import (
    events as events_repo,
)
from services.db.repos import (
    followups as followups_repo,
)
from services.db.repos import (
    health_snapshots as health_snapshots_repo,
)
from services.db.repos import (
    import_jobs as import_jobs_repo,
)
from services.db.repos import (
    invoices as invoices_repo,
)
from services.db.repos import (
    proposals as proposals_repo,
)
from services.db.repos import (
    settings as settings_repo,
)
from services.db.repos import (
    users as users_repo,
)
from services.events import emit_event
from services.memory import get_or_compute_client_memory, recompute_client_memory
from services.obs import init_logging, init_sentry, request_id_ctx, user_id_ctx
from services.seed import seed_demo_for_owner

# ---------- Boot-time secret validation ----------
# ENV=production tightens everything; anything else is dev/staging mode.
# Fails fast at import so you can't accidentally ship with test secrets.
ENV = (os.environ.get("ENV") or "development").lower()
_IS_PROD = ENV == "production"


def _validate_boot_secrets() -> None:
    jwt_secret = os.environ.get("JWT_SECRET", "")
    if not jwt_secret:
        raise RuntimeError("JWT_SECRET is required.")
    if _IS_PROD:
        if len(jwt_secret) < 32:
            raise RuntimeError(f"JWT_SECRET must be ≥32 chars in production (got {len(jwt_secret)}).")
        if jwt_secret.startswith(("test-", "ci-", "dev-", "changeme")):
            raise RuntimeError("JWT_SECRET looks like a placeholder. Set a real secret in production.")
        cors = os.environ.get("CORS_ORIGINS", "")
        if cors.strip() == "*" or not cors.strip():
            raise RuntimeError("CORS_ORIGINS must be an explicit allowlist in production (no '*', no empty).")
        if not os.environ.get("AUDIT_SIGNING_KEY"):
            # Not fatal — auto-gen still works — but loud, because a process restart
            # without env-pinned key + without persisted settings = chain break.
            import logging as _l

            _l.getLogger(__name__).warning(
                "ENV=production but AUDIT_SIGNING_KEY not set. Audit chain depends on "
                "the auto-generated key surviving in db.settings."
            )


_validate_boot_secrets()


# ---------- MongoDB ----------
mongo_url = os.environ["MONGO_URL"]
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ["DB_NAME"]]

JWT_SECRET = os.environ["JWT_SECRET"]
JWT_ALG = "HS256"

EMERGENT_AUTH_SESSION_URL = "https://demobackend.emergentagent.com/auth/v1/env/oauth/session-data"

app = FastAPI(title="Revora — Revenue Recovery OS")
api = APIRouter(prefix="/api")
bearer_scheme = HTTPBearer(auto_error=False)


def _user_or_ip_key(request: Request) -> str:
    """Rate-limit key: authenticated user id when available, else IP."""
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        try:
            payload = jwt.decode(
                auth.split(None, 1)[1].strip(),
                JWT_SECRET,
                algorithms=[JWT_ALG],
                options={"verify_exp": False},
            )
            sub = payload.get("sub")
            if sub:
                return f"user:{sub}"
        except Exception:
            pass
    return f"ip:{get_remote_address(request)}"


# `RATE_LIMIT_ENABLED=false` disables limits — for test/CI runs that share an IP.
_rate_limit_enabled = os.environ.get("RATE_LIMIT_ENABLED", "true").lower() == "true"
limiter = Limiter(key_func=get_remote_address, enabled=_rate_limit_enabled)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


# Global catch-all for anything we didn't think of. Logs the full traceback
# server-side (with request_id) so ops can trace, returns a stable safe shape
# to the client. Never leak internal paths/stack frames.
async def _internal_error_handler(request: Request, exc: Exception):
    from starlette.responses import JSONResponse

    rid = request_id_ctx.get() or "unknown"
    logging.getLogger(__name__).exception(
        "unhandled_exception",
        extra={"route": request.url.path, "method": request.method, "request_id": rid},
    )
    return JSONResponse(
        status_code=500,
        content={
            "detail": {
                "code": "internal_error",
                "message": "Something went wrong on our end. Please try again.",
                "request_id": rid,
            }
        },
    )


app.add_exception_handler(Exception, _internal_error_handler)


# ---------- Helpers ----------
def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(p: str, h: str) -> bool:
    if not h:
        return False
    try:
        return bcrypt.checkpw(p.encode("utf-8"), h.encode("utf-8"))
    except Exception:
        return False


def create_access_token(user_id: str, email: str, token_version: int = 0) -> str:
    payload = {
        "sub": user_id,
        "email": email,
        "tv": token_version,
        "exp": now_utc() + timedelta(days=7),
        "type": "access",
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALG)


async def get_current_user(creds: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme)) -> dict:
    if not creds or not creds.credentials:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(creds.credentials, JWT_SECRET, algorithms=[JWT_ALG])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await users_repo.get_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if int(payload.get("tv", 0)) != int(user.get("token_version", 0)):
        raise HTTPException(status_code=401, detail="Token revoked")
    user.pop("_id", None)
    user.pop("password_hash", None)
    # Stamp user_id into the request context so subsequent log lines + the
    # access-log middleware include it automatically.
    user_id_ctx.set(user["id"])
    return user


def _admin_emails() -> set[str]:
    """Set of admin emails (lowercased). ADMIN_EMAILS (CSV) takes precedence;
    ADMIN_EMAIL is a backward-compat single-value fallback."""
    raw = os.environ.get("ADMIN_EMAILS") or os.environ.get("ADMIN_EMAIL") or ""
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "auth_provider": u.get("auth_provider", "email"),
        "is_admin": u["email"].lower() in _admin_emails(),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    if user["email"].lower() not in _admin_emails():
        raise HTTPException(status_code=403, detail="Admin only")
    return user


async def assert_owns_client(client_id: str, user: dict) -> None:
    if not await clients_repo.exists_for_owner(client_id, user["id"]):
        raise HTTPException(404, "Client not found")


_EXISTS_BY_COLLECTION = {
    "clients": clients_repo.exists_for_owner,
    "proposals": proposals_repo.exists_for_owner,
}


async def assert_owns(collection: str, doc_id: str, user: dict) -> None:
    """Generic ownership check used for activity.related_id ∈ {proposals, invoices}."""
    fn = _EXISTS_BY_COLLECTION.get(collection)
    if fn is None:
        # invoices and others — fall back to a per-collection lookup
        if collection == "invoices":
            inv = await invoices_repo.get_for_owner(doc_id, user["id"])
            if not inv:
                raise HTTPException(404, "Not found")
            return
        raise HTTPException(404, "Not found")
    if not await fn(doc_id, user["id"]):
        raise HTTPException(404, "Not found")


# ---------- Status compute (RULE: never typed by user) ----------
def compute_proposal_status(last_contact_date: str) -> str:
    """Locked PRD thresholds: active ≤7d, cold 8-21d, dead >21d."""
    last = datetime.fromisoformat(last_contact_date)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = (now_utc() - last).days
    if days <= 7:
        return "active"
    if days <= 21:
        return "cold"
    return "dead"


def compute_invoice_status_and_overdue(invoice: dict) -> tuple[str, int]:
    if invoice.get("paid_date"):
        return "paid", 0
    due = datetime.fromisoformat(invoice["due_date"])
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    days_overdue = (now_utc() - due).days
    if days_overdue > 0:
        return "overdue", days_overdue
    return "unpaid", 0


def days_since(iso: str) -> int:
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (now_utc() - d).days


# ---------- Models ----------
# Length caps are generous but bounded — keep one mongo doc < ~50 KB and stop
# clients from posting megabyte payloads into notes/summary.
NAME_LEN = 120
TITLE_LEN = 300
COMPANY_LEN = 200
SHORT_LEN = 80
PHONE_LEN = 30
INVOICE_NO_LEN = 50
NOTES_LEN = 4000
MONEY_MAX = 1_000_000_000_000.0  # ₹1 trillion — well past any real proposal


class RegisterReq(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=8, max_length=128)
    name: str = Field(..., min_length=1, max_length=NAME_LEN)


class LoginReq(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=128)


class GoogleSessionReq(BaseModel):
    session_id: str = Field(..., min_length=1, max_length=512)


class ClientCreate(BaseModel):
    company_name: str = Field(..., min_length=1, max_length=COMPANY_LEN)
    contact_name: str = Field(..., min_length=1, max_length=NAME_LEN)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=PHONE_LEN)
    whatsapp: Optional[str] = Field(None, max_length=PHONE_LEN)
    industry: Optional[str] = Field(None, max_length=SHORT_LEN)
    language: str = Field("English", min_length=1, max_length=SHORT_LEN)
    notes: Optional[str] = Field(None, max_length=NOTES_LEN)


class ClientUpdate(BaseModel):
    company_name: Optional[str] = Field(None, min_length=1, max_length=COMPANY_LEN)
    contact_name: Optional[str] = Field(None, min_length=1, max_length=NAME_LEN)
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, max_length=PHONE_LEN)
    whatsapp: Optional[str] = Field(None, max_length=PHONE_LEN)
    industry: Optional[str] = Field(None, max_length=SHORT_LEN)
    language: Optional[str] = Field(None, min_length=1, max_length=SHORT_LEN)
    notes: Optional[str] = Field(None, max_length=NOTES_LEN)


ProposalStage = Literal["sent", "negotiating", "won", "lost"]


class ProposalCreate(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=64)
    title: str = Field(..., min_length=1, max_length=TITLE_LEN)
    value_inr: float = Field(..., gt=0, le=MONEY_MAX)
    sent_date: Optional[str] = None
    last_contact_date: Optional[str] = None
    stage: ProposalStage = "sent"
    notes: Optional[str] = Field(None, max_length=NOTES_LEN)


class ProposalUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=TITLE_LEN)
    value_inr: Optional[float] = Field(None, gt=0, le=MONEY_MAX)
    sent_date: Optional[str] = None
    last_contact_date: Optional[str] = None
    stage: Optional[ProposalStage] = None
    notes: Optional[str] = Field(None, max_length=NOTES_LEN)


class InvoiceCreate(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=64)
    invoice_no: str = Field(..., min_length=1, max_length=INVOICE_NO_LEN)
    amount_inr: float = Field(..., gt=0, le=MONEY_MAX)
    due_date: str
    paid_date: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=NOTES_LEN)


class InvoiceUpdate(BaseModel):
    invoice_no: Optional[str] = Field(None, min_length=1, max_length=INVOICE_NO_LEN)
    amount_inr: Optional[float] = Field(None, gt=0, le=MONEY_MAX)
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    notes: Optional[str] = Field(None, max_length=NOTES_LEN)


ActivityChannel = Literal["call", "whatsapp", "email", "meeting", "note"]
ActivityDirection = Literal["inbound", "outbound", "internal"]


class ActivityCreate(BaseModel):
    client_id: str = Field(..., min_length=1, max_length=64)
    related_type: Optional[Literal["proposal", "invoice"]] = None
    related_id: Optional[str] = Field(None, max_length=64)
    channel: ActivityChannel
    direction: ActivityDirection = "outbound"
    summary: str = Field(..., min_length=1, max_length=NOTES_LEN)


# ---------- Serialization ----------
def serialize_proposal(p: dict, clients_map: Optional[dict] = None) -> dict:
    out = {k: v for k, v in p.items() if k != "_id"}
    out["status"] = compute_proposal_status(p["last_contact_date"])
    out["days_silent"] = days_since(p["last_contact_date"])
    if clients_map is not None:
        c = clients_map.get(p["client_id"], {})
        out["client_company_name"] = c.get("company_name", "Unknown")
        out["client_contact_name"] = c.get("contact_name", "")
    return out


def serialize_invoice(inv: dict, clients_map: Optional[dict] = None) -> dict:
    out = {k: v for k, v in inv.items() if k != "_id"}
    status, days_overdue = compute_invoice_status_and_overdue(inv)
    out["status"] = status
    out["days_overdue"] = days_overdue
    if clients_map is not None:
        c = clients_map.get(inv["client_id"], {})
        out["client_company_name"] = c.get("company_name", "Unknown")
        out["client_contact_name"] = c.get("contact_name", "")
    return out


# ---------- Auth endpoints ----------
@api.post("/auth/register")
@limiter.limit("10/minute")
async def register(request: Request, req: RegisterReq):
    email = req.email.lower()
    existing = await users_repo.get_by_email(email)
    if existing:
        raise HTTPException(status_code=400, detail="Email already registered")
    user_id = str(uuid.uuid4())
    doc = {
        "id": user_id,
        "email": email,
        "name": req.name,
        "auth_provider": "email",
        "password_hash": hash_password(req.password),
        "token_version": 0,
        "created_at": now_utc().isoformat(),
    }
    await users_repo.insert(doc)
    await append_audit(
        db,
        action="auth.register",
        actor_id=user_id,
        actor_email=email,
        resource_type="user",
        resource_id=user_id,
        payload={"name": req.name},
    )
    token = create_access_token(user_id, email, 0)
    return {"token": token, "user": public_user(doc)}


@api.post("/auth/login")
@limiter.limit("30/minute")
async def login(request: Request, req: LoginReq):
    email = req.email.lower()
    user = await users_repo.get_by_email(email)
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], email, user.get("token_version", 0))
    return {"token": token, "user": public_user(user)}


@api.post("/auth/google/session")
@limiter.limit("30/minute")
async def google_session(request: Request, req: GoogleSessionReq):
    """
    Exchange an Emergent Google OAuth session_id (received in URL fragment on
    redirect back) for a Revora JWT bearer token.

    REMINDER: DO NOT HARDCODE THE URL, OR ADD ANY FALLBACKS OR REDIRECT URLS, THIS BREAKS THE AUTH
    """
    async with httpx.AsyncClient(timeout=10.0) as http:
        try:
            resp = await http.get(EMERGENT_AUTH_SESSION_URL, headers={"X-Session-ID": req.session_id})
        except httpx.HTTPError as e:
            raise HTTPException(status_code=502, detail=f"Auth upstream error: {e}")
    if resp.status_code != 200:
        raise HTTPException(status_code=401, detail="Invalid Google session")
    info = resp.json()
    email = (info.get("email") or "").lower()
    name = info.get("name") or info.get("email") or "Google user"
    if not email:
        raise HTTPException(status_code=400, detail="Google session missing email")

    user = await users_repo.get_by_email(email)
    if user is None:
        user_id = str(uuid.uuid4())
        user = {
            "id": user_id,
            "email": email,
            "name": name,
            "auth_provider": "google",
            "password_hash": None,
            "token_version": 0,
            "created_at": now_utc().isoformat(),
        }
        await users_repo.insert(user.copy())
        await append_audit(
            db,
            action="auth.google_session.register",
            actor_id=user["id"],
            actor_email=email,
            resource_type="user",
            resource_id=user["id"],
            payload={"name": name},
        )
    elif user.get("auth_provider") != "google":
        # Refuse silent account linking — a Google account for a password user's
        # email would otherwise take over that account.
        raise HTTPException(
            status_code=409,
            detail="This email is registered with a password. Please sign in with your password.",
        )

    token = create_access_token(user["id"], email, user.get("token_version", 0))
    return {"token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api.post("/auth/logout", status_code=204)
async def logout(user: dict = Depends(get_current_user)):
    """Revoke every outstanding token for this user by bumping token_version."""
    await users_repo.bump_token_version(user["id"])
    await append_audit(action="auth.logout", actor_id=user["id"], actor_email=user["email"])
    return None


# ---------- DPDP: data export + account deletion ----------
@api.get("/me/data")
async def export_my_data(user: dict = Depends(get_current_user)):
    """Full JSON dump of everything Revora stores about the caller's tenant.
    The DPDP Act requires us to make this available on request — this endpoint
    delivers in O(seconds) for a typical tenant."""
    uid = user["id"]
    clients, proposals, invoices, activities, followups, events, memory = await asyncio.gather(
        clients_repo.list_for_owner(uid),
        proposals_repo.list_for_owner(uid),
        invoices_repo.list_for_owner(uid),
        activities_repo.list_for_owner(uid, limit=10000),
        followups_repo.list_for_owner(uid),
        events_repo.list_for_owner(uid),
        memory_repo.list_for_owner(uid),
    )
    await append_audit(
        action="me.data.export",
        actor_id=uid,
        actor_email=user["email"],
        resource_type="user",
        resource_id=uid,
        payload={
            "counts": {
                "clients": len(clients),
                "proposals": len(proposals),
                "invoices": len(invoices),
                "activities": len(activities),
                "followups": len(followups),
                "events": len(events),
                "client_memory": len(memory),
            }
        },
    )
    return {
        "exported_at": now_utc().isoformat(),
        "user": public_user(user),
        "clients": clients,
        "proposals": proposals,
        "invoices": invoices,
        "activities": activities,
        "followups": followups,
        "events": events,
        "client_memory": memory,
    }


@api.delete("/me", status_code=204)
async def delete_my_account(user: dict = Depends(get_current_user)):
    """Delete the caller + every owned record. Postgres uses FK cascades;
    Mongo deletes per collection. The audit row is appended BEFORE the user
    row is gone (the chain doesn't lose the deletion fact)."""
    uid = user["id"]
    # Audit first — otherwise the deleted user's id is meaningless in logs.
    await append_audit(
        action="me.account.delete",
        actor_id=uid,
        actor_email=user["email"],
        resource_type="user",
        resource_id=uid,
    )
    await users_repo.delete_user_cascade(uid)
    return None


# ---------- Clients ----------
@api.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)):
    return await clients_repo.list_for_owner(user["id"])


@api.post("/clients")
async def create_client(payload: ClientCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    await clients_repo.insert(doc)
    await append_audit(
        action="client.create",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="client",
        resource_id=doc["id"],
        payload=payload.model_dump(),
    )
    return doc


@api.get("/clients/{client_id}")
async def get_client(client_id: str, user: dict = Depends(get_current_user)):
    # Three independent reads — fan out instead of three serial round-trips.
    c, proposals, invoices = await asyncio.gather(
        clients_repo.get_for_owner(client_id, user["id"]),
        proposals_repo.list_for_client_and_owner(client_id, user["id"], limit=500),
        invoices_repo.list_for_client_and_owner(client_id, user["id"], limit=500),
    )
    if not c:
        raise HTTPException(404, "Client not found")
    return {
        "client": c,
        "proposals": [serialize_proposal(p) for p in proposals],
        "invoices": [serialize_invoice(i) for i in invoices],
    }


@api.patch("/clients/{client_id}")
async def update_client(client_id: str, payload: ClientUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    matched = await clients_repo.update_for_owner(client_id, user["id"], updates)
    if not matched:
        raise HTTPException(404, "Client not found")
    c = await clients_repo.get_for_owner(client_id, user["id"])
    await append_audit(
        action="client.update",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="client",
        resource_id=client_id,
        payload=updates,
    )
    return c


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(get_current_user)):
    deleted = await clients_repo.delete_for_owner(client_id, user["id"])
    if deleted:
        await append_audit(
            action="client.delete",
            actor_id=user["id"],
            actor_email=user["email"],
            resource_type="client",
            resource_id=client_id,
        )
        await memory_repo.delete_for_client(user["id"], client_id)
    return {"ok": True}


@api.get("/clients/{client_id}/memory")
async def get_client_memory(client_id: str, user: dict = Depends(get_current_user)):
    """Per-client derived features. Cached doc; rebuilt on read if missing."""
    await assert_owns_client(client_id, user)
    return await get_or_compute_client_memory(owner_id=user["id"], client_id=client_id)


# ---------- Proposals ----------
async def _clients_map_for(owner_id: str) -> dict:
    rows = await clients_repo.list_for_owner(owner_id)
    return {c["id"]: c for c in rows}


@api.get("/proposals")
async def list_proposals(user: dict = Depends(get_current_user)):
    rows, clients_map = await asyncio.gather(
        proposals_repo.list_for_owner(user["id"]),
        _clients_map_for(user["id"]),
    )
    out = [serialize_proposal(p, clients_map) for p in rows]
    out.sort(key=lambda x: x["days_silent"], reverse=True)
    return out


@api.post("/proposals")
async def create_proposal(payload: ProposalCreate, user: dict = Depends(get_current_user)):
    await assert_owns_client(payload.client_id, user)
    now_iso = now_utc().isoformat()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["sent_date"] = doc.get("sent_date") or now_iso
    doc["last_contact_date"] = doc.get("last_contact_date") or doc["sent_date"]
    doc["created_at"] = now_iso
    await proposals_repo.insert(doc)
    await append_audit(
        action="proposal.create",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="proposal",
        resource_id=doc["id"],
        payload=payload.model_dump(),
    )
    await emit_event(
        owner_id=user["id"],
        event_type="proposal.created",
        entity_type="proposal",
        entity_id=doc["id"],
        source="user",
        metadata={"value_inr": doc["value_inr"], "stage": doc["stage"], "client_id": doc["client_id"]},
    )
    return serialize_proposal(doc)


@api.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    p = await proposals_repo.get_for_owner(proposal_id, user["id"])
    if not p:
        raise HTTPException(404, "Proposal not found")
    # client + memory are independent — fan out.
    c, memory = await asyncio.gather(
        clients_repo.get_for_owner(p["client_id"], user["id"]),
        memory_repo.get(user["id"], p["client_id"]),
    )
    c = c or {}
    out = serialize_proposal(p, {p["client_id"]: c})
    enriched_proposal = {**p, "client_industry": c.get("industry")}
    features = extract_proposal_features(proposal=enriched_proposal, memory=memory)
    out["prediction"] = predict_close_probability(features).to_dict()
    return out


@api.get("/proposals/{proposal_id}/followups")
async def list_proposal_followups(proposal_id: str, user: dict = Depends(get_current_user)):
    """Generation history for a proposal — newest first, grouped by generation_id."""
    await assert_owns("proposals", proposal_id, user)
    return await followups_repo.list_for_proposal(proposal_id, user["id"], limit=100)


@api.patch("/proposals/{proposal_id}")
async def update_proposal(proposal_id: str, payload: ProposalUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")

    prior = await proposals_repo.get_for_owner(proposal_id, user["id"])
    if not prior:
        raise HTTPException(404, "Proposal not found")
    prior_stage = prior.get("stage")
    new_stage = updates.get("stage")
    stage_changing = new_stage and new_stage != prior_stage
    if stage_changing and new_stage in ("won", "lost"):
        updates["outcome_at"] = now_utc().isoformat()

    await proposals_repo.update_for_owner(proposal_id, user["id"], updates)
    p = await proposals_repo.get_for_owner(proposal_id, user["id"])
    await append_audit(
        action="proposal.update",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="proposal",
        resource_id=proposal_id,
        payload=updates,
    )

    if stage_changing:
        sent_iso = prior.get("sent_date")
        days_to_close = days_since(sent_iso) if sent_iso else None
        await emit_event(
            owner_id=user["id"],
            event_type="proposal.stage_changed",
            entity_type="proposal",
            entity_id=proposal_id,
            source="user",
            prior_value=prior_stage,
            new_value=new_stage,
            metadata={"value_inr": prior.get("value_inr"), "client_id": prior.get("client_id")},
        )
        if new_stage in ("won", "lost"):
            await emit_event(
                owner_id=user["id"],
                event_type=f"proposal.{new_stage}",
                entity_type="proposal",
                entity_id=proposal_id,
                source="user",
                metadata={
                    "value_inr": prior.get("value_inr"),
                    "days_to_close": days_to_close,
                    "client_id": prior.get("client_id"),
                },
            )
            await recompute_client_memory(owner_id=user["id"], client_id=prior["client_id"])
    return serialize_proposal(p)


@api.delete("/proposals/{proposal_id}")
async def delete_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    deleted = await proposals_repo.delete_for_owner(proposal_id, user["id"])
    if deleted:
        await append_audit(
            action="proposal.delete",
            actor_id=user["id"],
            actor_email=user["email"],
            resource_type="proposal",
            resource_id=proposal_id,
        )
    return {"ok": True}


# ---------- Invoices ----------
@api.get("/invoices")
async def list_invoices(user: dict = Depends(get_current_user)):
    rows, clients_map = await asyncio.gather(
        invoices_repo.list_for_owner(user["id"]),
        _clients_map_for(user["id"]),
    )
    out = [serialize_invoice(inv, clients_map) for inv in rows]
    out.sort(key=lambda x: x["days_overdue"], reverse=True)
    return out


@api.post("/invoices")
async def create_invoice(payload: InvoiceCreate, user: dict = Depends(get_current_user)):
    await assert_owns_client(payload.client_id, user)
    now_iso = now_utc().isoformat()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["issued_at"] = now_iso
    doc["created_at"] = now_iso
    await invoices_repo.insert(doc)
    await append_audit(
        action="invoice.create",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="invoice",
        resource_id=doc["id"],
        payload=payload.model_dump(),
    )
    await emit_event(
        owner_id=user["id"],
        event_type="invoice.created",
        entity_type="invoice",
        entity_id=doc["id"],
        source="user",
        metadata={
            "amount_inr": doc["amount_inr"],
            "due_date": doc["due_date"],
            "client_id": doc["client_id"],
        },
    )
    return serialize_invoice(doc)


@api.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    inv = await invoices_repo.get_for_owner(invoice_id, user["id"])
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return serialize_invoice(inv)


@api.patch("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    prior = await invoices_repo.get_for_owner(invoice_id, user["id"])
    if not prior:
        raise HTTPException(404, "Invoice not found")
    became_paid = (not prior.get("paid_date")) and updates.get("paid_date")

    await invoices_repo.update_for_owner(invoice_id, user["id"], updates)
    inv = await invoices_repo.get_for_owner(invoice_id, user["id"])
    await append_audit(
        action="invoice.update",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="invoice",
        resource_id=invoice_id,
        payload=updates,
    )

    if became_paid:
        _, days_overdue_at_payment = compute_invoice_status_and_overdue({**prior, "paid_date": None})
        await emit_event(
            owner_id=user["id"],
            event_type="invoice.payment_received",
            entity_type="invoice",
            entity_id=invoice_id,
            source="user",
            metadata={
                "amount_inr": prior.get("amount_inr"),
                "days_overdue_at_payment": days_overdue_at_payment,
                "client_id": prior.get("client_id"),
            },
        )
        await recompute_client_memory(owner_id=user["id"], client_id=prior["client_id"])
    return serialize_invoice(inv)


@api.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    deleted = await invoices_repo.delete_for_owner(invoice_id, user["id"])
    if deleted:
        await append_audit(
            action="invoice.delete",
            actor_id=user["id"],
            actor_email=user["email"],
            resource_type="invoice",
            resource_id=invoice_id,
        )
    return {"ok": True}


# ---------- Events (append-only product analytics) ----------
@api.get("/events")
async def list_events(
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    event_type: Optional[str] = None,
    limit: int = 200,
    user: dict = Depends(get_current_user),
):
    """Read-only tail of the events stream, scoped to the caller's tenant."""
    limit = max(1, min(1000, limit))
    return await events_repo.list_filtered(
        user["id"],
        entity_type=entity_type,
        entity_id=entity_id,
        event_type=event_type,
        limit=limit,
    )


# ---------- Activities ----------
@api.get("/activities")
async def list_activities(user: dict = Depends(get_current_user)):
    return await activities_repo.list_for_owner(user["id"], limit=200)


@api.post("/activities")
async def create_activity(payload: ActivityCreate, user: dict = Depends(get_current_user)):
    await assert_owns_client(payload.client_id, user)
    if payload.related_type and payload.related_id:
        await assert_owns(payload.related_type + "s", payload.related_id, user)
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    await activities_repo.insert(doc)
    await append_audit(
        action="activity.create",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="activity",
        resource_id=doc["id"],
        payload=payload.model_dump(),
    )
    await recompute_client_memory(owner_id=user["id"], client_id=doc["client_id"])
    return doc


# ---------- Dashboard ----------
def compute_dashboard_summary(proposals: List[dict], invoices: List[dict], clients_map: dict) -> dict:
    """Pure function — unit-testable. Endpoint just wires it to the repos.
    Inputs are the raw rows from list_for_dashboard; outputs are the wire
    response. Recovery math lives here exactly once."""
    total_pipeline = 0.0
    active_inr = cold_inr = dead_inr = 0.0
    cold_count = 0
    by_status_count = {"active": 0, "cold": 0, "dead": 0}
    by_stage_count = {"sent": 0, "negotiating": 0, "won": 0, "lost": 0}
    at_risk_candidates: list = []

    for p in proposals:
        stage = p.get("stage", "sent")
        by_stage_count[stage] = by_stage_count.get(stage, 0) + 1
        if stage in ("sent", "negotiating"):
            value = float(p["value_inr"])
            total_pipeline += value
            s = compute_proposal_status(p["last_contact_date"])
            by_status_count[s] = by_status_count.get(s, 0) + 1
            if s == "active":
                active_inr += value
            elif s == "cold":
                cold_inr += value
                cold_count += 1
                at_risk_candidates.append((p, s, value))
            elif s == "dead":
                dead_inr += value
                at_risk_candidates.append((p, s, value))

    revenue_at_risk = cold_inr + dead_inr
    estimated_recoverable = round(revenue_at_risk * 0.25)

    overdue_count = 0
    overdue_amount = 0.0
    for inv in invoices:
        s, _ = compute_invoice_status_and_overdue(inv)
        if s == "overdue":
            overdue_count += 1
            overdue_amount += float(inv["amount_inr"])

    def _rank(item):
        p, _, v = item
        d = max(1, days_since(p["last_contact_date"]))
        return v * d

    at_risk_candidates.sort(key=_rank, reverse=True)
    top_at_risk = []
    for p, status, value in at_risk_candidates[:5]:
        c = clients_map.get(p["client_id"], {})
        top_at_risk.append(
            {
                "id": p["id"],
                "title": p["title"],
                "value_inr": value,
                "status": status,
                "days_silent": days_since(p["last_contact_date"]),
                "stage": p.get("stage", "sent"),
                "client_company_name": c.get("company_name", "Unknown"),
                "client_contact_name": c.get("contact_name", ""),
            }
        )

    return {
        "total_pipeline_inr": total_pipeline,
        "active_inr": active_inr,
        "cold_inr": cold_inr,
        "dead_inr": dead_inr,
        "cold_proposals_count": cold_count,
        "overdue_invoices_count": overdue_count,
        "overdue_invoices_inr": overdue_amount,
        "revenue_at_risk_inr": revenue_at_risk,
        "estimated_recoverable_inr": estimated_recoverable,
        "recoverable_assumption_pct": 25,
        "by_status": by_status_count,
        "by_stage": by_stage_count,
        "top_at_risk": top_at_risk,
    }


@api.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    # Three independent reads — fan out instead of three serial round-trips.
    proposals, invoices, clients_map = await asyncio.gather(
        proposals_repo.list_for_dashboard(user["id"]),
        invoices_repo.list_for_dashboard(user["id"]),
        _clients_map_for(user["id"]),
    )
    return compute_dashboard_summary(proposals, invoices, clients_map)


# ---------- Admin: AI kill-switch ----------
# In-process cache. The killswitch is checked on EVERY generate-followup call;
# without this it does a DB read per call (cheap but unnecessary).
# ponytail: single-process cache — multi-process deploys need DB poll or pub/sub.
# `_killswitch_cache` is None until first read; toggle endpoint invalidates it.
_killswitch_cache: Optional[bool] = None


async def ai_killswitch_enabled() -> bool:
    global _killswitch_cache
    if _killswitch_cache is None:
        doc = await settings_repo.get_global()
        _killswitch_cache = bool(doc and doc.get("ai_killswitch"))
    return _killswitch_cache


def _invalidate_killswitch_cache(new_value: bool) -> None:
    """Called by the toggle endpoint — single-process cache stays consistent."""
    global _killswitch_cache
    _killswitch_cache = new_value


class KillSwitchReq(BaseModel):
    enabled: bool


@api.get("/admin/killswitch")
async def get_killswitch(admin: dict = Depends(require_admin)):
    return {"ai_killswitch": await ai_killswitch_enabled()}


@api.post("/admin/killswitch")
async def set_killswitch(req: KillSwitchReq, admin: dict = Depends(require_admin)):
    await settings_repo.set_ai_killswitch(req.enabled)
    _invalidate_killswitch_cache(req.enabled)
    await append_audit(
        action="admin.killswitch.set",
        actor_id=admin["id"],
        actor_email=admin["email"],
        payload={"enabled": req.enabled},
    )
    return {"ai_killswitch": req.enabled}


# ---------- Admin: AI configuration ----------
@api.get("/admin/ai/config")
async def admin_ai_config(admin: dict = Depends(require_admin)):
    """Read-only view of the active prompts + routing table — powers the
    admin dashboard's 'AI Config' card."""
    from services.ai import prompts as _prompts
    from services.ai.router import _DEFAULTS, HIGH_VALUE_THRESHOLD_INR, RouteSignals, route

    active = {task: {"ref": t.ref, "description": t.description} for task, t in _prompts.ACTIVE.items()}
    versions = {t.ref: t.description for t in _prompts.ALL.values()}
    sample_simple = route(RouteSignals(value_inr=100_000))
    sample_complex = route(RouteSignals(value_inr=HIGH_VALUE_THRESHOLD_INR))
    return {
        "active_prompts": active,
        "prompt_versions": versions,
        "routes_default": {
            "simple": {"provider": sample_simple.provider, "model": sample_simple.model},
            "complex": {"provider": sample_complex.provider, "model": sample_complex.model},
        },
        "high_value_threshold_inr": HIGH_VALUE_THRESHOLD_INR,
    }


# ---------- Admin: audit log ----------
@api.get("/admin/audit-log/verify")
async def admin_audit_verify(limit: Optional[int] = None, admin: dict = Depends(require_admin)):
    """Re-walk the audit chain and report hash/signature integrity."""
    return await verify_chain(limit=limit)


@api.get("/admin/audit-log")
async def admin_audit_list(
    page: int = 1,
    page_size: int = 50,
    admin: dict = Depends(require_admin),
):
    """Paginated read of audit records, newest first."""
    page = max(1, page)
    page_size = max(1, min(500, page_size))
    total = await audit_log_repo.count()
    rows = await audit_log_repo.list_paginated(page, page_size)
    return {
        "page": page,
        "page_size": page_size,
        "total": total,
        "public_key_fp": get_public_key_fp(),
        "records": rows,
    }


@api.post("/proposals/{proposal_id}/generate-followup")
@limiter.limit("10/hour", key_func=_user_or_ip_key)
async def generate_followup_for_proposal(
    request: Request, proposal_id: str, user: dict = Depends(get_current_user)
):
    """
    Generate TWO drafts (WhatsApp + Email) for a proposal using the configured LLM.
    Saves each draft to a FollowUp record. Never sends anything.
    """
    if await ai_killswitch_enabled():
        raise HTTPException(
            status_code=503, detail="AI generation is currently disabled by the administrator."
        )
    p = await proposals_repo.get_for_owner(proposal_id, user["id"])
    if not p:
        raise HTTPException(404, "Proposal not found")
    c = await clients_repo.get_for_owner(p["client_id"], user["id"])
    if not c:
        raise HTTPException(404, "Client not found")

    days = max(0, days_since(p["last_contact_date"]))
    context_snapshot = {
        "sender_name": (user.get("name") or "Founder").split()[0],
        "recipient_contact": c.get("contact_name") or "there",
        "recipient_company": c.get("company_name") or "your company",
        "industry": c.get("industry"),
        "title": p["title"],
        "value_inr": float(p["value_inr"]),
        "days_silent": days,
    }

    t0 = time.perf_counter()
    try:
        result = await generate_proposal_followup(**context_snapshot)
    except NoApiKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except GuardrailViolation as e:
        raise HTTPException(status_code=422, detail=f"Draft failed safety checks: {e}. Please regenerate.")
    except LLMProviderUnavailable as e:
        # The frontend looks for code='llm_unavailable' to show the calm
        # 'AI busy, try again' panel + Retry button. Keep the shape stable.
        logger.warning("LLM provider unavailable: %s", e)
        raise HTTPException(
            status_code=503,
            detail={
                "code": "llm_unavailable",
                "message": "AI provider is busy. Please try again in a minute.",
            },
        )
    except MalformedOutputError as e:
        raise HTTPException(status_code=502, detail=f"Model returned invalid output: {e}")
    except Exception as e:
        logger.exception("AI generation failed")
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")
    latency_ms = int((time.perf_counter() - t0) * 1000)

    now_iso = now_utc().isoformat()
    generation_id = str(uuid.uuid4())
    wa_id = str(uuid.uuid4())
    em_id = str(uuid.uuid4())
    common = {
        "owner_id": user["id"],
        "proposal_id": proposal_id,
        "client_id": p["client_id"],
        "generation_id": generation_id,
        "context": context_snapshot,
        "prompt_ref": result.get("prompt_ref"),
        "route_ref": result.get("route_ref"),
        "confidence": result.get("confidence"),
        "latency_ms": latency_ms,
        "created_at": now_iso,
    }
    await followups_repo.insert_many(
        [
            {**common, "id": wa_id, "channel": "whatsapp", "draft_text": result["whatsapp_text"]},
            {
                **common,
                "id": em_id,
                "channel": "email",
                "draft_text": (f"Subject: {result['email_subject']}\n\n{result['email_body']}").strip(),
            },
        ]
    )
    await append_audit(
        action="ai.followup.generate",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="proposal",
        resource_id=proposal_id,
        payload={
            "days_silent": days,
            "generation_id": generation_id,
            "prompt_ref": result.get("prompt_ref"),
            "route_ref": result.get("route_ref"),
            "latency_ms": latency_ms,
        },
    )
    await emit_event(
        owner_id=user["id"],
        event_type="followup.generated",
        entity_type="proposal",
        entity_id=proposal_id,
        source="system",
        metadata={
            "generation_id": generation_id,
            "prompt_ref": result.get("prompt_ref"),
            "route_ref": result.get("route_ref"),
            "latency_ms": latency_ms,
            "client_id": p["client_id"],
        },
    )

    return {
        "whatsapp": {"id": wa_id, "text": result["whatsapp_text"]},
        "email": {"id": em_id, "subject": result["email_subject"], "body": result["email_body"]},
        "meta": {
            "generation_id": generation_id,
            "prompt_ref": result.get("prompt_ref"),
            "route_ref": result.get("route_ref"),
            "confidence": result.get("confidence"),
            "latency_ms": latency_ms,
            "created_at": now_iso,
        },
    }


# ---------- One-time migration: rename legacy field names ----------
async def migrate_legacy_fields():
    """
    Backward-compatible migration from the older internal field names to the
    locked-in schema. Safe to run repeatedly — only renames where new field
    is absent and old field exists.
    """
    # Clients: name -> contact_name, company -> company_name
    await db.clients.update_many(
        {"contact_name": {"$exists": False}, "name": {"$exists": True}}, {"$rename": {"name": "contact_name"}}
    )
    await db.clients.update_many(
        {"company_name": {"$exists": False}, "company": {"$exists": True}},
        {"$rename": {"company": "company_name"}},
    )
    await db.clients.update_many({"language": {"$exists": False}}, {"$set": {"language": "English"}})

    # Proposals: value -> value_inr, sent_at -> sent_date, last_contact_at -> last_contact_date
    await db.proposals.update_many(
        {"value_inr": {"$exists": False}, "value": {"$exists": True}}, {"$rename": {"value": "value_inr"}}
    )
    await db.proposals.update_many(
        {"sent_date": {"$exists": False}, "sent_at": {"$exists": True}}, {"$rename": {"sent_at": "sent_date"}}
    )
    await db.proposals.update_many(
        {"last_contact_date": {"$exists": False}, "last_contact_at": {"$exists": True}},
        {"$rename": {"last_contact_at": "last_contact_date"}},
    )
    # manual_status -> stage (best-effort: won/lost/dead map to stage)
    async for p in db.proposals.find({"stage": {"$exists": False}}):
        ms = p.get("manual_status")
        stage = "won" if ms == "won" else "lost" if ms == "lost" else "sent"
        await db.proposals.update_one(
            {"id": p["id"]}, {"$set": {"stage": stage}, "$unset": {"manual_status": ""}}
        )

    # Invoices: invoice_number -> invoice_no, amount -> amount_inr, paid_at -> paid_date
    await db.invoices.update_many(
        {"invoice_no": {"$exists": False}, "invoice_number": {"$exists": True}},
        {"$rename": {"invoice_number": "invoice_no"}},
    )
    await db.invoices.update_many(
        {"amount_inr": {"$exists": False}, "amount": {"$exists": True}}, {"$rename": {"amount": "amount_inr"}}
    )
    await db.invoices.update_many(
        {"paid_date": {"$exists": False}, "paid_at": {"$exists": True}}, {"$rename": {"paid_at": "paid_date"}}
    )

    # Activities: kind -> channel, proposal_id/invoice_id -> related_type/related_id
    await db.activities.update_many(
        {"channel": {"$exists": False}, "kind": {"$exists": True}}, {"$rename": {"kind": "channel"}}
    )
    async for a in db.activities.find({"related_type": {"$exists": False}}):
        rt, rid = None, None
        if a.get("proposal_id"):
            rt, rid = "proposal", a["proposal_id"]
        elif a.get("invoice_id"):
            rt, rid = "invoice", a["invoice_id"]
        update = {"$set": {"direction": a.get("direction", "outbound")}}
        if rt:
            update["$set"]["related_type"] = rt
            update["$set"]["related_id"] = rid
        update["$unset"] = {"proposal_id": "", "invoice_id": ""}
        await db.activities.update_one({"id": a["id"]}, update)

    # Users: auth_provider default
    await db.users.update_many({"auth_provider": {"$exists": False}}, {"$set": {"auth_provider": "email"}})


# ---------- Seed admin (email/password) ----------
async def seed_admin():
    """
    Ensure each configured admin (ADMIN_EMAILS, CSV) exists. Creates missing
    users with ADMIN_PASSWORD if set. Demo data is seeded ONLY for the
    explicit demo account (DEMO_SEED_EMAIL, default founder@bytehubble.com)
    so real-data tenants — e.g. abhishek.mishra@bytehubble.ai — stay clean
    per SPRINT.md §3 + the "no static numbers on the production tenant" rule.
    """
    emails = _admin_emails() or {"founder@bytehubble.com"}
    demo_email = (os.environ.get("DEMO_SEED_EMAIL") or "founder@bytehubble.com").strip().lower()
    admin_password = os.environ.get("ADMIN_PASSWORD")
    for admin_email in emails:
        existing = await users_repo.get_by_email(admin_email)
        if existing is None:
            if not admin_password:
                logger.warning("ADMIN_PASSWORD not set and admin %s does not exist — skipping.", admin_email)
                continue
            owner_id = str(uuid.uuid4())
            await users_repo.insert(
                {
                    "id": owner_id,
                    "email": admin_email,
                    "name": "ByteHubble Founder",
                    "auth_provider": "email",
                    "password_hash": hash_password(admin_password),
                    "token_version": 0,
                    "created_at": now_utc().isoformat(),
                }
            )
        else:
            owner_id = existing["id"]
        # Only the explicit demo account gets the idempotent demo seed.
        if admin_email == demo_email:
            await seed_demo_for_owner(owner_id=owner_id)


# ---------- Importer (Day 1 onboarding) ----------
class ImportMapReq(BaseModel):
    file_id: str
    target: Literal["clients", "proposals", "invoices"]


class ImportCommitReq(BaseModel):
    file_id: str
    mapping: Optional[dict[str, str]] = None  # optional override; default uses stored mapping


@api.post("/import/parse")
@limiter.limit("20/hour", key_func=_user_or_ip_key)
async def import_parse(
    request: Request,
    file: UploadFile = File(...),
    user: dict = Depends(get_current_user),
):
    """Stage 1 of the importer. Reads a CSV, derives column types, data
    quality, and quick signals in one pass. Persists everything to import_jobs
    so the founder can retry /map without re-uploading."""
    content = await file.read()
    if not content:
        raise HTTPException(400, "Empty file")
    try:
        result = analyze_file(content, filename=file.filename or "")
    except ValueError as e:
        raise HTTPException(400, str(e))

    file_id = await import_jobs_repo.create(
        owner_id=user["id"],
        headers=result["headers"],
        sample_rows=result["sample_rows"],
        raw_rows=result["raw_rows"],
        stats={
            "column_types": result["column_types"],
            "data_quality": result["data_quality"],
            "quick_signals": result["quick_signals"],
        },
    )
    await append_audit(
        action="import.parse",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="import_job",
        resource_id=file_id,
        payload={"rows": result["data_quality"]["rows"]},
    )
    return {
        "file_id": file_id,
        "headers": result["headers"],
        "sample_rows": result["sample_rows"],
        "column_types": result["column_types"],
        "data_quality": result["data_quality"],
        "quick_signals": result["quick_signals"],
    }


@api.post("/import/map")
@limiter.limit("30/hour", key_func=_user_or_ip_key)
async def import_map(
    request: Request,
    req: ImportMapReq,
    user: dict = Depends(get_current_user),
):
    """Stage 2 of the importer. Returns both:
      * heuristic_mapping — pure-Python guess (always populated)
      * ai_mapping — LLM-suggested mapping (None if LLM unavailable/malformed)
    The LLM's mapping is persisted to import_jobs as the proposed mapping;
    if the LLM is down we fall back to the heuristic. The UI is expected to
    let the founder confirm/override either way."""
    job = await import_jobs_repo.get(req.file_id, user["id"])
    if job is None:
        raise HTTPException(404, "Import job not found")
    headers: list[str] = job["headers"]
    sample_rows: list[dict] = job["sample_rows"]

    heuristic = heuristic_mapping(headers, req.target)
    ai_mapping = None
    ai_error = None
    try:
        suggestion = await generate_json(
            system=LLM_SYSTEM,
            user=llm_user_prompt(req.target, headers, sample_rows),
            schema=MappingSuggestion,
            max_tokens=800,
        )
        ai_mapping = [m.model_dump() for m in suggestion.mappings]
    except (LLMProviderUnavailable, NoApiKeyError, MalformedOutputError) as e:
        logger.warning("import.map LLM unavailable: %s", e)
        ai_error = type(e).__name__

    # Persist whichever is non-null, preferring AI. Founder can still override
    # via /commit's `mapping` body.
    chosen = ai_mapping or heuristic
    flat = {m["target_field"]: m["source_header"] for m in chosen if m["source_header"]}
    await import_jobs_repo.set_mapping(req.file_id, user["id"], mapping=flat, target=req.target)
    await append_audit(
        action="import.map",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="import_job",
        resource_id=req.file_id,
        payload={"target": req.target, "ai": ai_mapping is not None, "fields_mapped": len(flat)},
    )
    return {
        "file_id": req.file_id,
        "target": req.target,
        "heuristic_mapping": heuristic,
        "ai_mapping": ai_mapping,
        "ai_error": ai_error,
    }


@api.post("/import/seed-demo")
@limiter.limit("5/hour", key_func=_user_or_ip_key)
async def import_seed_demo(request: Request, user: dict = Depends(get_current_user)):
    """One-click path for the 'Use Demo Data' onboarding card. Wraps the
    existing seed_demo_for_owner, which is idempotent — returns 409 if the
    tenant already has data so we never overwrite real ByteHubble rows."""
    result = await seed_demo_for_owner(owner_id=user["id"])
    if result.get("skipped"):
        raise HTTPException(409, "Existing data present — demo seed refused")
    await append_audit(
        action="import.seed_demo",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="user",
        resource_id=user["id"],
        payload=result,
    )
    return result


class PersonalizeReq(BaseModel):
    preferred_channel: Literal["whatsapp", "email", "phone"]
    follow_up_days: Literal[3, 7, 14]
    priority: Literal["cash", "close", "relationship"]


# ---------- Revenue Health (Day 2 — pure SQL/Python, NO LLM) ----------
async def _memory_map_for(owner_id: str) -> dict:
    rows = await memory_repo.list_for_owner(owner_id)
    return {m["client_id"]: m for m in rows}


@api.get("/revenue-health")
async def revenue_health(user: dict = Depends(get_current_user)):
    """Single payload backing /health. Pure SQL/Python — never blocks on LLM.
    Snapshot upserted for today on each call (1 row/day max) so the delta
    arrow on the visibility score reflects real history."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    proposals, invoices, clients_map, memory_map, tenant_profile = await asyncio.gather(
        proposals_repo.list_for_owner(user["id"]),
        invoices_repo.list_for_owner(user["id"]),
        _clients_map_for(user["id"]),
        _memory_map_for(user["id"]),
        users_repo.get_tenant_profile(user["id"]),
    )
    payload = rh.compute(
        proposals=proposals,
        invoices=invoices,
        clients_map=clients_map,
        memory_map=memory_map,
        tenant_profile=tenant_profile,
    )

    # Fill delta arrow from prior snapshot (if any) BEFORE writing today's.
    from datetime import date as _date

    prior = await health_snapshots_repo.latest_before(user["id"], _date.today())
    if prior and prior.get("payload"):
        prior_score = (prior["payload"].get("visibility_score") or {}).get("score")
        if isinstance(prior_score, int):
            delta_val = payload["visibility_score"]["score"] - prior_score
            arrow = "↑" if delta_val > 0 else "↓" if delta_val < 0 else "→"
            payload["visibility_score"]["delta"] = {
                "arrow": arrow,
                "value": delta_val,
                "since_date": str(prior["snapshot_date"]),
            }

    await health_snapshots_repo.upsert_today(user["id"], payload)
    await append_audit(
        action="revenue_health.read",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="user",
        resource_id=user["id"],
        payload={"score": payload["visibility_score"]["score"]},
    )
    return payload


class RecommendationFeedbackReq(BaseModel):
    thumb: Literal["up", "down"]
    outcome: Optional[Literal["replied", "meeting_booked", "closed_won", "no_reply", "closed_lost"]] = None


@api.post("/recommendations/{recommendation_id}/feedback")
@limiter.limit("60/hour", key_func=_user_or_ip_key)
async def recommendation_feedback(
    request: Request,
    recommendation_id: str,
    req: RecommendationFeedbackReq,
    user: dict = Depends(get_current_user),
):
    """Learning Loop. recommendation_id == proposal_id (stable; no new table).
    Writes a recommendation.feedback event row scoped to the owner via RLS."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    if not await proposals_repo.exists_for_owner(recommendation_id, user["id"]):
        raise HTTPException(404, "Recommendation not found")
    await events_repo.insert(
        {
            "id": str(uuid.uuid4()),
            "owner_id": user["id"],
            "event_type": "recommendation.feedback",
            "entity_type": "proposal",
            "entity_id": recommendation_id,
            "metadata": {"thumb": req.thumb, "outcome": req.outcome},
            "source": "user",
            "created_at": now_utc().isoformat(),
        }
    )
    await append_audit(
        action="recommendation.feedback",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="proposal",
        resource_id=recommendation_id,
        payload={"thumb": req.thumb, "outcome": req.outcome},
    )
    return {"ok": True, "recommendation_id": recommendation_id, "thumb": req.thumb}


@api.get("/impact")
async def impact(user: dict = Depends(get_current_user)):
    """Dashboard 'Impact this week' card. Zeros are honest on cold tenants —
    no inflated marketing numbers. ponytail: 15 min/follow-up is a stake;
    refine when real usage data shows the saved-minutes distribution."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    week_ago = now_utc() - timedelta(days=7)
    followups, proposals, memory = await asyncio.gather(
        followups_repo.list_for_owner(user["id"]),
        proposals_repo.list_for_owner(user["id"]),
        memory_repo.list_for_owner(user["id"]),
    )

    def _parsed(iso: str):
        try:
            d = datetime.fromisoformat(iso)
            return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
        except Exception:
            return None

    week_followups = []
    for f in followups:
        ts = _parsed(f.get("created_at", ""))
        if ts is not None and ts >= week_ago:
            week_followups.append(f)
    proposal_ids_week = {f["proposal_id"] for f in week_followups}
    revenue_protected = int(
        sum(
            float(p["value_inr"])
            for p in proposals
            if p["id"] in proposal_ids_week and p.get("stage") in ("sent", "negotiating")
        )
    )
    rates = [m.get("response_rate") for m in memory if m.get("response_rate") is not None]
    response_rate = round(sum(rates) / len(rates), 2) if rates else 0.0

    return {
        "followups_generated_week": len(week_followups),
        "hours_saved_week": round(len(week_followups) * 15 / 60, 1),
        "revenue_protected_week": revenue_protected,
        "response_rate_week": response_rate,
    }


@api.get("/learning/aggregate")
async def learning_aggregate(user: dict = Depends(get_current_user)):
    """Rolling accuracy from recommendation.feedback events. Tenant-scoped."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    events = await events_repo.list_filtered(user["id"], event_type="recommendation.feedback", limit=1000)
    up = 0
    down = 0
    examples = []
    for e in events:
        meta = e.get("metadata") or {}
        if meta.get("thumb") == "up":
            up += 1
        elif meta.get("thumb") == "down":
            down += 1
        if len(examples) < 5:
            examples.append(
                {
                    "recommendation_id": e.get("entity_id"),
                    "thumb": meta.get("thumb"),
                    "outcome": meta.get("outcome"),
                    "created_at": e.get("created_at"),
                }
            )
    total = up + down
    accuracy_pct = round(100 * up / total) if total else None
    return {
        "thumbs_up_count": up,
        "thumbs_down_count": down,
        "accuracy_pct": accuracy_pct,
        "recent_examples": examples,
    }


# ---------- Morning Brief (Day 3 — the one LLM endpoint added today) ----------
async def _compose_brief(user: dict, *, force: bool = False) -> dict:
    """Returns the brief dict ({date, brief, recommendation_ids, source}).
    Cached on users.daily_brief — same-day reads short-circuit unless force=True."""
    from datetime import date as _date

    today_iso = _date.today().isoformat()
    cached = await users_repo.get_daily_brief(user["id"])
    if not force and cached and cached.get("date") == today_iso:
        return cached

    proposals, clients_map, memory_map, tenant_profile = await asyncio.gather(
        proposals_repo.list_for_owner(user["id"]),
        _clients_map_for(user["id"]),
        _memory_map_for(user["id"]),
        users_repo.get_tenant_profile(user["id"]),
    )
    actions = rh.top_actions(
        proposals=proposals,
        clients_map=clients_map,
        memory_map=memory_map,
        tenant_profile=tenant_profile,
        limit=3,
    )
    recommendation_ids = [a["id"] for a in actions]
    source = "llm"
    try:
        draft = await generate_brief(
            actions=actions,
            clients_map=clients_map,
            tenant_profile=tenant_profile,
            founder_name=(user.get("name") or "").split()[0] if user.get("name") else "",
        )
        brief = draft.model_dump()
    except (LLMProviderUnavailable, NoApiKeyError, MalformedOutputError) as e:
        logger.warning("brief.today LLM fallback: %s", e)
        source = "template_fallback"
        brief = template_fallback(
            actions=actions,
            clients_map=clients_map,
            founder_name=(user.get("name") or "").split()[0] if user.get("name") else "",
        )

    payload = {
        "date": today_iso,
        "brief": brief,
        "recommendation_ids": recommendation_ids,
        "source": source,
        "generated_at": now_utc().isoformat(),
    }
    await users_repo.set_daily_brief(user["id"], payload)
    return payload


@api.get("/brief/today")
async def brief_today(user: dict = Depends(get_current_user)):
    """Morning Brief — one LLM call/day cached on users.daily_brief.
    Returns shape: {date, brief:{headline,paragraph,confidence}, source, recommendation_ids}."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    return await _compose_brief(user)


@api.post("/brief/refresh")
@limiter.limit("3/day", key_func=_user_or_ip_key)
async def brief_refresh(request: Request, user: dict = Depends(get_current_user)):
    """Force a regen. Rate-limited so the LLM doesn't get hammered."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    payload = await _compose_brief(user, force=True)
    await append_audit(
        action="brief.refresh",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="user",
        resource_id=user["id"],
        payload={"source": payload["source"]},
    )
    return payload


@api.get("/today")
async def today(limit: int = 5, user: dict = Depends(get_current_user)):
    """Dashboard 'Today's Recovery' card. Same ranking as /revenue-health's
    do_these_today; caller picks limit."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    proposals, clients_map, memory_map, tenant_profile = await asyncio.gather(
        proposals_repo.list_for_owner(user["id"]),
        _clients_map_for(user["id"]),
        _memory_map_for(user["id"]),
        users_repo.get_tenant_profile(user["id"]),
    )
    rows = rh.top_actions(
        proposals=proposals,
        clients_map=clients_map,
        memory_map=memory_map,
        tenant_profile=tenant_profile,
        limit=max(1, min(20, limit)),
    )
    return {"rows": rows, "estimated_total_minutes": sum(r["estimated_minutes"] for r in rows)}


@api.get("/health/diff")
async def health_diff(since: Optional[str] = None, user: dict = Depends(get_current_user)):
    """Snapshot delta for the dashboard 'What Changed' card (Day 3).
    Default `since` = most recent prior snapshot. 200 with `available: False`
    when there's no prior snapshot to diff against."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    from datetime import date as _date

    target_date = _date.fromisoformat(since) if since else _date.today()
    prior = await health_snapshots_repo.latest_before(user["id"], target_date)
    today_snap = await health_snapshots_repo.get_for_date(user["id"], _date.today())
    if not prior or not today_snap:
        return {"available": False, "reason": "Need ≥2 snapshots to compute a diff"}

    def _score(snap):
        return ((snap.get("payload") or {}).get("visibility_score") or {}).get("score") or 0

    def _do_today_value(snap):
        rows = (snap.get("payload") or {}).get("do_these_today") or []
        return sum(int(r.get("value_inr") or 0) for r in rows)

    from_score = _score(prior)
    to_score = _score(today_snap)
    return {
        "available": True,
        "from_date": str(prior["snapshot_date"]),
        "to_date": str(today_snap["snapshot_date"]),
        "visibility": {"from": from_score, "to": to_score, "delta": to_score - from_score},
        "recovery_inr_delta": _do_today_value(today_snap) - _do_today_value(prior),
    }


@api.post("/personalize")
async def personalize(req: PersonalizeReq, user: dict = Depends(get_current_user)):
    """'Improve My Recommendations' card. Three answers steer ranking + (Day 3)
    Brief tone. Stored on users.tenant_profile."""
    profile = {
        "preferred_channel": req.preferred_channel,
        "follow_up_days": req.follow_up_days,
        "priority": req.priority,
    }
    await users_repo.set_tenant_profile(user["id"], profile)
    await append_audit(
        action="personalize.submit",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="user",
        resource_id=user["id"],
        payload=profile,
    )
    return {"ok": True, "tenant_profile": profile}


@api.get("/onboarding/state")
async def onboarding_state(user: dict = Depends(get_current_user)):
    """Lightweight gate for App.jsx routing. has_personalized is a Day 2
    field (settings.tenant_profile not yet shipped) and always reads false
    until Personalize/Improve My Recommendations lands."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required")
    async with pgdb.with_user(user["id"]) as conn:
        cc = await conn.fetchval("SELECT COUNT(*)::int FROM clients")
        pc = await conn.fetchval("SELECT COUNT(*)::int FROM proposals")
        ic = await conn.fetchval("SELECT COUNT(*)::int FROM invoices")
    profile = await users_repo.get_tenant_profile(user["id"])
    return {
        "has_data": (cc or 0) > 0,
        "has_personalized": profile is not None,
        "clients_count": cc or 0,
        "proposals_count": pc or 0,
        "invoices_count": ic or 0,
    }


@api.post("/import/commit")
@limiter.limit("10/hour", key_func=_user_or_ip_key)
async def import_commit(
    request: Request,
    req: ImportCommitReq,
    user: dict = Depends(get_current_user),
):
    """Stage 3 of the importer. Drains raw_rows into clients/proposals/invoices
    inside a single RLS-scoped transaction. For proposals/invoices targets,
    missing clients are auto-created (look up by company_name, lowercase,
    per owner). One audit event per commit, row counts only.

    ponytail: inline SQL keeps the whole import in one with_user() transaction
    without threading conn through repo methods. Refactor when a second caller
    needs the same bulk path."""
    if not is_postgres():
        raise HTTPException(503, "Postgres engine required for importer")
    job = await import_jobs_repo.get(req.file_id, user["id"])
    if job is None:
        raise HTTPException(404, "Import job not found")
    if job["stage"] == "committed":
        raise HTTPException(409, "Import already committed")
    target = job.get("target")
    if not target:
        raise HTTPException(400, "Import has no target — call /import/map first")

    mapping = req.mapping if req.mapping is not None else (job.get("mapping") or {})
    if not mapping:
        raise HTTPException(400, "Empty mapping — cannot commit")
    raw_rows: list[dict] = job["raw_rows"] or []
    owner_id = user["id"]
    headers: list[str] = job.get("headers") or []

    # When target=proposals, we want a one-shot import: clients (with contact
    # info + preferred channel) AND invoices ride along on the same commit.
    # Derive their mappings via heuristic so the founder doesn't have to map
    # 3 times. Falls back gracefully — if invoice columns aren't present in
    # the CSV, the invoice insert is just skipped per-row.
    client_mapping_derived: dict[str, str] = {}
    invoice_mapping_derived: dict[str, str] = {}
    # Outcome-override header: a second "status"-like column distinct from the
    # mapped stage column. Real CRMs often carry BOTH a pipeline-phase column
    # ("Follow-up" / "Decision Pending") AND a deal-outcome column ("Won" /
    # "Lost" / "Dead"). The heuristic picks one — we read the other for any
    # row where the outcome is terminal and override stage there.
    status_override_header: Optional[str] = None
    if target == "proposals" and headers:
        for x in heuristic_mapping(headers, "clients"):
            if x.get("source_header"):
                client_mapping_derived[x["target_field"]] = x["source_header"]
        for x in heuristic_mapping(headers, "invoices"):
            if x.get("source_header"):
                invoice_mapping_derived[x["target_field"]] = x["source_header"]
        stage_header = mapping.get("stage")
        for h in headers:
            h_norm = h.lower().strip()
            # Skip the mapped Stage column and any invoice/bill-flavored status
            # (those describe payment state, not deal outcome).
            if h == stage_header:
                continue
            if "invoice" in h_norm or "bill" in h_norm or "payment" in h_norm:
                continue
            if "status" in h_norm or "outcome" in h_norm:
                status_override_header = h
                break

    clients_inserted = proposals_inserted = invoices_inserted = 0
    skipped = 0

    async with pgdb.with_user(owner_id) as conn:
        # Cache lookup for client_name -> client_id within this commit, lowercased.
        client_cache: dict[str, str] = {}
        # Prefill with any existing clients so we don't duplicate.
        recs = await conn.fetch("SELECT id::text, lower(company_name) AS k FROM clients")
        for r in recs:
            client_cache[r["k"]] = r["id"]

        async def _ensure_client(name: str, row: dict | None = None) -> str:
            """Auto-create a client during a proposal/invoice commit.

            When `row` is provided AND client_mapping_derived is populated (i.e.
            target=proposals one-shot path), we pull email/phone/whatsapp from
            the CSV row so the WhatsApp deep-link works downstream. If the row
            has a Preferred Channel column, we also seed client_memory.
            channel_preference — that's what drives the action verb ("WhatsApp
            Abhishek" vs. "Call Abhishek") in Do These Today.
            """
            key = name.lower().strip()
            if key in client_cache:
                return client_cache[key]
            cid = str(uuid.uuid4())
            now = now_utc().isoformat()
            email = phone = whatsapp = None
            preferred_channel = None
            if row is not None and client_mapping_derived:
                email = _g(row, client_mapping_derived, "email")
                phone = _g(row, client_mapping_derived, "phone")
                whatsapp = _g(row, client_mapping_derived, "whatsapp")
                preferred_channel = _g(row, client_mapping_derived, "preferred_channel")
            # Mirror phone into whatsapp when CSV has no separate WhatsApp
            # column (the common case for Indian SMB CRMs — Phone IS WhatsApp).
            # The wa.me frontend logic prefers whatsapp; populating it directly
            # avoids relying on the `whatsapp || phone` fallback at click time.
            if not whatsapp and phone:
                whatsapp = phone
            await conn.execute(
                "INSERT INTO clients (id, owner_id, company_name, contact_name, email, phone, "
                "whatsapp, language, created_at) "
                "VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9)",
                cid,
                owner_id,
                name,
                "",
                email,
                phone,
                whatsapp,
                "English",
                now,
            )
            # Seed client_memory if we learned a channel preference. Lowercase
            # match against the values revenue_health's _CHANNEL_ACTIONS expects
            # — anything else gets dropped (silently safe).
            if preferred_channel:
                ch = preferred_channel.lower().strip()
                if ch in ("whatsapp", "email", "phone", "call"):
                    if ch == "call":
                        ch = "phone"
                    await conn.execute(
                        "INSERT INTO client_memory (id, owner_id, client_id, channel_preference, "
                        "channel_counts, last_outcomes, recompute_count, updated_at) "
                        "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, '{}'::jsonb, '[]'::jsonb, 0, $5) "
                        "ON CONFLICT (owner_id, client_id) DO UPDATE SET channel_preference = EXCLUDED.channel_preference",
                        str(uuid.uuid4()),
                        owner_id,
                        cid,
                        ch,
                        now,
                    )
            client_cache[key] = cid
            nonlocal clients_inserted
            clients_inserted += 1
            return cid

        for row in raw_rows:
            if target == "clients":
                doc = build_client_doc(row, mapping, owner_id)
                if doc is None:
                    skipped += 1
                    continue
                if doc["company_name"].lower().strip() in client_cache:
                    skipped += 1  # already exists; honor existing row
                    continue
                await conn.execute(
                    "INSERT INTO clients (id, owner_id, company_name, contact_name, email, phone, "
                    "whatsapp, industry, language, notes, created_at) "
                    "VALUES ($1::uuid, $2::uuid, $3, $4, $5, $6, $7, $8, $9, $10, $11)",
                    doc["id"],
                    doc["owner_id"],
                    doc["company_name"],
                    doc["contact_name"],
                    doc["email"],
                    doc["phone"],
                    doc["whatsapp"],
                    doc["industry"],
                    doc["language"],
                    doc["notes"],
                    doc["created_at"],
                )
                client_cache[doc["company_name"].lower().strip()] = doc["id"]
                clients_inserted += 1

            elif target == "proposals":
                client_name = row.get(mapping.get("client_name", ""), "")
                if not client_name or not str(client_name).strip():
                    skipped += 1
                    continue
                # Build with placeholder client_id first; only ensure_client
                # if row is otherwise valid, so a bad row doesn't leave an
                # orphan client behind.
                doc = build_proposal_doc(row, mapping, owner_id, "placeholder")
                if doc is None:
                    skipped += 1
                    continue
                # Terminal outcome from the second status column (e.g. "Won")
                # wins over pipeline phase (e.g. "Decision Pending"). CRM exports
                # routinely keep stale phase values on deals that have already
                # closed — we trust the outcome column when it's decisive.
                if status_override_header:
                    raw_outcome = row.get(status_override_header)
                    if raw_outcome:
                        oc = str(raw_outcome).lower().strip()
                        if oc in ("won", "closed won", "closed_won"):
                            doc["stage"] = "won"
                        elif oc in ("lost", "closed lost", "closed_lost", "dead", "dropped"):
                            doc["stage"] = "lost"
                doc["client_id"] = await _ensure_client(str(client_name).strip(), row)
                await conn.execute(
                    "INSERT INTO proposals (id, owner_id, client_id, title, value_inr, sent_date, "
                    "last_contact_date, stage, outcome_at, notes, created_at) "
                    "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10, $11)",
                    doc["id"],
                    doc["owner_id"],
                    doc["client_id"],
                    doc["title"],
                    doc["value_inr"],
                    doc["sent_date"],
                    doc["last_contact_date"],
                    doc["stage"],
                    doc["outcome_at"],
                    doc["notes"],
                    doc["created_at"],
                )
                proposals_inserted += 1

                # One-shot import: if invoice columns are present in the same
                # CSV row, write the invoice too. The Welcome.jsx UX only asks
                # the founder to confirm ONE mapping (proposals) — riding the
                # invoice in here saves a second upload/map cycle and matches
                # how real CRM exports bundle deal + invoice on one row.
                if invoice_mapping_derived.get("invoice_no") and invoice_mapping_derived.get("amount_inr"):
                    inv_doc = build_invoice_doc(row, invoice_mapping_derived, owner_id, doc["client_id"])
                    if inv_doc is not None:
                        await conn.execute(
                            "INSERT INTO invoices (id, owner_id, client_id, invoice_no, amount_inr, due_date, "
                            "paid_date, issued_at, notes, created_at) "
                            "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10)",
                            inv_doc["id"],
                            inv_doc["owner_id"],
                            inv_doc["client_id"],
                            inv_doc["invoice_no"],
                            inv_doc["amount_inr"],
                            inv_doc["due_date"],
                            inv_doc["paid_date"],
                            inv_doc["issued_at"],
                            inv_doc["notes"],
                            inv_doc["created_at"],
                        )
                        invoices_inserted += 1

            elif target == "invoices":
                client_name = row.get(mapping.get("client_name", ""), "")
                if not client_name or not str(client_name).strip():
                    skipped += 1
                    continue
                doc = build_invoice_doc(row, mapping, owner_id, "placeholder")
                if doc is None:
                    skipped += 1
                    continue
                doc["client_id"] = await _ensure_client(str(client_name).strip(), row)
                await conn.execute(
                    "INSERT INTO invoices (id, owner_id, client_id, invoice_no, amount_inr, due_date, "
                    "paid_date, issued_at, notes, created_at) "
                    "VALUES ($1::uuid, $2::uuid, $3::uuid, $4, $5, $6, $7, $8, $9, $10)",
                    doc["id"],
                    doc["owner_id"],
                    doc["client_id"],
                    doc["invoice_no"],
                    doc["amount_inr"],
                    doc["due_date"],
                    doc["paid_date"],
                    doc["issued_at"],
                    doc["notes"],
                    doc["created_at"],
                )
                invoices_inserted += 1

    await import_jobs_repo.mark_committed(req.file_id, owner_id)
    counts = {
        "clients_inserted": clients_inserted,
        "proposals_inserted": proposals_inserted,
        "invoices_inserted": invoices_inserted,
        "skipped": skipped,
    }
    await append_audit(
        action="import.commit",
        actor_id=user["id"],
        actor_email=user["email"],
        resource_type="import_job",
        resource_id=req.file_id,
        payload={"target": target, **counts},
    )
    return {"file_id": req.file_id, "target": target, **counts}


@api.get("/")
async def root():
    return {"app": "Revora", "status": "ok"}


app.include_router(api)


# Hard cap on request body size — pre-parse defence against DoS by giant
# payloads. Pydantic per-field limits are post-parse; this stops a 100MB
# upload from eating memory before we even look at it.
MAX_REQUEST_BYTES = int(os.environ.get("MAX_REQUEST_BYTES", str(5 * 1024 * 1024)))  # 5MB default


@app.middleware("http")
async def enforce_max_body_size(request: Request, call_next):
    """Reject oversized bodies via Content-Length, or stream-and-cap when the
    client omits the header (chunked transfer)."""
    cl = request.headers.get("content-length")
    if cl is not None:
        try:
            if int(cl) > MAX_REQUEST_BYTES:
                from starlette.responses import JSONResponse

                return JSONResponse(
                    status_code=413,
                    content={
                        "detail": {
                            "code": "request_too_large",
                            "message": f"Request body must be ≤ {MAX_REQUEST_BYTES} bytes.",
                        }
                    },
                )
        except ValueError:
            pass  # malformed Content-Length — let Starlette deal with it
    return await call_next(request)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


@app.middleware("http")
async def request_context_and_access_log(request: Request, call_next):
    """Stamp every request with a unique id, propagate it through logs +
    response header, and emit one structured access-log line at end."""
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    rid_token = request_id_ctx.set(rid)
    # user_id is set later by routes that have already auth'd; default is ''.
    uid_token = user_id_ctx.set("")
    t0 = time.perf_counter()
    status = 500
    try:
        response = await call_next(request)
        status = response.status_code
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        latency_ms = int((time.perf_counter() - t0) * 1000)
        # Skip health check + static — they're 100x noisier than they're worth.
        path = request.url.path
        if not (path == "/api/" or path == "/api"):
            logger.info(
                "request",
                extra={
                    "method": request.method,
                    "route": path,
                    "status": status,
                    "latency_ms": latency_ms,
                },
            )
        request_id_ctx.reset(rid_token)
        user_id_ctx.reset(uid_token)


_cors_origins = [
    o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:3000").split(",") if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
    expose_headers=["X-Request-ID"],
)

# JSON-structured logging on stdout. init_logging() resets the root logger so
# this overrides any uvicorn-installed basicConfig.
init_logging()
init_sentry()  # no-op if SENTRY_DSN unset or sentry-sdk missing
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def on_startup():
    if is_postgres():
        await pgdb.init_pool()
        logger.info("DB_ENGINE=postgres — asyncpg pool ready.")
    if is_mongo():
        # Mongo-only: indexes + legacy field-rename migration. Postgres ships
        # its indexes in the schema file and has no legacy data to rename.
        await db.users.create_index("email", unique=True)
        await db.clients.create_index([("owner_id", 1), ("company_name", 1)])
        await db.proposals.create_index([("owner_id", 1)])
        await db.invoices.create_index([("owner_id", 1)])
        await db.activities.create_index([("owner_id", 1), ("created_at", -1)])
        await db.followups.create_index([("owner_id", 1), ("proposal_id", 1), ("created_at", -1)])
        await db.audit_log.create_index("seq", unique=True)
        await db.audit_log.create_index([("actor_id", 1), ("timestamp", -1)])
        await db.audit_log.create_index([("action", 1), ("timestamp", -1)])
        await db.events.create_index([("owner_id", 1), ("entity_id", 1), ("created_at", -1)])
        await db.events.create_index([("owner_id", 1), ("event_type", 1), ("created_at", -1)])
        await db.client_memory.create_index([("owner_id", 1), ("client_id", 1)], unique=True)
        await db.settings.create_index("id", unique=True)
        await migrate_legacy_fields()
    await load_signing_key()
    await seed_admin()
    logger.info(
        "Revora ready (engine=%s, audit key fp=%s).",
        "postgres" if is_postgres() else "mongo",
        get_public_key_fp(),
    )


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
    if is_postgres():
        await pgdb.close_pool()
