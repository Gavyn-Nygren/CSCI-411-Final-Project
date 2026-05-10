import importlib
from datetime import date, timedelta

from fastapi.testclient import TestClient


def make_client(tmp_path, monkeypatch):
    monkeypatch.setenv("CLEANOPS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("CLEANOPS_DB_PATH", str(tmp_path / "data" / "test.sqlite3"))
    import app.database as database
    import app.main as main
    import app.security as security

    importlib.reload(database)
    importlib.reload(security)
    main = importlib.reload(main)
    main.initialize_app()
    return TestClient(main.app)


def setup_user(client):
    return client.post(
        "/api/setup",
        json={"username": "Owner1", "password": "StrongPass1!"},
    )


def future_date(days=30):
    return (date.today() + timedelta(days=days)).isoformat()


def future_year_month(days=30):
    target = date.today() + timedelta(days=days)
    return target.year, target.month


def yesterday():
    return (date.today() - timedelta(days=1)).isoformat()


def old_service_date():
    return (date.today() - timedelta(days=40)).isoformat()


def test_first_run_setup_and_login_flow(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    assert client.get("/api/setup-required").json() == {"setup_required": True}

    weak = client.post("/api/setup", json={"username": "Owner1", "password": "weak"})
    assert weak.status_code == 400

    response = setup_user(client)
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert client.get("/api/setup-required").json() == {"setup_required": False}

    duplicate = client.post("/api/setup", json={"username": "Owner2", "password": "StrongPass2!"})
    assert duplicate.status_code == 409


def test_register_additional_account_after_setup(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    client.post("/api/logout")

    registered = client.post(
        "/api/register",
        json={"username": "Owner2", "password": "StrongPass2!"},
    )
    assert registered.status_code == 200
    assert registered.json()["username"] == "Owner2"
    assert "httponly" in registered.headers["set-cookie"].lower()

    client.post("/api/logout")
    duplicate = client.post(
        "/api/register",
        json={"username": "Owner2", "password": "StrongPass3!"},
    )
    assert duplicate.status_code == 409


def test_protected_routes_require_auth(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    response = client.get("/api/customers")
    assert response.status_code == 401


def test_customer_validation_and_sql_injection_string(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)

    bad_customer = client.post(
        "/api/customers",
        json={
            "name": "Bad<script>",
            "email": "bad@example.com",
            "phone": "555-1212",
            "address": "1 Main St",
            "service_type": "Cleaning",
            "frequency": "Weekly",
            "notes": "",
        },
    )
    assert bad_customer.status_code == 400

    good_customer = client.post(
        "/api/customers",
        json={
            "name": "Alice Smith",
            "email": "alice@example.com",
            "phone": "555-1212",
            "address": "1 Main St",
            "service_type": "Cleaning",
            "frequency": "Weekly",
            "notes": "'; DROP TABLE customers; --",
        },
    )
    assert good_customer.status_code == 200

    listed = client.get("/api/customers", params={"search": "Alice"}).json()
    assert len(listed["items"]) == 1
    assert "DROP TABLE" in listed["items"][0]["notes"]


def test_can_create_and_list_many_customers(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)

    names = ["Alice Adams", "Betty Brown", "Carla Clark", "Diana Davis", "Erin Evans"]
    for index, name in enumerate(names, start=1):
        response = client.post(
            "/api/customers",
            json={
                "name": name,
                "email": f"customer{index}@example.com",
                "phone": f"555-120{index}",
                "address": f"{index} Main St",
                "service_type": "Cleaning",
                "frequency": "Weekly",
                "notes": "",
            },
        )
        assert response.status_code == 200

    listed = client.get("/api/customers", params={"page_size": 100}).json()
    assert len(listed["items"]) == 5
    assert {customer["name"] for customer in listed["items"]} == set(names)


def test_service_financial_summary_and_contract_upload(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Bob Jones",
            "email": "bob@example.com",
            "phone": "555-2323",
            "address": "2 Main St",
            "service_type": "Move-out",
            "frequency": "Once",
            "notes": "",
        },
    ).json()

    service = client.post(
        "/api/services",
        json={
            "customer_id": customer["id"],
            "service_type": "Move-out",
            "job_date": future_date(),
            "service_time": "17:00",
            "cost": 200,
            "duration_minutes": 180,
            "notes": "Complete",
        },
    )
    assert service.status_code == 200
    service_list = client.get("/api/services").json()["items"]
    assert service_list[0]["customer_name"] == "Bob Jones"
    assert service_list[0]["customer_address"] == "2 Main St"

    financial = client.post(
        "/api/financials",
        json={
            "customer_id": customer["id"],
            "entry_type": "income",
            "category": "Job",
            "service_type": "Move-out",
            "amount": 200,
            "entry_date": "2026-05-10",
            "notes": "",
        },
    )
    assert financial.status_code == 200
    expense = client.post(
        "/api/financials",
        json={
            "customer_id": "",
            "entry_type": "expense",
            "category": "Tools",
            "service_type": "Replacement",
            "amount": 50,
            "entry_date": "2026-05-10",
            "notes": "",
        },
    )
    assert expense.status_code == 200
    summary = client.get("/api/financials/summary", params={"year": 2026, "month": 5}).json()
    assert summary["income"] == 200
    assert summary["expenses"] == 50
    assert summary["net"] == 150

    upload = client.post(
        "/api/contracts",
        data={"customer_id": customer["id"]},
        files={"file": ("contract.pdf", b"contract text", "application/pdf")},
    )
    assert upload.status_code == 200
    contract_id = upload.json()["id"]
    contracts = client.get("/api/contracts").json()["items"]
    assert contracts[0]["customer_name"] == "Bob Jones"
    assert contracts[0]["original_filename"] == "contract.pdf"
    download = client.get(f"/api/contracts/{contract_id}/download")
    assert download.status_code == 200
    assert download.content == b"contract text"


def test_service_type_must_match_customer_schedule(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Jane Doe",
            "email": "jane@example.com",
            "phone": "555-3434",
            "address": "3 Main St",
            "service_type": "Scrub",
            "frequency": "Monthly",
            "notes": "",
        },
    ).json()

    rejected = client.post(
        "/api/services",
        json={
            "customer_id": customer["id"],
            "service_type": "Move-out",
            "job_date": future_date(1),
            "service_time": "09:00",
            "cost": 50,
            "duration_minutes": 30,
            "notes": "",
        },
    )
    assert rejected.status_code == 400
    assert "Scrub" in rejected.json()["detail"]

    accepted = client.post(
        "/api/services",
        json={
            "customer_id": customer["id"],
            "service_type": "Scrub",
            "job_date": future_date(1),
            "service_time": "17:00",
            "cost": 50,
            "duration_minutes": 30,
            "notes": "",
        },
    )
    assert accepted.status_code == 200


def test_contract_can_be_viewed_in_app(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Text Viewer",
            "email": "viewer@example.com",
            "phone": "555-9090",
            "address": "10 Main St",
            "service_type": "Scrub",
            "frequency": "Weekly",
            "notes": "",
        },
    ).json()
    upload = client.post(
        "/api/contracts",
        data={"customer_id": customer["id"]},
        files={"file": ("notes.txt", b"preview me", "text/plain")},
    )
    contract_id = upload.json()["id"]

    view = client.get(f"/api/contracts/{contract_id}/view")
    assert view.status_code == 200
    assert "preview me" in view.text
    assert "Text Viewer" in view.text


def test_can_delete_contract(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Contract Delete",
            "email": "contractdelete@example.com",
            "phone": "555-9191",
            "address": "11 Main St",
            "service_type": "Scrub",
            "frequency": "Weekly",
            "notes": "",
        },
    ).json()
    upload = client.post(
        "/api/contracts",
        data={"customer_id": customer["id"]},
        files={"file": ("delete-me.txt", b"remove me", "text/plain")},
    )
    contract_id = upload.json()["id"]

    assert len(client.get("/api/contracts").json()["items"]) == 1
    delete = client.delete(f"/api/contracts/{contract_id}")
    assert delete.status_code == 200
    assert client.get("/api/contracts").json()["items"] == []
    assert client.get(f"/api/contracts/{contract_id}/download").status_code == 404


