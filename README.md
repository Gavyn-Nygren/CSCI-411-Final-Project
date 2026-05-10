# CleanOps Secure Web Application

A secure client/server web application for small, service-oriented businesses. This MVP follows the project proposal by supporting:

- Business owner login/logout with bcrypt password hashing and HTTP-only cookie sessions
- Customer create/view/edit/search/filter
- Service records linked to customers
- Contract upload, list, and download
- Financial entry creation and reporting by month/service type
- SQLite database storage
- Server-side validation and least-privilege style routing

## Tech Stack

- **Frontend:** HTML, CSS, JavaScript
- **Backend:** Python FastAPI
- **Database:** SQLite
- **Security:** bcrypt, secure session cookies, server-side validation

## Project Structure

```
cleanops_secure_webapp/
├── app/
│   ├── main.py
│   ├── database.py
│   ├── models.py
│   ├── schemas.py
│   ├── security.py
│   ├── seed.py
│   ├── templates/
│   │   └── index.html
│   └── static/
│       ├── app.js
│       └── styles.css
├── uploads/
│   └── contracts/
├── requirements.txt
└── README.md
```

## Setup

1. Create and activate a virtual environment.
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
uvicorn app.main:app --reload
```

4. Open:

```text
http://127.0.0.1:8000
```

## First Login

On first run, the app auto-creates an admin account:

- **Username:** `admin`
- **Password:** `ChangeMe123!`

Change the password immediately in a real deployment.

## Security Notes

- Passwords are stored with **bcrypt** hashes.
- Sessions use a random opaque token stored in an **HTTP-only cookie**.
- All protected routes require authentication.
- Contract uploads are sanitized for filename collisions.
- In production, set `COOKIE_SECURE = True` and place the app behind **HTTPS**.
- Store the SQLite file and upload directory with restricted OS permissions.

## Future Enhancements

- Role-based authorization if the app expands beyond one admin user
- CSRF tokens for stricter browser form protection
- Audit logging for sensitive record updates
- Encrypted backups and automated backup jobs
- File type scanning and stricter upload policies
