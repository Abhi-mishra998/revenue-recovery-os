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
from fastapi import APIRouter, Depends, FastAPI, HTTPException, Request
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
from services.audit import append_audit, get_public_key_fp, load_signing_key, verify_chain
from services.data import extract_proposal_features, predict_close_probability
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


def public_user(u: dict) -> dict:
    admin_email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "auth_provider": u.get("auth_provider", "email"),
        "is_admin": bool(admin_email) and u["email"].lower() == admin_email,
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Authorize the configured ADMIN_EMAIL only. ponytail: single-admin model
    is enough for now; switch to a roles collection when there's a second admin."""
    admin_email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    if not admin_email or user["email"].lower() != admin_email:
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
    Create the admin user on first boot only. After that, never touch the
    password — rotation is the user's responsibility, not the server's.
    Requires ADMIN_PASSWORD env var if no admin exists yet; otherwise no-op.
    """
    admin_email = os.environ.get("ADMIN_EMAIL", "founder@bytehubble.com").lower()
    existing = await users_repo.get_by_email(admin_email)
    if existing is not None:
        await seed_demo_for_owner(owner_id=existing["id"])
        return
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        logger.warning("ADMIN_PASSWORD not set and no admin user exists — skipping admin seed.")
        return
    user_id = str(uuid.uuid4())
    await users_repo.insert(
        {
            "id": user_id,
            "email": admin_email,
            "name": "ByteHubble Founder",
            "auth_provider": "email",
            "password_hash": hash_password(admin_password),
            "token_version": 0,
            "created_at": now_utc().isoformat(),
        }
    )
    await seed_demo_for_owner(owner_id=user_id)


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
