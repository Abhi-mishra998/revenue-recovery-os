from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
import uuid
import bcrypt
import httpx
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from services.seed import seed_demo_for_owner
from services.ai import generate_proposal_followup, NoApiKeyError
from services.audit import append_audit, load_signing_key, verify_chain, get_public_key_fp

# ---------- MongoDB ----------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
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
                JWT_SECRET, algorithms=[JWT_ALG],
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
    user = await db.users.find_one({"id": payload["sub"]})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    if int(payload.get("tv", 0)) != int(user.get("token_version", 0)):
        raise HTTPException(status_code=401, detail="Token revoked")
    user.pop("_id", None)
    user.pop("password_hash", None)
    return user


def public_user(u: dict) -> dict:
    return {
        "id": u["id"],
        "email": u["email"],
        "name": u.get("name", ""),
        "auth_provider": u.get("auth_provider", "email"),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """Authorize the configured ADMIN_EMAIL only. ponytail: single-admin model
    is enough for now; switch to a roles collection when there's a second admin."""
    admin_email = (os.environ.get("ADMIN_EMAIL") or "").strip().lower()
    if not admin_email or user["email"].lower() != admin_email:
        raise HTTPException(status_code=403, detail="Admin only")
    return user


async def assert_owns_client(client_id: str, user: dict) -> None:
    if not await db.clients.find_one({"id": client_id, "owner_id": user["id"]}, {"_id": 1}):
        raise HTTPException(404, "Client not found")


async def assert_owns(collection: str, doc_id: str, user: dict) -> None:
    if not await db[collection].find_one({"id": doc_id, "owner_id": user["id"]}, {"_id": 1}):
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
    existing = await db.users.find_one({"email": email})
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
    await db.users.insert_one(doc)
    await append_audit(db, action="auth.register", actor_id=user_id, actor_email=email,
                       resource_type="user", resource_id=user_id, payload={"name": req.name})
    token = create_access_token(user_id, email, 0)
    return {"token": token, "user": public_user(doc)}


@api.post("/auth/login")
@limiter.limit("30/minute")
async def login(request: Request, req: LoginReq):
    email = req.email.lower()
    user = await db.users.find_one({"email": email})
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

    user = await db.users.find_one({"email": email})
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
        await db.users.insert_one(user.copy())
        await append_audit(db, action="auth.google_session.register",
                           actor_id=user["id"], actor_email=email,
                           resource_type="user", resource_id=user["id"],
                           payload={"name": name})
    elif user.get("auth_provider") != "google":
        # Refuse silent account linking — a Google account for a password user's
        # email would otherwise take over that account.
        raise HTTPException(status_code=409, detail="This email is registered with a password. Please sign in with your password.")

    token = create_access_token(user["id"], email, user.get("token_version", 0))
    return {"token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


@api.post("/auth/logout", status_code=204)
async def logout(user: dict = Depends(get_current_user)):
    """Revoke every outstanding token for this user by bumping token_version."""
    await db.users.update_one({"id": user["id"]}, {"$inc": {"token_version": 1}})
    await append_audit(db, action="auth.logout", actor_id=user["id"], actor_email=user["email"])
    return None


# ---------- Clients ----------
@api.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)):
    rows = await db.clients.find({"owner_id": user["id"]}, {"_id": 0}).sort("company_name", 1).to_list(2000)
    return rows


