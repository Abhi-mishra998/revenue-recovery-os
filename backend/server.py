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

from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, EmailStr

from services.seed import seed_demo_for_owner

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


def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id,
        "email": email,
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


# ---------- Status compute (RULE: never typed by user) ----------
def compute_proposal_status(last_contact_date: str) -> str:
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
class RegisterReq(BaseModel):
    email: EmailStr
    password: str
    name: str


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class GoogleSessionReq(BaseModel):
    session_id: str


class ClientCreate(BaseModel):
    company_name: str
    contact_name: str
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    industry: Optional[str] = None
    language: str = "English"
    notes: Optional[str] = None


class ClientUpdate(BaseModel):
    company_name: Optional[str] = None
    contact_name: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    whatsapp: Optional[str] = None
    industry: Optional[str] = None
    language: Optional[str] = None
    notes: Optional[str] = None


ProposalStage = Literal["sent", "negotiating", "won", "lost"]


class ProposalCreate(BaseModel):
    client_id: str
    title: str
    value_inr: float
    sent_date: Optional[str] = None
    last_contact_date: Optional[str] = None
    stage: ProposalStage = "sent"
    notes: Optional[str] = None


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    value_inr: Optional[float] = None
    sent_date: Optional[str] = None
    last_contact_date: Optional[str] = None
    stage: Optional[ProposalStage] = None
    notes: Optional[str] = None


class InvoiceCreate(BaseModel):
    client_id: str
    invoice_no: str
    amount_inr: float
    due_date: str
    paid_date: Optional[str] = None
    notes: Optional[str] = None


class InvoiceUpdate(BaseModel):
    invoice_no: Optional[str] = None
    amount_inr: Optional[float] = None
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    notes: Optional[str] = None


ActivityChannel = Literal["call", "whatsapp", "email", "meeting", "note"]
ActivityDirection = Literal["inbound", "outbound", "internal"]


class ActivityCreate(BaseModel):
    client_id: str
    related_type: Optional[Literal["proposal", "invoice"]] = None
    related_id: Optional[str] = None
    channel: ActivityChannel
    direction: ActivityDirection = "outbound"
    summary: str


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
async def register(req: RegisterReq):
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
        "created_at": now_utc().isoformat(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(user_id, email)
    return {"token": token, "user": public_user(doc)}


@api.post("/auth/login")
async def login(req: LoginReq):
    email = req.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], email)
    return {"token": token, "user": public_user(user)}


@api.post("/auth/google/session")
async def google_session(req: GoogleSessionReq):
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
            "created_at": now_utc().isoformat(),
        }
        await db.users.insert_one(user.copy())
    else:
        # Backfill auth_provider if missing
        if not user.get("auth_provider"):
            await db.users.update_one({"id": user["id"]}, {"$set": {"auth_provider": user.get("auth_provider", "google")}})

    token = create_access_token(user["id"], email)
    return {"token": token, "user": public_user(user)}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return public_user(user)


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
    c = await db.clients.find_one({"id": client_id}, {"_id": 0})
    return c


@api.delete("/clients/{client_id}")
async def delete_client(client_id: str, user: dict = Depends(get_current_user)):
    await db.clients.delete_one({"id": client_id, "owner_id": user["id"]})
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
    now_iso = now_utc().isoformat()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["sent_date"] = doc.get("sent_date") or now_iso
    doc["last_contact_date"] = doc.get("last_contact_date") or doc["sent_date"]
    doc["created_at"] = now_iso
    await db.proposals.insert_one(doc.copy())
    return serialize_proposal({k: v for k, v in doc.items() if k != "_id"})


@api.get("/proposals/{proposal_id}")
async def get_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    p = await db.proposals.find_one({"id": proposal_id, "owner_id": user["id"]}, {"_id": 0})
    if not p:
        raise HTTPException(404, "Proposal not found")
    clients_map = {p["client_id"]: await db.clients.find_one({"id": p["client_id"]}, {"_id": 0}) or {}}
    return serialize_proposal(p, clients_map)


