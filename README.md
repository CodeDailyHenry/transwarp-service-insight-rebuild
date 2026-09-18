# SLA Intelligent Diagnosis

API-first backend and CLI for the SLA intelligent diagnosis service. W01 provides
the service skeleton; W02 adds persistent identities, personal tokens and server-side
authorization. Diagnosis and knowledge workflows are subsequent work items.

## Local development

Python 3.11 is required. Create an isolated environment and install the locked dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Initialize the first administrator once, then run the backend:

```powershell
.\.venv\Scripts\sla-admin.exe bootstrap --username maintainer
.\.venv\Scripts\uvicorn.exe sla_assistant.api:app --reload
```

Check it through the CLI in another terminal:

```powershell
.\.venv\Scripts\sla.exe ready
```

Set `SLA_API_URL` in the CLI process environment or pass `--api-url` when the backend
is not at `http://127.0.0.1:8000`. Docker Compose reads `SLA_API_PORT` from the shell
or a local `.env` file; `.env.example` documents these public connection settings.
Never put credentials in either file.

The bootstrap command prints a JSON object containing the administrator and a personal
token. Save the token securely at issuance: the server stores only its SHA-256 hash and
cannot show it again. The token remains usable until reset or account disablement;
"once" refers to displaying the plaintext, not a single authenticated request.
Repeated bootstrap is rejected, including after a restart. There is no HTTP bootstrap
endpoint. `sla-admin` is a host deployment tool; the user-facing `sla` remains a pure
HTTP client.

Local development defaults to an ignored `sla-assistant.db` SQLite file in the working
directory. Start both commands from the same directory. For PostgreSQL, inject
`SLA_DATABASE_URL` (`postgresql+psycopg://...`) through the process environment, or use
`SLA_DATABASE_PASSWORD_FILE` with `SLA_DATABASE_HOST`, `SLA_DATABASE_USER`, and
`SLA_DATABASE_NAME` (defaults: `db`, `sla`, `sla`). Compose uses PostgreSQL and a mounted
password file. SQLite is only the development/test fallback.

## Identity API

Send `Authorization: Bearer <personal-token>` on every identity request. Use HTTPS
when requests cross machines; TLS termination is a deployment responsibility.

| Method and path | Access | Result |
| --- | --- | --- |
| `GET /v1/auth/me` | Any enabled account | Current identity, without token/hash |
| `GET /v1/admin/users` | Admin | Accounts, without token/hash |
| `POST /v1/admin/users` | Admin | Create `{ "username": "support" }`; optional `role`, default `user` |
| `PATCH /v1/admin/users/{id}` | Admin | Change `role` and/or `enabled` |
| `POST /v1/admin/users/{id}/reset-token` | Admin | Return new token once; old token immediately stops working |
| `GET /v1/admin/audit` | Admin | Latest 100 identity audit events, newest first |
| `GET /health/live` | Public | Process liveness |
| `GET /health/ready` | Public | Identity database accessibility |

Account creation and reset responses are `{ "user": {...}, "token": "..." }` with
`Cache-Control: no-store`. Tokens use 256 bits of random entropy. Disabled accounts
are rejected on every request; re-enabling restores the current token, so reset it
as well when a credential has been compromised. The last enabled administrator
cannot be demoted or disabled. Usernames are 1–64 ASCII letters/digits with dots,
underscores or hyphens after the first character; role values are `user`, `curator`,
and `admin`.

Business modules must attach `Depends(require_permission("<permission>"))` from
`sla_assistant.security` to restricted endpoints. The policy implements the V1 role
matrix, including curator import/edit privileges and admin-only publishing. Tests
exercise this guard over HTTP; those future business endpoints are not implemented
by W02. Missing/invalid/disabled tokens return 401; insufficient permission returns
403. Authentication, denied authorization, bootstrap, account changes and resets
produce persistent audit events containing identifiers, event names and timestamps,
never bearer tokens or their hashes.

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy src tests
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

CI repeats identity tests against PostgreSQL 16 as well as SQLite. To run the same
PostgreSQL tests locally, set `SLA_TEST_POSTGRES_URL` to a dedicated test database
and run `pytest tests/test_identity.py tests/test_identity_api.py`. Each test creates
and removes its own randomly named schema; the connection needs schema privileges.

## Docker Compose

Create `.secrets/postgres_password.txt` with a strong database password, using a
secret manager or an interactive prompt (do not put it in shell history). The
directory is ignored by Git and excluded from the image. Restrict its permissions
to the deployment account. Then build and start the API:

```powershell
docker compose up --build -d
docker compose ps
docker compose exec api sla-admin bootstrap --username maintainer
```

Then run `sla ready`. Stop the stack with `docker compose down`.
PostgreSQL data is retained in the `identity_data` volume. Do not remove that volume
when recreating containers. The password file must match the password used when
the volume was first initialized; changing the file alone does not rotate an
existing database password. The first schema is created at startup; future schema
changes will require explicit migrations.
