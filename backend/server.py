from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import logging
import uuid
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr

from services.ai import draft_followup
from services.seed import seed_demo_for_owner

# ---------- MongoDB ----------
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALG = "HS256"
EMERGENT_LLM_KEY = os.environ['EMERGENT_LLM_KEY']

app = FastAPI(title="Revora — Revenue Recovery OS")
api = APIRouter(prefix="/api")
bearer_scheme = HTTPBearer(auto_error=False)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def hash_password(p: str) -> str:
    return bcrypt.hashpw(p.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(p: str, h: str) -> bool:
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


def compute_proposal_status(last_contact_at: str, manual_status: Optional[str]) -> str:
    if manual_status in ("dead", "won", "lost"):
        return manual_status
    last = datetime.fromisoformat(last_contact_at)
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    days = (now_utc() - last).days
    if days <= 7:
        return "active"
    if days <= 21:
        return "cold"
    return "dead"


def compute_invoice_status(invoice: dict) -> str:
    if invoice.get("paid_at"):
        return "paid"
    due = datetime.fromisoformat(invoice["due_date"])
    if due.tzinfo is None:
        due = due.replace(tzinfo=timezone.utc)
    days_overdue = (now_utc() - due).days
    if days_overdue <= 0:
        return "due"
    if days_overdue <= 14:
        return "overdue"
    return "critical"


def days_since(iso: str) -> int:
    d = datetime.fromisoformat(iso)
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return (now_utc() - d).days


def fmt_inr(n: float) -> str:
    digits = str(int(round(n)))
    if len(digits) <= 3:
        return f"₹{digits}"
    last3 = digits[-3:]
    rest = digits[:-3]
    groups = []
    while len(rest) > 2:
        groups.insert(0, rest[-2:])
        rest = rest[:-2]
    if rest:
        groups.insert(0, rest)
    return "₹" + ",".join(groups) + "," + last3


# ---------- Models ----------
class RegisterReq(BaseModel):
    email: EmailStr
    password: str
    name: str
    company: Optional[str] = None


class LoginReq(BaseModel):
    email: EmailStr
    password: str


class ClientCreate(BaseModel):
    name: str
    company: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    notes: Optional[str] = None


class ProposalCreate(BaseModel):
    client_id: str
    title: str
    value: float
    sent_at: Optional[str] = None
    last_contact_at: Optional[str] = None
    manual_status: Optional[Literal["active", "cold", "dead", "won", "lost"]] = None
    notes: Optional[str] = None


class ProposalUpdate(BaseModel):
    title: Optional[str] = None
    value: Optional[float] = None
    last_contact_at: Optional[str] = None
    manual_status: Optional[Literal["active", "cold", "dead", "won", "lost"]] = None
    notes: Optional[str] = None


class InvoiceCreate(BaseModel):
    client_id: str
    invoice_number: str
    amount: float
    issued_at: Optional[str] = None
    due_date: str
    notes: Optional[str] = None


class InvoiceUpdate(BaseModel):
    amount: Optional[float] = None
    due_date: Optional[str] = None
    paid_at: Optional[str] = None
    notes: Optional[str] = None


class ActivityCreate(BaseModel):
    client_id: str
    proposal_id: Optional[str] = None
    invoice_id: Optional[str] = None
    kind: Literal["call", "whatsapp", "email", "meeting", "note", "draft_copied"]
    summary: str


class DraftReq(BaseModel):
    kind: Literal["whatsapp", "email", "invoice_reminder"]
    tone: Literal["gentle", "firm", "final"] = "gentle"
    proposal_id: Optional[str] = None
    invoice_id: Optional[str] = None


# ---------- AI Draft ----------
async def generate_draft(user: dict, payload: DraftReq) -> dict:
    proposal = invoice = clientdoc = None
    if payload.proposal_id:
        proposal = await db.proposals.find_one({"id": payload.proposal_id, "owner_id": user["id"]})
        if proposal:
            clientdoc = await db.clients.find_one({"id": proposal["client_id"], "owner_id": user["id"]})
    elif payload.invoice_id:
        invoice = await db.invoices.find_one({"id": payload.invoice_id, "owner_id": user["id"]})
        if invoice:
            clientdoc = await db.clients.find_one({"id": invoice["client_id"], "owner_id": user["id"]})
    if not clientdoc:
        raise HTTPException(status_code=404, detail="Reference not found")

    if proposal:
        days = days_since(proposal["last_contact_at"])
        subject_ref = f'proposal "{proposal["title"]}" worth {fmt_inr(proposal["value"])}'
    elif invoice:
        days = days_since(invoice["due_date"])
        subject_ref = f'invoice #{invoice["invoice_number"]} for {fmt_inr(invoice["amount"])} (due {days} days ago)'
    else:
        raise HTTPException(status_code=400, detail="Missing reference")

    text = await draft_followup(
        kind=payload.kind,
        tone=payload.tone,
        sender_name=user.get("name", "Founder"),
        sender_company=user.get("company") or "ByteHubble",
        recipient_name=clientdoc["name"],
        recipient_company=clientdoc.get("company") or "",
        subject_ref=subject_ref,
        days=days,
    )
    return {"kind": payload.kind, "tone": payload.tone, "text": text}


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
        "company": req.company or "",
        "password_hash": hash_password(req.password),
        "created_at": now_utc().isoformat(),
    }
    await db.users.insert_one(doc)
    token = create_access_token(user_id, email)
    return {"token": token, "user": {"id": user_id, "email": email, "name": req.name, "company": req.company or ""}}


