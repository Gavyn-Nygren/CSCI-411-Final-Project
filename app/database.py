from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.getenv("CLEANOPS_DATA_DIR", BASE_DIR / "data"))
DATABASE_PATH = Path(os.getenv("CLEANOPS_DB_PATH", DATA_DIR / "cleanops.sqlite3"))


def get_connection() -> sqlite3.Connection:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_connection() as db:
        db.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL UNIQUE,
                password_hash BLOB NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                token TEXT PRIMARY KEY,
                user_id INTEGER NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS customers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                phone TEXT NOT NULL,
                address TEXT NOT NULL,
                service_type TEXT NOT NULL,
                frequency TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS service_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                job_date TEXT NOT NULL,
                service_time TEXT NOT NULL DEFAULT '09:00',
                cost REAL NOT NULL,
                duration_minutes INTEGER NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS customer_services (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                customer_id INTEGER NOT NULL,
                service_type TEXT NOT NULL,
                frequency TEXT NOT NULL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE,
                UNIQUE(customer_id, service_type)
            );

            CREATE TABLE IF NOT EXISTS contracts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                customer_id INTEGER NOT NULL,
                original_filename TEXT NOT NULL,
                stored_filename TEXT NOT NULL UNIQUE,
                content_type TEXT NOT NULL,
                size_bytes INTEGER NOT NULL,
                checksum_sha256 TEXT NOT NULL,
                uploaded_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS financial_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                owner_id INTEGER NOT NULL,
                customer_id INTEGER,
                service_record_id INTEGER,
                entry_type TEXT NOT NULL,
                category TEXT NOT NULL,
                service_type TEXT NOT NULL,
                amount REAL NOT NULL,
                entry_date TEXT NOT NULL,
                notes TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE,
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL,
                FOREIGN KEY (service_record_id) REFERENCES service_records(id) ON DELETE SET NULL
            );
            """
        )
        db.execute(
            """
            INSERT OR IGNORE INTO customer_services (customer_id, service_type, frequency)
            SELECT id, service_type, frequency
            FROM customers
            WHERE service_type != '' AND frequency != ''
            """
        )
        columns = {row["name"] for row in db.execute("PRAGMA table_info(service_records)").fetchall()}
        if "service_time" not in columns:
            db.execute("ALTER TABLE service_records ADD COLUMN service_time TEXT NOT NULL DEFAULT '09:00'")
        normalize_customer_phones(db)


def format_phone(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 10:
        return value
    return f"({digits[:3]})-{digits[3:6]}-{digits[6:]}"


def normalize_customer_phones(db: sqlite3.Connection) -> None:
    rows = db.execute("SELECT id, phone FROM customers").fetchall()
    for row in rows:
        formatted = format_phone(row["phone"])
        if formatted != row["phone"]:
            db.execute("UPDATE customers SET phone = ? WHERE id = ?", (formatted, row["id"]))


def row_to_dict(row: sqlite3.Row | None) -> dict | None:
    if row is None:
        return None
    return dict(row)