@api.patch("/proposals/{proposal_id}")
async def update_proposal(proposal_id: str, payload: ProposalUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    res = await db.proposals.update_one({"id": proposal_id, "owner_id": user["id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Proposal not found")
    p = await db.proposals.find_one({"id": proposal_id}, {"_id": 0})
    return serialize_proposal(p)


@api.delete("/proposals/{proposal_id}")
async def delete_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    await db.proposals.delete_one({"id": proposal_id, "owner_id": user["id"]})
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
    now_iso = now_utc().isoformat()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["issued_at"] = now_iso
    doc["created_at"] = now_iso
    await db.invoices.insert_one(doc.copy())
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
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    return serialize_invoice(inv)


@api.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    await db.invoices.delete_one({"id": invoice_id, "owner_id": user["id"]})
    return {"ok": True}


# ---------- Activities ----------
@api.get("/activities")
async def list_activities(user: dict = Depends(get_current_user)):
    rows = await db.activities.find({"owner_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(200).to_list(200)
    return rows


@api.post("/activities")
async def create_activity(payload: ActivityCreate, user: dict = Depends(get_current_user)):
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["created_at"] = now_utc().isoformat()
    await db.activities.insert_one(doc.copy())
    doc.pop("_id", None)
    return doc


# ---------- Dashboard ----------
@api.get("/dashboard/summary")
async def dashboard_summary(user: dict = Depends(get_current_user)):
    proposals = await db.proposals.find({"owner_id": user["id"]}, {"_id": 0}).to_list(10000)
    invoices = await db.invoices.find({"owner_id": user["id"]}, {"_id": 0}).to_list(10000)

    total_pipeline = 0.0
    cold_count = 0
    revenue_at_risk = 0.0
    by_status = {"active": 0, "cold": 0, "dead": 0}
    by_stage = {"sent": 0, "negotiating": 0, "won": 0, "lost": 0}

    for p in proposals:
        stage = p.get("stage", "sent")
        by_stage[stage] = by_stage.get(stage, 0) + 1
        if stage in ("sent", "negotiating"):
            total_pipeline += float(p["value_inr"])
            s = compute_proposal_status(p["last_contact_date"])
            by_status[s] = by_status.get(s, 0) + 1
            if s == "cold":
                cold_count += 1
                revenue_at_risk += float(p["value_inr"])
            elif s == "dead":
                revenue_at_risk += float(p["value_inr"])

    overdue_count = 0
    overdue_amount = 0.0
    for inv in invoices:
        s, _ = compute_invoice_status_and_overdue(inv)
        if s == "overdue":
            overdue_count += 1
            overdue_amount += float(inv["amount_inr"])

    return {
        "total_pipeline_inr": total_pipeline,
        "cold_proposals_count": cold_count,
        "overdue_invoices_count": overdue_count,
        "overdue_invoices_inr": overdue_amount,
        "revenue_at_risk_inr": revenue_at_risk,
        "by_status": by_status,
        "by_stage": by_stage,
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
    admin_email = os.environ.get("ADMIN_EMAIL", "founder@bytehubble.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "ByteHubble@2025")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        user_id = str(uuid.uuid4())
        await db.users.insert_one({
            "id": user_id, "email": admin_email,
            "name": "ByteHubble Founder",
            "auth_provider": "email",
            "password_hash": hash_password(admin_password),
            "created_at": now_utc().isoformat(),
        })
        await seed_demo_for_owner(db, user_id)
    else:
        if existing.get("auth_provider", "email") == "email" and not verify_password(admin_password, existing.get("password_hash", "")):
            await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        await seed_demo_for_owner(db, existing["id"])


@api.get("/")
async def root():
    return {"app": "Revora", "status": "ok"}


app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
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
    await migrate_legacy_fields()
    await seed_admin()
    logger.info("Revora ready.")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