@api.post("/auth/login")
async def login(req: LoginReq):
    email = req.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token = create_access_token(user["id"], email)
    return {"token": token, "user": {"id": user["id"], "email": email, "name": user["name"], "company": user.get("company", "")}}


@api.get("/auth/me")
async def me(user: dict = Depends(get_current_user)):
    return user


# ---------- Clients ----------
@api.get("/clients")
async def list_clients(user: dict = Depends(get_current_user)):
    rows = await db.clients.find({"owner_id": user["id"]}, {"_id": 0}).sort("name", 1).to_list(1000)
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
    for p in proposals:
        p["status"] = compute_proposal_status(p["last_contact_at"], p.get("manual_status"))
        p["days_silent"] = days_since(p["last_contact_at"])
    invoices = await db.invoices.find({"client_id": client_id, "owner_id": user["id"]}, {"_id": 0}).to_list(500)
    for inv in invoices:
        inv["status"] = compute_invoice_status(inv)
        inv["days_overdue"] = max(0, days_since(inv["due_date"]))
    activities = await db.activities.find({"client_id": client_id, "owner_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(500)
    return {"client": c, "proposals": proposals, "invoices": invoices, "activities": activities}


# ---------- Proposals ----------
@api.get("/proposals")
async def list_proposals(user: dict = Depends(get_current_user)):
    rows = await db.proposals.find({"owner_id": user["id"]}, {"_id": 0}).to_list(2000)
    clients_map = {c["id"]: c async for c in db.clients.find({"owner_id": user["id"]}, {"_id": 0})}
    out = []
    for r in rows:
        r["status"] = compute_proposal_status(r["last_contact_at"], r.get("manual_status"))
        r["days_silent"] = days_since(r["last_contact_at"])
        c = clients_map.get(r["client_id"], {})
        r["client_name"] = c.get("name", "Unknown")
        r["client_company"] = c.get("company", "")
        out.append(r)
    out.sort(key=lambda x: x["days_silent"], reverse=True)
    return out


@api.post("/proposals")
async def create_proposal(payload: ProposalCreate, user: dict = Depends(get_current_user)):
    now_iso = now_utc().isoformat()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["sent_at"] = doc.get("sent_at") or now_iso
    doc["last_contact_at"] = doc.get("last_contact_at") or doc["sent_at"]
    doc["created_at"] = now_iso
    await db.proposals.insert_one(doc.copy())
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "client_id": doc["client_id"],
        "proposal_id": doc["id"],
        "kind": "note",
        "summary": f"Proposal created: {doc['title']}",
        "created_at": now_iso,
    })
    doc.pop("_id", None)
    return doc


