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
- [Authentication and per-user isolation](#authentication-and-per-user-isolation)
- [Ticket lifecycle](#ticket-lifecycle)
  - [Reading a ticket back](#reading-a-ticket-back)
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
| `DATABASE_PATH` | `./app/data/db/mock.db` | Path to the SQLite database file. Kept in its own directory so the container volume that persists it cannot shadow `schema.sql` or the seed fixtures next to it. |
| `TOOLS_API_KEY` | `change-me` | The agent's API key, sent as `X-API-Key`. This default only applies when running the service on its own; the full stack sets it from the project's `.env`, where it is `local-demo-tools-key`. |
| `OPERATOR_API_KEY` | `change-me-operator` | The operations console's API key. The list endpoints and the state-changing development endpoints accept only this one, and a caller holding it is outside the per-customer isolation rule. Must differ from `TOOLS_API_KEY`. |
| `IDENTITY_ISOLATION` | `enforced` | `enforced` refuses any customer-scoped request that carries no `X-End-User-Id` header, and refuses an end user already linked to a different customer. `disabled` removes the boundary; the service logs a warning at every boot and `GET /health` reports which mode is active. |
| `IDENTITY_REBINDING` | `denied` | What happens when a linked end user presents a different identification number: `denied` refuses with `403`, `allowed` moves the link. |

Copy `.env.example` to `.env` and adjust as needed; `docker-compose.yml` reads these from the
host environment (falling back to the same defaults) so a production deployment isn't stuck
with the sample keys.

## API documentation

Once the service is running, interactive OpenAPI documentation is available at:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`
- Raw schema: `http://localhost:8000/openapi.json`

Every request other than `/health` and the docs pages requires the `X-API-Key` header. Requests
that touch a customer also require `X-End-User-Id`: see
[Authentication and per-user isolation](#authentication-and-per-user-isolation).

## Domains

The API is organized into six tagged domains, matching how they appear in `/docs`:

| Domain | Purpose |
|---|---|
| `clients` | Client identification and registration (identification only, not authentication). |
| `catalog` | Product browsing and comparison for consultative sales. |
| `orders` | Order status, delivery tracking, and simulated purchases. |
| `warranty` | Warranty coverage checks and claim filing, with automatic safety escalation. |
| `sessions` | Current and cross-session conversational memory. |
| `escalations` | Support tickets: every warranty claim, plus the hand-overs the agent raises and the automatic safety escalation, worked through their lifecycle from the operations console and readable by the customer they belong to. |

## Authentication and per-user isolation

Two keys, two principals. `TOOLS_API_KEY` identifies the agent; `OPERATOR_API_KEY` identifies
the operations console. The agent's key is matched first, so setting both to the same value
degrades into a `403` on the operator endpoints rather than quietly promoting the agent.

Operator-only endpoints, which are deliberately outside the agent's tool catalog:
`GET /api/v1/orders`, `GET /api/v1/orders/by-client/{client_id}`,
`PATCH /api/v1/orders/{order_id}/status`, `GET /api/v1/warranty`, the three
`PATCH /api/v1/warranty/...` development endpoints, `GET /api/v1/escalations` and
`PATCH /api/v1/escalations/{ticket_id}`. `GET /api/v1/escalations/mine` is the one endpoint
under that prefix the agent may call, and it is customer-scoped rather than operator-only.

On top of the key, every request made on behalf of a chat user carries `X-End-User-Id`, the id
of whoever the chat frontend authenticated. The service links that subject to the first
customer it verifies or registers for them, in `identity_bindings`, and afterwards refuses any
other customer with `403`. The error codes are `identity_required` (no header),
`identity_not_verified` (no customer identified yet) and `identity_mismatch` (linked to another
customer). Where the customer can be derived from that link it is never taken from the request
body: `POST /api/v1/orders`, `POST /api/v1/warranty/claims`, `GET /api/v1/orders/mine` and
`GET /api/v1/escalations/mine` all work it out themselves. The root `README.md` has the full
rationale.

## Ticket lifecycle

Every ticket number the store issues is a row in `escalations`, whichever of the three ways it
was born, so a number given to a customer always resolves to exactly one ticket:

| `origin` | Issued when | Priority |
|---|---|---|
| `warranty_claim` | any claim is filed; the ticket reuses the number `POST /api/v1/warranty/claims` returns | `medium` |
| `safety_risk` | the same, when the description matches a safety keyword; again the same number | `high` |
| `agent_request` | the agent calls `POST /api/v1/escalations` | as requested |

A claim keeps its own `claim_id` and its own row in `warranty_claims`, which holds what the
claim is about; the ticket holds where it is in the queue. The two are joined by `ticket_id`,
which is unique in both tables.

`pending_agent -> in_progress -> resolved`, with `resolved -> in_progress` to reopen. Moving to
`in_progress` needs an `assignee`; moving to `resolved` needs a `resolution_note`. A ticket
whose `origin` is `safety_risk` cannot go from `pending_agent` straight to `resolved`; it
returns `409 human_review_required` until somebody has taken it. The other two origins can be
closed in one step.

### Reading a ticket back

`GET /api/v1/escalations/mine` returns the tickets of the customer the caller is bound to, and
takes no ticket number: a number belonging to somebody else is absent from the answer rather
than refused, so the endpoint cannot be used to probe whether one exists. It returns the ticket
number, `origin`, `status`, a `topic`, the timestamps and `related_ticket_id`. For a claim the
topic is the customer's own description of the fault; for a hand-over it is the reason the
agent gave for escalating, which is a paraphrase rather than the customer's words. It deliberately withholds `assignee`, `resolution_note` and `priority`:
those are written for the operations console, and an internal closing note or a member of
staff's name has no business being read out in a chat window.

`POST /api/v1/escalations` accepts an optional `related_ticket_id`, so a hand-over to a person
about a case that already has a ticket is stored as that ticket's follow-up instead of as a
second unrelated number. The link is best-effort: a number that is not one of this customer's
own tickets is dropped rather than refused, because a wrong number must never block a request
for a human, and the response echoes `related_ticket_id` so a dropped link is visible.

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
│   ├── auth.py            # X-API-Key verification, agent and operator principals
│   ├── identity.py        # per-user isolation: the trusted subject and its binding
│   ├── errors.py          # uniform error envelope
│   ├── db.py               # SQLite connection, schema init, seeding
│   ├── data/
│   │   ├── schema.sql      # table definitions
│   │   ├── db/             # the SQLite file; the container volume mounts here
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

Outside Docker, the database lives at `app/data/db/mock.db` and is created on first run; delete
that file to start from a clean seed.

Inside Docker, `app/data/` (schema, seed fixtures, and the generated database) is mounted on a
named volume so data survives a `docker compose restart`. Because that volume is only populated
once, it does **not** pick up later changes to the seed fixtures on its own -- if the seed data
changes, reset with:

```bash
docker compose down -v
docker compose up api --build
```
