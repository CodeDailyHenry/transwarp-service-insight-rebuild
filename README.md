# SLA Intelligent Diagnosis

API-first backend and CLI skeleton for the SLA intelligent diagnosis service.

## Local development

Python 3.11 is required. Create an isolated environment and install the locked dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
```

Run the backend:

```powershell
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

## Quality checks

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m mypy src tests
.\.venv\Scripts\ruff.exe check .
.\.venv\Scripts\ruff.exe format --check .
```

## Docker Compose

Build and start the API:

```powershell
docker compose up --build -d
docker compose ps
```

Then run `sla ready`. Stop the stack with `docker compose down`.