def test_service_date_cannot_be_before_today(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Lena Lane",
            "email": "lena@example.com",
            "phone": "555-4040",
            "address": "8 Main St",
            "service_type": "Scrub",
            "frequency": "Weekly",
            "notes": "",
        },
    ).json()

    response = client.post(
        "/api/services",
        json={
            "customer_id": customer["id"],
            "service_type": "Scrub",
            "job_date": yesterday(),
            "service_time": "10:00",
            "cost": 50,
            "duration_minutes": 30,
            "notes": "",
        },
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "Job date cannot be before today."


def test_customer_can_have_multiple_scheduled_services_and_be_deleted(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Morgan Miller",
            "email": "morgan@example.com",
            "phone": "555-4545",
            "address": "4 Main St",
            "services": [
                {"service_type": "Scrub", "frequency": "Weekly"},
                {"service_type": "Windows", "frequency": "Monthly"},
            ],
            "notes": "",
        },
    )
    assert customer.status_code == 200
    customer_data = customer.json()
    assert customer_data["service_type"] == "Scrub"
    assert {service["service_type"] for service in customer_data["services"]} == {"Scrub", "Windows"}

    windows = client.post(
        "/api/services",
        json={
            "customer_id": customer_data["id"],
            "service_type": "Windows",
            "job_date": future_date(2),
            "service_time": "08:30",
            "cost": 75,
            "duration_minutes": 45,
            "notes": "",
        },
    )
    assert windows.status_code == 200

    rejected = client.post(
        "/api/services",
        json={
            "customer_id": customer_data["id"],
            "service_type": "Move-out",
            "job_date": future_date(2),
            "service_time": "08:30",
            "cost": 75,
            "duration_minutes": 45,
            "notes": "",
        },
    )
    assert rejected.status_code == 400

    delete = client.delete(f"/api/customers/{customer_data['id']}")
    assert delete.status_code == 200
    assert client.get(f"/api/customers/{customer_data['id']}").status_code == 404
    assert client.get("/api/services").json()["items"] == []


