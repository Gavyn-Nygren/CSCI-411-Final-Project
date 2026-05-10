from __future__ import annotations

import html
import hashlib
import sqlite3
import secrets
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from xml.etree import ElementTree

from fastapi import Cookie, Depends, FastAPI, File, Form, HTTPException, Request, Response, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles

from .database import BASE_DIR, get_connection, init_db, row_to_dict
from .security import (
    SESSION_COOKIE,
    clear_session,
    create_session,
    hash_password,
    require_user,
    validate_password,
    validate_username,
    verify_password,
)
from .validation import (
    MAX_CONTRACT_BYTES,
    clean_contract_filename,
    clean_customer_payload,
    clean_financial_payload,
    clean_int,
    clean_search,
    clean_service_payload,
)


STATIC_DIR = BASE_DIR / "app" / "static"
TEMPLATE_PATH = BASE_DIR / "app" / "templates" / "index.html"
UPLOAD_DIR = BASE_DIR / "uploads" / "contracts"


def initialize_app() -> None:
    init_db()
    delete_old_service_records()
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_app()
    yield


app = FastAPI(title="CleanOps Secure Web Application", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.middleware("http")
async def add_security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self'; "
        "img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'self'"
    )
    return response


@app.get("/", response_class=HTMLResponse)
def index() -> HTMLResponse:
    return HTMLResponse(TEMPLATE_PATH.read_text(encoding="utf-8"))


def user_count() -> int:
    with get_connection() as db:
        return int(db.execute("SELECT COUNT(*) AS c FROM users").fetchone()["c"])


def attach_customer_services(db, customer: dict) -> dict:
    rows = db.execute(
        """
        SELECT service_type, frequency
        FROM customer_services
        WHERE customer_id = ?
        ORDER BY service_type
        """,
        (customer["id"],),
    ).fetchall()
    services = [dict(row) for row in rows]
    if not services and customer.get("service_type") and customer.get("frequency"):
        services = [{"service_type": customer["service_type"], "frequency": customer["frequency"]}]
    customer["services"] = services
    if services:
        customer["service_type"] = services[0]["service_type"]
        customer["frequency"] = services[0]["frequency"]
    return customer


def replace_customer_services(db, customer_id: int, services: list[dict]) -> None:
    db.execute("DELETE FROM customer_services WHERE customer_id = ?", (customer_id,))
    db.executemany(
        """
        INSERT INTO customer_services (customer_id, service_type, frequency)
        VALUES (?, ?, ?)
        """,
        [(customer_id, service["service_type"], service["frequency"]) for service in services],
    )


def delete_old_service_records() -> None:
    with get_connection() as db:
        db.execute("DELETE FROM service_records WHERE job_date < date('now', 'localtime', '-1 month')")


@app.get("/api/me")
def me(user: dict = Depends(require_user)) -> dict:
    return {"authenticated": True, "username": user["username"], "setup_required": False}


@app.get("/api/setup-required")
def setup_required() -> dict:
    return {"setup_required": user_count() == 0}


@app.post("/api/setup")
async def setup_owner(request: Request, response: Response) -> dict:
    if user_count() > 0:
        raise HTTPException(status_code=409, detail="Owner account already exists.")
    data = await request.json()
    username = validate_username(data.get("username", ""))
    password = validate_password(data.get("password", ""))
    password_hash = hash_password(password)
    with get_connection() as db:
        cur = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        user_id = int(cur.lastrowid)
    create_session(response, user_id)
    return {"username": username}


@app.post("/api/register")
async def register(request: Request, response: Response) -> dict:
    data = await request.json()
    username = validate_username(data.get("username", ""))
    password = validate_password(data.get("password", ""))
    password_hash = hash_password(password)
    with get_connection() as db:
        try:
            cur = db.execute("INSERT INTO users (username, password_hash) VALUES (?, ?)", (username, password_hash))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail="Username already exists.") from None
        user_id = int(cur.lastrowid)
    create_session(response, user_id)
    return {"username": username}


