# LifePilot AI

Your Personal AI Operating System: a context-aware assistant that understands,
remembers, retrieves, decides, executes and verifies.

## Repository layout

```
apps/web/       React web dashboard (Vite + Tailwind)
backend/        FastAPI app + AI engineering layer (modular monolith)
  app/core/     config, logging, error handling
  app/db/       SQLAlchemy engine, sessions, base model
  app/modules/  business domains (no LLM code here)
  app/ai/       providers, tools, orchestration (may call modules, never the reverse)
  tests/
docs/           architecture notes and decisions
```

See [docs/architecture.md](docs/architecture.md) for the system design.

## Local setup (Windows / PowerShell)

Requires Python 3.14 and a Neon Postgres project (see [docs/architecture.md](docs/architecture.md#9-configuration-and-environments)).

```powershell
cd backend
py -3.14 -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements-dev.txt

Copy-Item ..\.env.example ..\.env   # then fill in the Neon URLs (or: neon env pull)
alembic upgrade head                # apply database migrations
uvicorn app.main:app --reload       # http://127.0.0.1:8000/docs
```

All backend commands run from `backend/`.

### Trying the API

Open http://127.0.0.1:8000/docs, then:

1. `POST /api/v1/auth/register` with your email, name and a password of 12+ characters.
2. `POST /api/v1/auth/login` and copy `access_token` from the response.
3. Click **Authorize** (top right), paste the token, and call `GET /api/v1/users/me`.
4. `POST /api/v1/chat` with `{"message": "Plan my week"}`. Send the returned
   `conversation.id` as `conversation_id` to continue the same conversation.

Chat needs `OPENROUTER_API_KEY` in `.env`. To try a model from the terminal without the API:

```powershell
python -m app.ai.cli "In one sentence, what is a token?"
python -m app.ai.cli --model anthropic/claude-haiku-5.5 "..."   # any OpenRouter model id
```

## Web app (apps/web)

Vite + React + TypeScript + Tailwind. Sign-in and the Assistant (chat history, real model
replies) use the real backend; the dashboard and finance screens still show sample data from
`src/api/mock.ts`.

Start the backend first (`uvicorn app.main:app --reload` in `backend/`), then:

```powershell
cd apps/web
npm install
npm run dev      # http://localhost:5173 (proxies /api to http://localhost:8000)
npm run build    # type-check + production build
npm run lint
```

Pages get data only through `src/api/client.ts`; each backend phase replaces a mock
function there with a real API call.

## Tests

```powershell
cd backend
pytest
```

Tests run with `APP_ENV=test` against `TEST_DATABASE_URL` (a separate Neon branch). The test
run drops and rebuilds that database from migrations, and the app refuses to start in test mode
if `TEST_DATABASE_URL` is missing or points at the main database.

## Status

- Phase 1 – Foundation: complete
- Phase 2 – Authentication: complete, including web sessions (2b) and Sign in with Google (2c);
  login rate limiting pending
- Phase 3 – AI assistant: LLM provider layer (3.1), stored conversations with `POST /chat` (3.2)
  and streaming replies with Stop (3.3) done; structured outputs and tool calling next
