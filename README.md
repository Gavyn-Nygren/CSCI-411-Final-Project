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

```text
cleanops_secure_webapp/
|-- app/
|   |-- main.py
|   |-- database.py
|   |-- security.py
|   |-- validation.py
|   |-- templates/
|   |   `-- index.html
|   `-- static/
|       |-- app.js
|       `-- styles.css
|-- tests/
|   `-- test_app.py
|-- uploads/
|   `-- contracts/
|-- requirements.txt
`-- README.md
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

## First Run Owner Setup

The app does **not** ship with a hardcoded username or password. On first launch, the login screen becomes an owner setup screen. Create the owner account with a password that includes:

- 8-128 characters
- uppercase and lowercase letters
- a number
- a special character from `@$!%*?&`

After setup, the owner account is stored in SQLite with a bcrypt password hash.

## Security Notes

- Passwords are stored with **bcrypt** hashes.
- Sessions use a random opaque token stored in an **HTTP-only cookie**.
- All protected routes require authentication.
- SQL queries use parameterized SQLite statements.
- Browser output uses DOM text APIs for user-provided values.
- Contract uploads are size-limited, extension-limited, checksummed, and stored outside the static web path.
- The app avoids shell command execution APIs.
- In production, set `COOKIE_SECURE = True` and place the app behind **HTTPS**.
- Store the SQLite file and upload directory with restricted OS permissions.
- Back up the SQLite database and contract upload directory regularly.
- Run the server under a process manager that restarts it after crashes.

## Tests

Run the focused security and workflow tests:

```bash
pytest
```

## Future Enhancements

- Role-based authorization if the app expands beyond one admin user
- CSRF tokens for stricter browser form protection
- Audit logging for sensitive record updates
- Encrypted backups and automated backup jobs
- File type scanning and stricter upload policies