@api.post("/clients")
async def create_client(payload: ClientCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    await db.clients.insert_one(doc.copy())
    doc.pop("_id", None)
    await append_audit(db, action="client.create", actor_id=user["id"], actor_email=user["email"],
                       resource_type="client", resource_id=doc["id"], payload=payload.model_dump())
    return doc


@api.get("/clients/{client_id}")
async def get_client(client_id: str, user: dict = Depends(get_current_user)):
    c = await db.clients.find_one({"id": client_id, "owner_id": user["id"]}, {"_id": 0})
    if not c:
        raise HTTPException(404, "Client not found")
    proposals = await db.proposals.find({"client_id": client_id, "owner_id": user["id"]}, {"_id": 0}).to_list(500)
    invoices = await db.invoices.find({"client_id": client_id, "owner_id": user["id"]}, {"_id": 0}).to_list(500)
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
    res = await db.clients.update_one({"id": client_id, "owner_id": user["id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Client not found")
    c = await db.clients.find_one({"id": client_id, "owner_id": user["id"]}, {"_id": 0})
    await append_audit(db, action="client.update", actor_id=user["id"], actor_email=user["email"],
                       resource_type="client", resource_id=client_id, payload=updates)
    return c


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(get_current_user)):
    res = await db.clients.delete_one({"id": client_id, "owner_id": user["id"]})
    if res.deleted_count:
        await append_audit(db, action="client.delete", actor_id=user["id"], actor_email=user["email"],
                           resource_type="client", resource_id=client_id)
    return {"ok": True}


# ---------- Proposals ----------
@api.get("/proposals")
async def list_proposals(user: dict = Depends(get_current_user)):
    rows = await db.proposals.find({"owner_id": user["id"]}, {"_id": 0}).to_list(5000)
    clients_map = {c["id"]: c async for c in db.clients.find({"owner_id": user["id"]}, {"_id": 0})}
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
    await db.proposals.insert_one(doc.copy())
    await append_audit(db, action="proposal.create", actor_id=user["id"], actor_email=user["email"],
                       resource_type="proposal", resource_id=doc["id"], payload=payload.model_dump())
    return serialize_proposal({k: v for k, v in doc.items() if k != "_id"})


@api.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    p = await db.proposals.find_one({"id": proposal_id, "owner_id": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Proposal not found")
    clients_map = {p["client_id"]: await db.clients.find_one({"id": p["client_id"], "owner_id": user["id"]}, {"_id": 0}) or {}}
    return serialize_proposal(p, clients_map)


@api.patch("/proposals/{proposal_id}")
async def update_proposal(proposal_id: str, payload: ProposalUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    res = await db.proposals.update_one({"id": proposal_id, "owner_id": user["id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Proposal not found")
    p = await db.proposals.find_one({"id": proposal_id, "owner_id": user["id"]}, {"_id": 0})
    await append_audit(db, action="proposal.update", actor_id=user["id"], actor_email=user["email"],
                       resource_type="proposal", resource_id=proposal_id, payload=updates)
    return serialize_proposal(p)


@api.delete("/proposals/{proposal_id}")
async def delete_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    res = await db.proposals.delete_one({"id": proposal_id, "owner_id": user["id"]})
    if res.deleted_count:
        await append_audit(db, action="proposal.delete", actor_id=user["id"], actor_email=user["email"],
                           resource_type="proposal", resource_id=proposal_id)
    return {"ok": True}


# ---------- Invoices ----------
@api.get("/invoices")
async def list_invoices(user: dict = Depends(get_current_user)):
    rows = await db.invoices.find({"owner_id": user["id"]}, {"_id": 0}).to_list(5000)
    clients_map = {c["id"]: c async for c in db.clients.find({"owner_id": user["id"]}, {"_id": 0})}
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
    await db.invoices.insert_one(doc.copy())
    await append_audit(db, action="invoice.create", actor_id=user["id"], actor_email=user["email"],
                       resource_type="invoice", resource_id=doc["id"], payload=payload.model_dump())
    return serialize_invoice({k: v for k, v in doc.items() if k != "_id"})


@api.get("/invoices/{invoice_id}")
async def get_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    inv = await db.invoices.find_one({"id": invoice_id, "owner_id": user["id"]}, {"_id": 0})
    if not inv:
        raise HTTPException(404, "Invoice not found")
    return serialize_invoice(inv)


@api.patch("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    res = await db.invoices.update_one({"id": invoice_id, "owner_id": user["id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Invoice not found")
    inv = await db.invoices.find_one({"id": invoice_id, "owner_id": user["id"]}, {"_id": 0})
    await append_audit(db, action="invoice.update", actor_id=user["id"], actor_email=user["email"],
                       resource_type="invoice", resource_id=invoice_id, payload=updates)
    return serialize_invoice(inv)


@api.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    res = await db.invoices.delete_one({"id": invoice_id, "owner_id": user["id"]})
    if res.deleted_count:
        await append_audit(db, action="invoice.delete", actor_id=user["id"], actor_email=user["email"],
                           resource_type="invoice", resource_id=invoice_id)
    return {"ok": True}


# ---------- Activities ----------
@api.get("/activities")
async def list_activities(user: dict = Depends(get_current_user)):
    rows = await db.activities.find({"owner_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return rows


@api.post("/activities")
async def create_activity(payload: ActivityCreate, user: dict = Depends(get_current_user)):
    await assert_owns_client(payload.client_id, user)
    if payload.related_type and payload.related_id:
        await assert_owns(payload.related_type + "s", payload.related_id, user)
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    await db.activities.insert_one(doc.copy())
    doc.pop("_id", None)
    await append_audit(db, action="activity.create", actor_id=user["id"], actor_email=user["email"],
                       resource_type="activity", resource_id=doc["id"], payload=payload.model_dump())
    return doc


# ---------- Dashboard ----------
@api.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    proposals = await db.proposals.find({"owner_id": user["id"]}, {"_id": 0}).to_list(10000)
    invoices = await db.invoices.find({"owner_id": user["id"]}, {"_id": 0}).to_list(10000)
    clients_map = {c["id"]: c async for c in db.clients.find({"owner_id": user["id"]}, {"_id": 0})}

    total_pipeline = 0.0
    active_inr = 0.0
    cold_inr = 0.0
    dead_inr = 0.0
    cold_count = 0
    by_status_count = {"active": 0, "cold": 0, "dead": 0}
    by_stage_count = {"sent": 0, "negotiating": 0, "won": 0, "lost": 0}
    at_risk_candidates = []

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

    # Top 5 at-risk proposals: rank by value × days_silent (urgency).
    def _rank(item):
        p, _, v = item
        d = max(1, days_since(p["last_contact_date"]))
        return v * d

    at_risk_candidates.sort(key=_rank, reverse=True)
    top_at_risk = []
    for p, status, value in at_risk_candidates[:5]:
        c = clients_map.get(p["client_id"], {})
        top_at_risk.append({
            "id": p["id"],
            "title": p["title"],
            "value_inr": value,
            "status": status,
            "days_silent": days_since(p["last_contact_date"]),
            "stage": p.get("stage", "sent"),
            "client_company_name": c.get("company_name", "Unknown"),
            "client_contact_name": c.get("contact_name", ""),
        })

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


# ---------- Admin: AI kill-switch ----------
# ponytail: per-call DB lookup on a single tiny doc (~1ms). Cache in-process
# if it shows up in profiles.
async def ai_killswitch_enabled() -> bool:
    doc = await db.settings.find_one({"id": "global"}, {"ai_killswitch": 1})
    return bool(doc and doc.get("ai_killswitch"))


class KillSwitchReq(BaseModel):
    enabled: bool


@api.get("/admin/killswitch")
async def get_killswitch(admin: dict = Depends(require_admin)):
    return {"ai_killswitch": await ai_killswitch_enabled()}


@api.post("/admin/killswitch")
async def set_killswitch(req: KillSwitchReq, admin: dict = Depends(require_admin)):
    await db.settings.update_one(
        {"id": "global"},
        {"$set": {"ai_killswitch": req.enabled}, "$setOnInsert": {"id": "global"}},
        upsert=True,
    )
    await append_audit(db, action="admin.killswitch.set",
                       actor_id=admin["id"], actor_email=admin["email"],
                       payload={"enabled": req.enabled})
    return {"ai_killswitch": req.enabled}


# ---------- Admin: audit log ----------
@api.get("/admin/audit-log/verify")
async def admin_audit_verify(limit: Optional[int] = None, admin: dict = Depends(require_admin)):
    """Re-walk the audit chain and report hash/signature integrity."""
    return await verify_chain(db, limit=limit)


@api.get("/admin/audit-log")
async def admin_audit_list(
    page: int = 1, page_size: int = 50, admin: dict = Depends(require_admin),
):
    """Paginated read of audit records, newest first."""
    page = max(1, page)
    page_size = max(1, min(500, page_size))
    skip = (page - 1) * page_size
    total = await db.audit_log.count_documents({})
    rows = await db.audit_log.find(
        {}, {"_id": 0},
    ).sort("seq", -1).skip(skip).limit(page_size).to_list(page_size)
    return {
        "page": page, "page_size": page_size, "total": total,
        "public_key_fp": get_public_key_fp(),
        "records": rows,
    }


@api.post("/proposals/{proposal_id}/generate-followup")
@limiter.limit("10/hour", key_func=_user_or_ip_key)
async def generate_followup_for_proposal(request: Request, proposal_id: str, user: dict = Depends(get_current_user)):
    """
    Generate TWO drafts (WhatsApp + Email) for a proposal using the configured LLM.
    Saves each draft to a FollowUp record. Never sends anything.
    """
    if await ai_killswitch_enabled():
        raise HTTPException(status_code=503, detail="AI generation is currently disabled by the administrator.")
    p = await db.proposals.find_one({"id": proposal_id, "owner_id": user["id"]})
    if not p:
        raise HTTPException(404, "Proposal not found")
    c = await db.clients.find_one({"id": p["client_id"], "owner_id": user["id"]})
    if not c:
        raise HTTPException(404, "Client not found")

    days = max(0, days_since(p["last_contact_date"]))

    try:
        result = await generate_proposal_followup(
            sender_name=(user.get("name") or "Founder").split()[0],
            recipient_contact=c.get("contact_name") or "there",
            recipient_company=c.get("company_name") or "your company",
            industry=c.get("industry"),
            title=p["title"],
            value_inr=float(p["value_inr"]),
            days_silent=days,
        )
    except NoApiKeyError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception("AI generation failed")
        raise HTTPException(status_code=502, detail=f"AI generation failed: {e}")

    now_iso = now_utc().isoformat()
    wa_id = str(uuid.uuid4())
    em_id = str(uuid.uuid4())
    await db.followups.insert_many([
        {
            "id": wa_id, "owner_id": user["id"],
            "proposal_id": proposal_id, "invoice_id": None,
            "channel": "whatsapp",
            "draft_text": result["whatsapp_text"],
            "created_at": now_iso,
        },
        {
            "id": em_id, "owner_id": user["id"],
            "proposal_id": proposal_id, "invoice_id": None,
            "channel": "email",
            "draft_text": (f"Subject: {result['email_subject']}\n\n{result['email_body']}").strip(),
            "created_at": now_iso,
        },
    ])
    await append_audit(db, action="ai.followup.generate",
                       actor_id=user["id"], actor_email=user["email"],
                       resource_type="proposal", resource_id=proposal_id,
                       payload={"days_silent": days, "wa_followup_id": wa_id, "email_followup_id": em_id})

    return {
        "whatsapp": {"id": wa_id, "text": result["whatsapp_text"]},
        "email": {"id": em_id, "subject": result["email_subject"], "body": result["email_body"]},
    }


# ---------- One-time migration: rename legacy field names ----------
async def migrate_legacy_fields():
    """
    Backward-compatible migration from the older internal field names to the
    locked-in schema. Safe to run repeatedly — only renames where new field
    is absent and old field exists.
    """
    # Clients: name -> contact_name, company -> company_name
    await db.clients.update_many({"contact_name": {"$exists": False}, "name": {"$exists": True}}, {"$rename": {"name": "contact_name"}})
    await db.clients.update_many({"company_name": {"$exists": False}, "company": {"$exists": True}}, {"$rename": {"company": "company_name"}})
    await db.clients.update_many({"language": {"$exists": False}}, {"$set": {"language": "English"}})

    # Proposals: value -> value_inr, sent_at -> sent_date, last_contact_at -> last_contact_date
    await db.proposals.update_many({"value_inr": {"$exists": False}, "value": {"$exists": True}}, {"$rename": {"value": "value_inr"}})
    await db.proposals.update_many({"sent_date": {"$exists": False}, "sent_at": {"$exists": True}}, {"$rename": {"sent_at": "sent_date"}})
    await db.proposals.update_many({"last_contact_date": {"$exists": False}, "last_contact_at": {"$exists": True}}, {"$rename": {"last_contact_at": "last_contact_date"}})
    # manual_status -> stage (best-effort: won/lost/dead map to stage)
    async for p in db.proposals.find({"stage": {"$exists": False}}):
        ms = p.get("manual_status")
        stage = "won" if ms == "won" else "lost" if ms == "lost" else "sent"
        await db.proposals.update_one({"id": p["id"]}, {"$set": {"stage": stage}, "$unset": {"manual_status": ""}})

    # Invoices: invoice_number -> invoice_no, amount -> amount_inr, paid_at -> paid_date
    await db.invoices.update_many({"invoice_no": {"$exists": False}, "invoice_number": {"$exists": True}}, {"$rename": {"invoice_number": "invoice_no"}})
    await db.invoices.update_many({"amount_inr": {"$exists": False}, "amount": {"$exists": True}}, {"$rename": {"amount": "amount_inr"}})
    await db.invoices.update_many({"paid_date": {"$exists": False}, "paid_at": {"$exists": True}}, {"$rename": {"paid_at": "paid_date"}})

    # Activities: kind -> channel, proposal_id/invoice_id -> related_type/related_id
    await db.activities.update_many({"channel": {"$exists": False}, "kind": {"$exists": True}}, {"$rename": {"kind": "channel"}})
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
    existing = await db.users.find_one({"email": admin_email})
    if existing is not None:
        await seed_demo_for_owner(db, existing["id"])
        return
    admin_password = os.environ.get("ADMIN_PASSWORD")
    if not admin_password:
        logger.warning("ADMIN_PASSWORD not set and no admin user exists — skipping admin seed.")
        return
    user_id = str(uuid.uuid4())
    await db.users.insert_one({
        "id": user_id, "email": admin_email,
        "name": "ByteHubble Founder",
        "auth_provider": "email",
        "password_hash": hash_password(admin_password),
        "created_at": now_utc().isoformat(),
    })
    await seed_demo_for_owner(db, user_id)


@api.get("/")
async def root():
    return {"app": "Revora", "status": "ok"}


app.include_router(api)


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault("X-Content-Type-Options", "nosniff")
    response.headers.setdefault("X-Frame-Options", "DENY")
    response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
    response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
    response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
    return response


_cors_origins = [o.strip() for o in os.environ.get('CORS_ORIGINS', 'http://localhost:3000').split(',') if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)


@app.on_event("startup")
async def on_startup():
    await db.users.create_index("email", unique=True)
    await db.clients.create_index([("owner_id", 1), ("company_name", 1)])
    await db.proposals.create_index([("owner_id", 1)])
    await db.invoices.create_index([("owner_id", 1)])
    await db.activities.create_index([("owner_id", 1), ("created_at", -1)])
    await db.followups.create_index([("owner_id", 1), ("proposal_id", 1), ("created_at", -1)])
    await db.audit_log.create_index("seq", unique=True)
    await db.audit_log.create_index([("actor_id", 1), ("timestamp", -1)])
    await db.audit_log.create_index([("action", 1), ("timestamp", -1)])
    await db.settings.create_index("id", unique=True)
    await migrate_legacy_fields()
    await load_signing_key(db)
    await seed_admin()
    logger.info("Revora ready (audit key fp=%s).", get_public_key_fp())


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