def test_services_include_time_and_sort_current_date_forward(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Nora North",
            "email": "nora@example.com",
            "phone": "555-5656",
            "address": "5 Main St",
            "service_type": "Scrub",
            "frequency": "Weekly",
            "notes": "",
        },
    ).json()

    day_one = future_date(1)
    day_two = future_date(2)
    for job_date, service_time in [
        (day_one, "17:00"),
        (day_two, "08:00"),
        (day_two, "17:30"),
    ]:
        response = client.post(
            "/api/services",
            json={
                "customer_id": customer["id"],
                "service_type": "Scrub",
                "job_date": job_date,
                "service_time": service_time,
                "cost": 50,
                "duration_minutes": 30,
                "notes": "",
            },
        )
        assert response.status_code == 200

    services = client.get("/api/services").json()["items"]
    assert [(service["job_date"], service["service_time"]) for service in services] == [
        (day_one, "17:00"),
        (day_two, "08:00"),
        (day_two, "17:30"),
    ]


def test_can_delete_service_record(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Paula Park",
            "email": "paula@example.com",
            "phone": "555-6767",
            "address": "6 Main St",
            "service_type": "Scrub",
            "frequency": "Weekly",
            "notes": "",
        },
    ).json()
    service = client.post(
        "/api/services",
        json={
            "customer_id": customer["id"],
            "service_type": "Scrub",
            "job_date": future_date(3),
            "service_time": "10:00",
            "cost": 60,
            "duration_minutes": 30,
            "notes": "",
        },
    ).json()

    assert len(client.get("/api/services").json()["items"]) == 1
    delete = client.delete(f"/api/services/{service['id']}")
    assert delete.status_code == 200
    assert client.get("/api/services").json()["items"] == []
    assert client.delete(f"/api/services/{service['id']}").status_code == 404