@app.post("/api/login")
async def login(request: Request, response: Response) -> dict:
    data = await request.json()
    username = data.get("username", "")
    password = data.get("password", "")
    if not isinstance(username, str) or not isinstance(password, str):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    with get_connection() as db:
        row = db.execute("SELECT id, username, password_hash FROM users WHERE username = ?", (username,)).fetchone()
    if row is None or not verify_password(password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    create_session(response, int(row["id"]))
    return {"username": row["username"]}


@app.post("/api/logout")
def logout(response: Response, token: str | None = Cookie(default=None, alias=SESSION_COOKIE)) -> dict:
    clear_session(response, token)
    return {"ok": True}


@app.post("/api/customers")
async def create_customer(request: Request, user: dict = Depends(require_user)) -> dict:
    payload = clean_customer_payload(await request.json())
    with get_connection() as db:
        cur = db.execute(
            """
            INSERT INTO customers (owner_id, name, email, phone, address, service_type, frequency, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload["name"],
                payload["email"],
                payload["phone"],
                payload["address"],
                payload["service_type"],
                payload["frequency"],
                payload["notes"],
            ),
        )
        customer_id = int(cur.lastrowid)
        replace_customer_services(db, customer_id, payload["services"])
        row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return attach_customer_services(db, row_to_dict(row))


@app.get("/api/customers")
def list_customers(
    search: str | None = None,
    page: int = 1,
    page_size: int = 25,
    user: dict = Depends(require_user),
) -> dict:
    search = clean_search(search)
    page = clean_int(page, "Page", 1)
    page_size = clean_int(page_size, "Page size", 1, 100)
    offset = (page - 1) * page_size
    like = f"%{search}%"
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT * FROM customers
            WHERE owner_id = ?
              AND (
                ? = ''
                OR name LIKE ?
                OR email LIKE ?
                OR phone LIKE ?
                OR address LIKE ?
                OR id IN (
                    SELECT customer_id
                    FROM customer_services
                    WHERE service_type LIKE ? OR frequency LIKE ?
                )
              )
            ORDER BY name
            LIMIT ? OFFSET ?
            """,
            (user["id"], search, like, like, like, like, like, like, page_size, offset),
        ).fetchall()
        items = [attach_customer_services(db, dict(row)) for row in rows]
    return {"items": items, "page": page, "page_size": page_size}


@app.get("/api/customers/{customer_id}")
def get_customer(customer_id: int, user: dict = Depends(require_user)) -> dict:
    customer_id = clean_int(customer_id, "Customer ID", 1)
    with get_connection() as db:
        row = db.execute("SELECT * FROM customers WHERE id = ? AND owner_id = ?", (customer_id, user["id"])).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Customer not found.")
        return attach_customer_services(db, row_to_dict(row))


@app.put("/api/customers/{customer_id}")
async def update_customer(customer_id: int, request: Request, user: dict = Depends(require_user)) -> dict:
    customer_id = clean_int(customer_id, "Customer ID", 1)
    payload = clean_customer_payload(await request.json())
    with get_connection() as db:
        cur = db.execute(
            """
            UPDATE customers
            SET name = ?, email = ?, phone = ?, address = ?, service_type = ?, frequency = ?, notes = ?,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND owner_id = ?
            """,
            (
                payload["name"],
                payload["email"],
                payload["phone"],
                payload["address"],
                payload["service_type"],
                payload["frequency"],
                payload["notes"],
                customer_id,
                user["id"],
            ),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Customer not found.")
        replace_customer_services(db, customer_id, payload["services"])
        row = db.execute("SELECT * FROM customers WHERE id = ?", (customer_id,)).fetchone()
        return attach_customer_services(db, row_to_dict(row))


@app.delete("/api/customers/{customer_id}")
def delete_customer(customer_id: int, user: dict = Depends(require_user)) -> dict:
    customer_id = clean_int(customer_id, "Customer ID", 1)
    with get_connection() as db:
        cur = db.execute("DELETE FROM customers WHERE id = ? AND owner_id = ?", (customer_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Customer not found.")
    return {"ok": True}


def require_customer(owner_id: int, customer_id: int) -> dict:
    with get_connection() as db:
        row = db.execute("SELECT * FROM customers WHERE id = ? AND owner_id = ?", (customer_id, owner_id)).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Customer not found.")
    return row_to_dict(row)


def customer_service_schedule(owner_id: int, customer_id: int) -> list[dict]:
    with get_connection() as db:
        rows = db.execute(
            """
            SELECT cs.service_type, cs.frequency
            FROM customer_services cs
            JOIN customers c ON c.id = cs.customer_id
            WHERE cs.customer_id = ? AND c.owner_id = ?
            ORDER BY cs.service_type
            """,
            (customer_id, owner_id),
        ).fetchall()
    return [dict(row) for row in rows]


def require_scheduled_service(owner_id: int, payload: dict) -> None:
    customer = require_customer(owner_id, payload["customer_id"])
    scheduled = customer_service_schedule(owner_id, payload["customer_id"])
    allowed = {service["service_type"] for service in scheduled}
    if payload["service_type"] not in allowed:
        allowed_text = ", ".join(sorted(allowed)) or customer["service_type"]
        raise HTTPException(
            status_code=400,
            detail=f"{customer['name']} is scheduled for these services only: {allowed_text}.",
        )


@app.post("/api/services")
async def create_service(request: Request, user: dict = Depends(require_user)) -> dict:
    payload = clean_service_payload(await request.json())
    require_scheduled_service(user["id"], payload)
    with get_connection() as db:
        cur = db.execute(
            """
            INSERT INTO service_records
            (owner_id, customer_id, service_type, job_date, service_time, cost, duration_minutes, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload["customer_id"],
                payload["service_type"],
                payload["job_date"],
                payload["service_time"],
                payload["cost"],
                payload["duration_minutes"],
                payload["notes"],
            ),
        )
        row = db.execute("SELECT * FROM service_records WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.put("/api/services/{service_id}")
async def update_service(service_id: int, request: Request, user: dict = Depends(require_user)) -> dict:
    service_id = clean_int(service_id, "Service ID", 1)
    payload = clean_service_payload(await request.json())
    require_scheduled_service(user["id"], payload)
    with get_connection() as db:
        cur = db.execute(
            """
            UPDATE service_records
            SET customer_id = ?, service_type = ?, job_date = ?, service_time = ?,
                cost = ?, duration_minutes = ?, notes = ?
            WHERE id = ? AND owner_id = ?
            """,
            (
                payload["customer_id"],
                payload["service_type"],
                payload["job_date"],
                payload["service_time"],
                payload["cost"],
                payload["duration_minutes"],
                payload["notes"],
                service_id,
                user["id"],
            ),
        )
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Service record not found.")
        row = db.execute("SELECT * FROM service_records WHERE id = ?", (service_id,)).fetchone()
    return row_to_dict(row)


@app.get("/api/services")
def list_services(customer_id: int | None = None, user: dict = Depends(require_user)) -> dict:
    delete_old_service_records()
    params: list[object] = [user["id"]]
    where = "sr.owner_id = ?"
    if customer_id:
        customer_id = clean_int(customer_id, "Customer ID", 1)
        where += " AND sr.customer_id = ?"
        params.append(customer_id)
    with get_connection() as db:
        rows = db.execute(
            f"""
            SELECT
                sr.*,
                c.name AS customer_name,
                c.address AS customer_address,
                c.email AS customer_email,
                c.phone AS customer_phone,
                EXISTS (
                    SELECT 1
                    FROM financial_entries fe
                    WHERE fe.service_record_id = sr.id
                      AND fe.owner_id = sr.owner_id
                      AND fe.entry_type = 'income'
                ) AS completed
            FROM service_records sr
            JOIN customers c ON c.id = sr.customer_id
            WHERE {where}
            ORDER BY
                CASE WHEN sr.job_date >= date('now', 'localtime') THEN 0 ELSE 1 END,
                CASE WHEN sr.job_date >= date('now', 'localtime') THEN sr.job_date END ASC,
                CASE WHEN sr.job_date >= date('now', 'localtime') THEN sr.service_time END ASC,
                CASE WHEN sr.job_date < date('now', 'localtime') THEN sr.job_date END DESC,
                CASE WHEN sr.job_date < date('now', 'localtime') THEN sr.service_time END DESC,
                sr.id DESC
            """,
            params,
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.post("/api/services/{service_id}/complete")
def complete_service(service_id: int, user: dict = Depends(require_user)) -> dict:
    service_id = clean_int(service_id, "Service ID", 1)
    with get_connection() as db:
        service = db.execute(
            """
            SELECT
                sr.*,
                c.name AS customer_name
            FROM service_records sr
            JOIN customers c ON c.id = sr.customer_id
            WHERE sr.id = ? AND sr.owner_id = ?
            """,
            (service_id, user["id"]),
        ).fetchone()
        if service is None:
            raise HTTPException(status_code=404, detail="Service record not found.")

        existing = db.execute(
            """
            SELECT *
            FROM financial_entries
            WHERE owner_id = ? AND service_record_id = ? AND entry_type = 'income'
            """,
            (user["id"], service_id),
        ).fetchone()
        if existing is not None:
            return {"completed": True, "financial_entry": dict(existing)}

        cur = db.execute(
            """
            INSERT INTO financial_entries
            (owner_id, customer_id, service_record_id, entry_type, category, service_type, amount, entry_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                service["customer_id"],
                service_id,
                "income",
                "Completed Service",
                service["service_type"],
                service["cost"],
                service["job_date"],
                f"Completed {service['service_type']} service for {service['customer_name']}.",
            ),
        )
        row = db.execute("SELECT * FROM financial_entries WHERE id = ?", (cur.lastrowid,)).fetchone()
    return {"completed": True, "financial_entry": row_to_dict(row)}


@app.delete("/api/services/{service_id}")
def delete_service(service_id: int, user: dict = Depends(require_user)) -> dict:
    service_id = clean_int(service_id, "Service ID", 1)
    with get_connection() as db:
        cur = db.execute("DELETE FROM service_records WHERE id = ? AND owner_id = ?", (service_id, user["id"]))
        if cur.rowcount == 0:
            raise HTTPException(status_code=404, detail="Service record not found.")
    return {"ok": True}


def contract_for_user(contract_id: int, owner_id: int) -> tuple[dict, Path]:
    with get_connection() as db:
        row = db.execute(
            """
            SELECT
                contracts.*,
                customers.name AS customer_name
            FROM contracts
            JOIN customers ON customers.id = contracts.customer_id
            WHERE contracts.id = ? AND contracts.owner_id = ?
            """,
            (contract_id, owner_id),
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="Contract not found.")
    contract = dict(row)
    path = UPLOAD_DIR / contract["stored_filename"]
    if not path.exists() or path.parent.resolve() != UPLOAD_DIR.resolve():
        raise HTTPException(status_code=404, detail="Contract file not found.")
    return contract, path


def docx_text(path: Path) -> str:
    try:
        with zipfile.ZipFile(path) as archive:
            xml = archive.read("word/document.xml")
    except (KeyError, zipfile.BadZipFile):
        raise HTTPException(status_code=400, detail="Unable to preview this DOCX file.") from None
    root = ElementTree.fromstring(xml)
    namespace = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}
    paragraphs = []
    for paragraph in root.findall(".//w:p", namespace):
        parts = [node.text or "" for node in paragraph.findall(".//w:t", namespace)]
        text = "".join(parts).strip()
        if text:
            paragraphs.append(text)
    return "\n\n".join(paragraphs) or "This DOCX file does not contain previewable text."


@app.post("/api/contracts")
async def upload_contract(
    customer_id: int = Form(...),
    file: UploadFile = File(...),
    user: dict = Depends(require_user),
) -> dict:
    customer_id = clean_int(customer_id, "Customer ID", 1)
    require_customer(user["id"], customer_id)
    original = clean_contract_filename(file.filename)
    contents = await file.read(MAX_CONTRACT_BYTES + 1)
    if len(contents) > MAX_CONTRACT_BYTES:
        raise HTTPException(status_code=400, detail="File exceeds 10MB limit.")
    checksum = hashlib.sha256(contents).hexdigest()
    stored = f"{secrets.token_urlsafe(16)}{Path(original).suffix.lower()}"
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    path = UPLOAD_DIR / stored
    path.write_bytes(contents)
    with get_connection() as db:
        cur = db.execute(
            """
            INSERT INTO contracts
            (owner_id, customer_id, original_filename, stored_filename, content_type, size_bytes, checksum_sha256)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (user["id"], customer_id, original, stored, file.content_type or "application/octet-stream", len(contents), checksum),
        )
        row = db.execute("SELECT * FROM contracts WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.get("/api/contracts")
def list_contracts(customer_id: int | None = None, user: dict = Depends(require_user)) -> dict:
    params: list[object] = [user["id"]]
    where = "contracts.owner_id = ?"
    if customer_id:
        customer_id = clean_int(customer_id, "Customer ID", 1)
        where += " AND contracts.customer_id = ?"
        params.append(customer_id)
    with get_connection() as db:
        rows = db.execute(
            f"""
            SELECT
                contracts.*,
                customers.name AS customer_name
            FROM contracts
            JOIN customers ON customers.id = contracts.customer_id
            WHERE {where}
            ORDER BY contracts.uploaded_at DESC
            """,
            params,
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.get("/api/contracts/{contract_id}/download")
def download_contract(contract_id: int, user: dict = Depends(require_user)) -> FileResponse:
    contract_id = clean_int(contract_id, "Contract ID", 1)
    contract, path = contract_for_user(contract_id, user["id"])
    return FileResponse(path, media_type=contract["content_type"], filename=contract["original_filename"])


@app.delete("/api/contracts/{contract_id}")
def delete_contract(contract_id: int, user: dict = Depends(require_user)) -> dict:
    contract_id = clean_int(contract_id, "Contract ID", 1)
    contract, path = contract_for_user(contract_id, user["id"])
    path.unlink(missing_ok=True)
    with get_connection() as db:
        db.execute("DELETE FROM contracts WHERE id = ? AND owner_id = ?", (contract["id"], user["id"]))
    return {"ok": True}


@app.get("/api/contracts/{contract_id}/raw")
def raw_contract(contract_id: int, user: dict = Depends(require_user)) -> FileResponse:
    contract_id = clean_int(contract_id, "Contract ID", 1)
    contract, path = contract_for_user(contract_id, user["id"])
    return FileResponse(path, media_type=contract["content_type"])


@app.get("/api/contracts/{contract_id}/view", response_class=HTMLResponse)
def view_contract(contract_id: int, user: dict = Depends(require_user)) -> HTMLResponse:
    contract_id = clean_int(contract_id, "Contract ID", 1)
    contract, path = contract_for_user(contract_id, user["id"])
    filename = html.escape(contract["original_filename"])
    customer_name = html.escape(contract["customer_name"])
    suffix = path.suffix.lower()
    content_type = contract["content_type"]

    if suffix == ".txt" or content_type.startswith("text/"):
        body = f"<pre>{html.escape(path.read_text(encoding='utf-8', errors='replace'))}</pre>"
    elif suffix == ".docx":
        body = f"<pre>{html.escape(docx_text(path))}</pre>"
    elif content_type.startswith("image/"):
        body = f'<img src="/api/contracts/{contract_id}/raw" alt="{filename}" width="100%">'
    elif content_type == "application/pdf" or suffix == ".pdf":
        body = f'<iframe src="/api/contracts/{contract_id}/raw" title="{filename}" width="100%" height="720"></iframe>'
    else:
        body = "<p>This file type cannot be previewed in the app. Use Download to open it.</p>"

    return HTMLResponse(
        f"""
        <!doctype html>
        <html lang="en">
          <head>
            <meta charset="utf-8">
            <title>{filename}</title>
          </head>
          <body>
            <h1>{filename}</h1>
            <p>{customer_name}</p>
            {body}
          </body>
        </html>
        """
    )


@app.post("/api/financials")
async def create_financial(request: Request, user: dict = Depends(require_user)) -> dict:
    payload = clean_financial_payload(await request.json())
    if payload["customer_id"]:
        require_customer(user["id"], payload["customer_id"])
    with get_connection() as db:
        cur = db.execute(
            """
            INSERT INTO financial_entries
            (owner_id, customer_id, service_record_id, entry_type, category, service_type, amount, entry_date, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user["id"],
                payload["customer_id"],
                payload["service_record_id"],
                payload["entry_type"],
                payload["category"],
                payload["service_type"],
                payload["amount"],
                payload["entry_date"],
                payload["notes"],
            ),
        )
        row = db.execute("SELECT * FROM financial_entries WHERE id = ?", (cur.lastrowid,)).fetchone()
    return row_to_dict(row)


@app.get("/api/financials")
def list_financials(user: dict = Depends(require_user)) -> dict:
    with get_connection() as db:
        rows = db.execute(
            "SELECT * FROM financial_entries WHERE owner_id = ? ORDER BY entry_date DESC",
            (user["id"],),
        ).fetchall()
    return {"items": [dict(row) for row in rows]}


@app.get("/api/financials/summary")
def financial_summary(year: int, month: int, service_type: str | None = None, user: dict = Depends(require_user)) -> dict:
    year = clean_int(year, "Year", 2000, 2100)
    month = clean_int(month, "Month", 1, 12)
    prefix = f"{year:04d}-{month:02d}-%"
    params: list[object] = [user["id"], prefix]
    service_filter = ""
    if service_type:
        service_type = service_type.strip()
        service_filter = " AND service_type = ?"
        params.append(service_type)
    with get_connection() as db:
        totals = db.execute(
            f"""
            SELECT entry_type, COALESCE(SUM(amount), 0) AS total
            FROM financial_entries
            WHERE owner_id = ? AND entry_date LIKE ?{service_filter}
            GROUP BY entry_type
            """,
            params,
        ).fetchall()
        by_service = db.execute(
            """
            SELECT service_type, COALESCE(SUM(amount), 0) AS total
            FROM financial_entries
            WHERE owner_id = ? AND entry_date LIKE ? AND entry_type = 'income'
            GROUP BY service_type
            ORDER BY total DESC
            """,
            (user["id"], prefix),
        ).fetchall()
    income = sum(row["total"] for row in totals if row["entry_type"] == "income")
    expenses = sum(row["total"] for row in totals if row["entry_type"] == "expense")
    return {
        "year": year,
        "month": month,
        "income": round(income, 2),
        "expenses": round(expenses, 2),
        "net": round(income - expenses, 2),
        "income_by_service_type": [dict(row) for row in by_service],
    }
