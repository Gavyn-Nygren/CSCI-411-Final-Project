from __future__ import annotations

import re
from datetime import date, time
from pathlib import Path

from fastapi import HTTPException


NAME_RE = re.compile(r"^[A-Za-z\s\-]+$")
EMAIL_RE = re.compile(r"^[\w\.-]+@[\w\.-]+\.\w+$")
PHONE_RE = re.compile(r"^[0-9\-\(\)\s]+$")
ADDRESS_RE = re.compile(r"^[A-Za-z0-9\s,\.\-]+$")
TEXT_RE = re.compile(r"^[A-Za-z0-9\s\.,!?\-'\":;()/&]*$")
SEARCH_RE = re.compile(r"^[A-Za-z0-9\s\.,'\-]*$")
SERVICE_RE = re.compile(r"^[A-Za-z0-9\s\-]+$")
CATEGORY_RE = re.compile(r"^[A-Za-z0-9\s\-]{1,50}$")
ALLOWED_CONTRACT_EXTENSIONS = {".pdf", ".doc", ".docx", ".txt", ".png", ".jpg", ".jpeg"}
MAX_CONTRACT_BYTES = 10 * 1024 * 1024


def bad(message: str) -> None:
    raise HTTPException(status_code=400, detail=message)


def clean_string(value: str, field: str, min_len: int, max_len: int, pattern: re.Pattern[str] | None = None) -> str:
    if not isinstance(value, str):
        bad(f"{field} must be a string.")
    value = value.strip()
    if len(value) < min_len or len(value) > max_len:
        bad(f"{field} must be between {min_len} and {max_len} characters.")
    if pattern and not pattern.fullmatch(value):
        bad(f"{field} contains invalid characters.")
    return value


def clean_notes(value: str | None) -> str:
    value = "" if value is None else value.strip()
    return clean_string(value, "Notes", 0, 1000, TEXT_RE)


def clean_customer_services(data: dict) -> list[dict]:
    raw_services = data.get("services")
    if raw_services is None:
        raw_services = [
            {
                "service_type": data.get("service_type", ""),
                "frequency": data.get("frequency", ""),
            }
        ]
    if not isinstance(raw_services, list) or not raw_services:
        bad("At least one scheduled service is required.")
    if len(raw_services) > 10:
        bad("A customer can have no more than 10 scheduled services.")

    services = []
    seen = set()
    for index, item in enumerate(raw_services, start=1):
        if not isinstance(item, dict):
            bad(f"Scheduled service {index} is invalid.")
        service_type = clean_string(item.get("service_type", ""), "Service type", 1, 50, SERVICE_RE)
        frequency = clean_string(item.get("frequency", ""), "Frequency", 1, 50, SERVICE_RE)
        key = service_type.casefold()
        if key in seen:
            bad("Scheduled service types must be unique for each customer.")
        seen.add(key)
        services.append({"service_type": service_type, "frequency": frequency})
    return services


def clean_customer_payload(data: dict) -> dict:
    services = clean_customer_services(data)
    return {
        "name": clean_string(data.get("name", ""), "Name", 1, 100, NAME_RE),
        "email": clean_string(data.get("email", ""), "Email", 3, 255, EMAIL_RE),
        "phone": clean_string(data.get("phone", ""), "Phone", 7, 20, PHONE_RE),
        "address": clean_string(data.get("address", ""), "Address", 1, 255, ADDRESS_RE),
        "service_type": services[0]["service_type"],
        "frequency": services[0]["frequency"],
        "services": services,
        "notes": clean_notes(data.get("notes", "")),
    }


def clean_int(value: object, field: str, low: int, high: int | None = None) -> int:
    try:
        value = int(value)
    except (TypeError, ValueError):
        bad(f"{field} must be an integer.")
    if value < low or (high is not None and value > high):
        suffix = f" between {low} and {high}" if high is not None else f" at least {low}"
        bad(f"{field} must be{suffix}.")
    return value


def clean_amount(value: object, field: str = "Amount", low: float = 0.01, high: float = 100000.0) -> float:
    try:
        value = float(value)
    except (TypeError, ValueError):
        bad(f"{field} must be numeric.")
    if value < low or value > high:
        bad(f"{field} must be between {low} and {high}.")
    return round(value, 2)


def clean_date(value: str, field: str = "Date") -> str:
    if not isinstance(value, str):
        bad(f"{field} must be a date string.")
    try:
        return date.fromisoformat(value).isoformat()
    except ValueError:
        bad(f"{field} must use YYYY-MM-DD format.")
    return value


def clean_service_date(value: str) -> str:
    cleaned = clean_date(value, "Job date")
    if date.fromisoformat(cleaned) < date.today():
        bad("Job date cannot be before today.")
    return cleaned


def clean_time(value: str, field: str = "Time") -> str:
    if not isinstance(value, str):
        bad(f"{field} must be a time string.")
    try:
        return time.fromisoformat(value).strftime("%H:%M")
    except ValueError:
        bad(f"{field} must use HH:MM format.")
    return value


def clean_service_payload(data: dict) -> dict:
    return {
        "customer_id": clean_int(data.get("customer_id"), "Customer ID", 1),
        "service_type": clean_string(data.get("service_type", ""), "Service type", 1, 50, SERVICE_RE),
        "job_date": clean_service_date(data.get("job_date", "")),
        "service_time": clean_time(data.get("service_time", ""), "Service time"),
        "cost": clean_amount(data.get("cost"), "Cost", 0.0, 100000.0),
        "duration_minutes": clean_int(data.get("duration_minutes"), "Duration", 1, 1440),
        "notes": clean_notes(data.get("notes", "")),
    }


def clean_financial_payload(data: dict) -> dict:
    entry_type = data.get("entry_type", "")
    if entry_type not in {"income", "expense"}:
        bad("Entry type must be income or expense.")
    return {
        "customer_id": clean_int(data["customer_id"], "Customer ID", 1) if data.get("customer_id") else None,
        "service_record_id": clean_int(data["service_record_id"], "Service record ID", 1)
        if data.get("service_record_id")
        else None,
        "entry_type": entry_type,
        "category": clean_string(data.get("category", ""), "Category", 1, 50, CATEGORY_RE),
        "service_type": clean_string(data.get("service_type", ""), "Service type", 1, 50, SERVICE_RE),
        "amount": clean_amount(data.get("amount")),
        "entry_date": clean_date(data.get("entry_date", ""), "Entry date"),
        "notes": clean_notes(data.get("notes", "")),
    }


def clean_search(value: str | None) -> str:
    value = "" if value is None else value.strip()
    return clean_string(value, "Search", 0, 100, SEARCH_RE)


def clean_contract_filename(filename: str | None) -> str:
    if not filename:
        bad("No file selected.")
    original = Path(filename).name.strip()
    if not original or original in {".", ".."}:
        bad("Invalid filename.")
    ext = Path(original).suffix.lower()
    if ext not in ALLOWED_CONTRACT_EXTENSIONS:
        bad("Unsupported contract file type.")
    return original