def test_service_records_over_one_month_old_are_deleted(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Old Record",
            "email": "old@example.com",
            "phone": "555-7070",
            "address": "9 Main St",
            "service_type": "Scrub",
            "frequency": "Weekly",
            "notes": "",
        },
    ).json()

    import app.database as database

    with database.get_connection() as db:
        db.execute(
            """
            INSERT INTO service_records
            (owner_id, customer_id, service_type, job_date, service_time, cost, duration_minutes, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (1, customer["id"], "Scrub", old_service_date(), "10:00", 60, 30, ""),
        )

    assert client.get("/api/services").json()["items"] == []


def test_can_edit_service_record(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Quinn Queen",
            "email": "quinn@example.com",
            "phone": "555-7878",
            "address": "7 Main St",
            "services": [
                {"service_type": "Scrub", "frequency": "Weekly"},
                {"service_type": "Windows", "frequency": "Monthly"},
            ],
            "notes": "",
        },
    ).json()
    service = client.post(
        "/api/services",
        json={
            "customer_id": customer["id"],
            "service_type": "Scrub",
            "job_date": future_date(3),
            "service_time": "10:00",
            "cost": 60,
            "duration_minutes": 30,
            "notes": "",
        },
    ).json()

    update = client.put(
        f"/api/services/{service['id']}",
        json={
            "customer_id": customer["id"],
            "service_type": "Windows",
            "job_date": future_date(4),
            "service_time": "14:30",
            "cost": 90,
            "duration_minutes": 45,
            "notes": "Updated",
        },
    )
    assert update.status_code == 200
    updated = update.json()
    assert updated["service_type"] == "Windows"
    assert updated["job_date"] == future_date(4)
    assert updated["service_time"] == "14:30"
    assert updated["cost"] == 90
    assert updated["duration_minutes"] == 45
    assert updated["notes"] == "Updated"

    rejected = client.put(
        f"/api/services/{service['id']}",
        json={
            "customer_id": customer["id"],
            "service_type": "Move-out",
            "job_date": future_date(4),
            "service_time": "14:30",
            "cost": 90,
            "duration_minutes": 45,
            "notes": "Updated",
        },
    )
    assert rejected.status_code == 400


def test_complete_service_creates_financial_entry_once(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    customer = client.post(
        "/api/customers",
        json={
            "name": "Completed Customer",
            "email": "completed@example.com",
            "phone": "555-8080",
            "address": "12 Main St",
            "service_type": "Scrub",
            "frequency": "Weekly",
            "notes": "",
        },
    ).json()
    service_day = future_date(5)
    service = client.post(
        "/api/services",
        json={
            "customer_id": customer["id"],
            "service_type": "Scrub",
            "job_date": service_day,
            "service_time": "10:00",
            "cost": 125,
            "duration_minutes": 60,
            "notes": "",
        },
    ).json()

    complete = client.post(f"/api/services/{service['id']}/complete")
    assert complete.status_code == 200
    entry = complete.json()["financial_entry"]
    assert entry["entry_type"] == "income"
    assert entry["category"] == "Completed Service"
    assert entry["service_record_id"] == service["id"]
    assert entry["amount"] == 125
    assert entry["entry_date"] == service_day

    listed_service = client.get("/api/services").json()["items"][0]
    assert listed_service["completed"] == 1

    duplicate = client.post(f"/api/services/{service['id']}/complete")
    assert duplicate.status_code == 200
    assert len(client.get("/api/financials").json()["items"]) == 1

    year, month = future_year_month(5)
    summary = client.get("/api/financials/summary", params={"year": year, "month": month}).json()
    assert summary["income"] == 125
    assert summary["net"] == 125


def test_logout_invalidates_session(tmp_path, monkeypatch):
    client = make_client(tmp_path, monkeypatch)
    setup_user(client)
    assert client.get("/api/me").status_code == 200
    assert client.post("/api/logout").status_code == 200
    assert client.get("/api/me").status_code == 401