@api.patch("/proposals/{proposal_id}")
async def update_proposal(proposal_id: str, payload: ProposalUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    res = await db.proposals.update_one({"id": proposal_id, "owner_id": user["id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Proposal not found")
    p = await db.proposals.find_one({"id": proposal_id}, {"_id": 0})
    return p


@api.post("/proposals/{proposal_id}/touch")
async def touch_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    now_iso = now_utc().isoformat()
    res = await db.proposals.update_one(
        {"id": proposal_id, "owner_id": user["id"]},
        {"$set": {"last_contact_at": now_iso}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Proposal not found")
    p = await db.proposals.find_one({"id": proposal_id}, {"_id": 0})
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "client_id": p["client_id"],
        "proposal_id": proposal_id,
        "kind": "note",
        "summary": "Marked as followed-up today",
        "created_at": now_iso,
    })
    return p


@api.delete("/proposals/{proposal_id}")
async def delete_proposal(proposal_id: str, user: dict = Depends(get_current_user)):
    await db.proposals.delete_one({"id": proposal_id, "owner_id": user["id"]})
    return {"ok": True}


# ---------- Invoices ----------
@api.get("/invoices")
async def list_invoices(user: dict = Depends(get_current_user)):
    rows = await db.invoices.find({"owner_id": user["id"]}, {"_id": 0}).to_list(2000)
    clients_map = {c["id"]: c async for c in db.clients.find({"owner_id": user["id"]}, {"_id": 0})}
    out = []
    for r in rows:
        r["status"] = compute_invoice_status(r)
        r["days_overdue"] = max(0, days_since(r["due_date"]))
        c = clients_map.get(r["client_id"], {})
        r["client_name"] = c.get("name", "Unknown")
        r["client_company"] = c.get("company", "")
        out.append(r)
    out.sort(key=lambda x: x["days_overdue"], reverse=True)
    return out


@api.post("/invoices")
async def create_invoice(payload: InvoiceCreate, user: dict = Depends(get_current_user)):
    now_iso = now_utc().isoformat()
    doc = payload.model_dump()
    doc["id"] = str(uuid.uuid4())
    doc["owner_id"] = user["id"]
    doc["issued_at"] = doc.get("issued_at") or now_iso
    doc["paid_at"] = None
    doc["created_at"] = now_iso
    await db.invoices.insert_one(doc.copy())
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "client_id": doc["client_id"],
        "invoice_id": doc["id"],
        "kind": "note",
        "summary": f"Invoice #{doc['invoice_number']} raised",
        "created_at": now_iso,
    })
    doc.pop("_id", None)
    return doc


@api.patch("/invoices/{invoice_id}")
async def update_invoice(invoice_id: str, payload: InvoiceUpdate, user: dict = Depends(get_current_user)):
    updates = {k: v for k, v in payload.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(400, "Nothing to update")
    res = await db.invoices.update_one({"id": invoice_id, "owner_id": user["id"]}, {"$set": updates})
    if res.matched_count == 0:
        raise HTTPException(404, "Invoice not found")
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    return inv


@api.post("/invoices/{invoice_id}/mark-paid")
async def mark_paid(invoice_id: str, user: dict = Depends(get_current_user)):
    now_iso = now_utc().isoformat()
    res = await db.invoices.update_one(
        {"id": invoice_id, "owner_id": user["id"]},
        {"$set": {"paid_at": now_iso}},
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Invoice not found")
    inv = await db.invoices.find_one({"id": invoice_id}, {"_id": 0})
    await db.activities.insert_one({
        "id": str(uuid.uuid4()),
        "owner_id": user["id"],
        "client_id": inv["client_id"],
        "invoice_id": invoice_id,
        "kind": "note",
        "summary": f"Invoice #{inv['invoice_number']} marked PAID ({fmt_inr(inv['amount'])})",
        "created_at": now_iso,
    })
    return inv


@api.delete("/invoices/{invoice_id}")
async def delete_invoice(invoice_id: str, user: dict = Depends(get_current_user)):
    await db.invoices.delete_one({"id": invoice_id, "owner_id": user["id"]})
    return {"ok": True}


# ---------- Activities ----------
@api.get("/activities")
async def list_activities(user: dict = Depends(get_current_user)):
    rows = await db.activities.find({"owner_id": user["id"]}, {"_id": 0}).sort("created_at", -1).limit(50).to_list(50)
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
    proposals = await db.proposals.find({"owner_id": user["id"]}, {"_id": 0}).to_list(5000)
    invoices = await db.invoices.find({"owner_id": user["id"]}, {"_id": 0}).to_list(5000)

    p_buckets = {"active": 0.0, "cold": 0.0, "dead": 0.0, "won": 0.0, "lost": 0.0}
    p_counts = {"active": 0, "cold": 0, "dead": 0, "won": 0, "lost": 0}
    for p in proposals:
        s = compute_proposal_status(p["last_contact_at"], p.get("manual_status"))
        if s in p_buckets:
            p_buckets[s] += float(p["value"])
            p_counts[s] += 1
    pipeline_value = p_buckets["active"] + p_buckets["cold"]
    recoverable = p_buckets["cold"]
    at_risk = p_buckets["cold"] + p_buckets["dead"]

    inv_buckets = {"due": 0.0, "overdue": 0.0, "critical": 0.0, "paid": 0.0}
    inv_counts = {"due": 0, "overdue": 0, "critical": 0, "paid": 0}
    for inv in invoices:
        s = compute_invoice_status(inv)
        inv_buckets[s] += float(inv["amount"])
        inv_counts[s] += 1
    outstanding = inv_buckets["due"] + inv_buckets["overdue"] + inv_buckets["critical"]
    collected = inv_buckets["paid"]

    return {
        "revenue_at_risk": at_risk,
        "recoverable": recoverable,
        "pipeline_value": pipeline_value,
        "outstanding_invoices": outstanding,
        "collected": collected,
        "proposal_buckets": p_buckets,
        "proposal_counts": p_counts,
        "invoice_buckets": inv_buckets,
        "invoice_counts": inv_counts,
    }


@api.get("/dashboard/today")
async def todays_actions(user: dict = Depends(get_current_user)):
    proposals = await db.proposals.find({"owner_id": user["id"]}, {"_id": 0}).to_list(5000)
    invoices = await db.invoices.find({"owner_id": user["id"]}, {"_id": 0}).to_list(5000)
    clients_map = {c["id"]: c async for c in db.clients.find({"owner_id": user["id"]}, {"_id": 0})}

    actions = []
    for p in proposals:
        s = compute_proposal_status(p["last_contact_at"], p.get("manual_status"))
        if s in ("cold", "dead"):
            days = days_since(p["last_contact_at"])
            c = clients_map.get(p["client_id"], {})
            urgency = float(p["value"]) * (1 + min(days, 60) / 30)
            actions.append({
                "kind": "proposal",
                "id": p["id"],
                "client_id": p["client_id"],
                "client_name": c.get("name", "Unknown"),
                "client_company": c.get("company", ""),
                "title": p["title"],
                "value": p["value"],
                "status": s,
                "days": days,
                "urgency": urgency,
            })
    for inv in invoices:
        s = compute_invoice_status(inv)
        if s in ("overdue", "critical"):
            days = max(0, days_since(inv["due_date"]))
            c = clients_map.get(inv["client_id"], {})
            urgency = float(inv["amount"]) * (1 + min(days, 90) / 20)
            actions.append({
                "kind": "invoice",
                "id": inv["id"],
                "client_id": inv["client_id"],
                "client_name": c.get("name", "Unknown"),
                "client_company": c.get("company", ""),
                "title": f"Invoice #{inv['invoice_number']}",
                "value": inv["amount"],
                "status": s,
                "days": days,
                "urgency": urgency,
            })
    actions.sort(key=lambda x: x["urgency"], reverse=True)
    return actions[:20]


@api.post("/ai/draft")
async def ai_draft(payload: DraftReq, user: dict = Depends(get_current_user)):
    return await generate_draft(user, payload)


# ---------- Seed demo data ----------
async def seed_demo_for_user(user_id: str):
    await seed_demo_for_owner(db, user_id)


async def seed_admin():
    admin_email = os.environ.get("ADMIN_EMAIL", "founder@bytehubble.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "ByteHubble@2025")
    existing = await db.users.find_one({"email": admin_email})
    if existing is None:
        user_id = str(uuid.uuid4())
        await db.users.insert_one({
            "id": user_id, "email": admin_email,
            "name": "ByteHubble Founder",
            "company": "ByteHubble",
            "password_hash": hash_password(admin_password),
            "created_at": now_utc().isoformat(),
        })
        await seed_demo_for_user(user_id)
    else:
        if not verify_password(admin_password, existing["password_hash"]):
            await db.users.update_one({"email": admin_email}, {"$set": {"password_hash": hash_password(admin_password)}})
        await seed_demo_for_user(existing["id"])


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
    await db.clients.create_index([("owner_id", 1), ("name", 1)])
    await db.proposals.create_index([("owner_id", 1)])
    await db.invoices.create_index([("owner_id", 1)])
    await db.activities.create_index([("owner_id", 1), ("created_at", -1)])
    await seed_admin()
    logger.info("Revora ready.")


@app.on_event("shutdown")
async def on_shutdown():
    client.close()
