# Core API

![Python](https://img.shields.io/badge/Python-3.14-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688?logo=fastapi&logoColor=white)
![Pydantic](https://img.shields.io/badge/Pydantic-2.x-E92063?logo=pydantic&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-3-07405E?logo=sqlite&logoColor=white)
![Pytest](https://img.shields.io/badge/tested%20with-pytest-0A9EDC?logo=pytest&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)

A FastAPI microservice that exposes the business logic (catalog, orders, warranty, escalations,
session memory) behind an AI customer-service agent for an electronics retailer. It is called
as a set of tools by an orchestration layer (n8n) and has no UI of its own.

## Table of contents

- [Tech stack](#tech-stack)
- [Quick start](#quick-start)
  - [Option A: Docker](#option-a-docker-recommended)
  - [Option B: Local (Python virtualenv)](#option-b-local-python-virtualenv)
- [Environment variables](#environment-variables)
- [API documentation](#api-documentation)
- [Domains](#domains)
- [Running the tests](#running-the-tests)
- [Project structure](#project-structure)
- [Persistence and resetting data](#persistence-and-resetting-data)

## Tech stack

| Layer | Choice |
|---|---|
| Language | Python 3.14 |
| Web framework | FastAPI + Uvicorn |
| Validation | Pydantic v2 |
| Persistence | SQLite (stdlib `sqlite3`, no ORM) |
| Tests | pytest |
| Container | Docker / Docker Compose |

## Quick start

### Option A: Docker (recommended)

From the repository root (one level above `core-api/`):

```bash
docker compose up api --build
```

This builds the image, seeds the SQLite database on first boot, and serves the API on
`http://localhost:8000`. Verify it's up:

```bash
curl http://localhost:8000/health
# {"status":"ok"}
```

Stop it with `docker compose down`, or `docker compose down -v` to also drop the persisted
database volume (see [Persistence and resetting data](#persistence-and-resetting-data)).

### Option B: Local (Python virtualenv)

From `core-api/`:

```bash
python3 -m venv .venv
source .venv/bin/activate        # .venv\Scripts\activate on Windows
pip install -r requirements.txt
cp .env.example .env             # edit values if needed, see below
uvicorn app.main:app --reload --env-file .env
```

The API is then served on `http://localhost:8000`. The SQLite database and its seed data are
created automatically the first time the app starts (`app/data/mock.db`, gitignored).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `DATABASE_PATH` | `./app/data/mock.db` | Path to the SQLite database file. |
| `TOOLS_API_KEY` | `change-me` | Static API key every request must send as the `X-API-Key` header. |

Copy `.env.example` to `.env` and adjust as needed; `docker-compose.yml` reads `TOOLS_API_KEY`
from the host environment (falling back to the same default) so a production deployment isn't
stuck with the sample key.

## API documentation

Once the service is running, interactive OpenAPI documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Raw schema: `http://localhost:8000/openapi.json`

Every request other than `/health` and the docs pages requires the `X-API-Key` header.

## Domains

The API is organized into six tagged domains, matching how they appear in `/docs`:

| Domain | Purpose |
|---|---|
| `clients` | Client identification and registration (identification only, not authentication). |
| `catalog` | Product browsing and comparison for consultative sales. |
| `orders` | Order status, delivery tracking, and simulated purchases. |
| `warranty` | Warranty coverage checks and claim filing, with automatic safety escalation. |
| `sessions` | Current and cross-session conversational memory. |
| `escalations` | Manual escalation of a case to a human agent. |

## Running the tests

```bash
cd core-api
source .venv/bin/activate
python3 -m pytest -q
```

The suite runs entirely against temporary, throwaway SQLite databases (`tmp_path` fixtures) and
never touches `app/data/mock.db`.

## Project structure

```
core-api/
├── app/
│   ├── main.py          # FastAPI app, router registration, OpenAPI tags
│   ├── config.py         # environment variable loading
│   ├── auth.py            # X-API-Key verification
│   ├── errors.py          # uniform error envelope
│   ├── db.py               # SQLite connection, schema init, seeding
│   ├── data/
│   │   ├── schema.sql      # table definitions
│   │   └── seed/           # fixture JSON loaded on first boot
│   ├── schemas/             # Pydantic models and validators, one file per domain
│   ├── repositories/        # SQL access and domain rules, one file per domain
│   └── routers/              # HTTP endpoints, one file per domain
├── tests/                     # pytest suite, mirrors app/ by domain
├── Dockerfile
├── .dockerignore
├── .env.example
└── requirements.txt
```

## Persistence and resetting data

Outside Docker, the database lives at `app/data/mock.db` and is created on first run; delete
that file to start from a clean seed.

Inside Docker, `app/data/` (schema, seed fixtures, and the generated database) is mounted on a
named volume so data survives a `docker compose restart`. Because that volume is only populated
once, it does **not** pick up later changes to the seed fixtures on its own -- if the seed data
changes, reset with:

```bash
docker compose down -v
docker compose up api --build
```
