# PlaceChat-Team

PlaceChat is an anonymous, campus location-based chat website for college students. When students open the website, they automatically receive a random anonymous identity and can join chat rooms tied to real campus locations, such as libraries, student unions, and academic buildings, to talk in real time with people nearby without registering. Rooms near the student are recommended first, and any room can be joined. Administrators manage rooms, review reports, remove inappropriate messages, and temporarily block disruptive users, so the community stays safe while students remain anonymous.

Optional accounts, friends, direct messages, and campus announcements from student organizations are planned extensions and are not part of the current sprints.

## Tech stack

| Part | Technology | Hosting |
|---|---|---|
| Frontend | Next.js (App Router), React, TypeScript, Tailwind CSS | Vercel |
| Backend | FastAPI, Python 3.13 | Render |
| Data | Supabase PostgreSQL, Auth, Realtime | Supabase |

## Repository layout

| Path | Contents |
|---|---|
| [`frontend/`](frontend/) | Next.js app |
| [`backend/`](backend/) | FastAPI app |
| [`supabase/migrations/`](supabase/) | Database schema and policies |
| [`tools/loadtest/`](tools/loadtest/) | Load test script |
| [`docs/`](docs/) | [PlaceChat Technical Design](docs/technical-design.md): the architecture, API contract, and decisions every PR follows |

## Environments

| Environment | Frontend | Backend | Deployed from |
|---|---|---|---|
| Staging | https://placechat-staging.vercel.app | https://placechat-api-staging.onrender.com ([health](https://placechat-api-staging.onrender.com/health), [API docs](https://placechat-api-staging.onrender.com/docs)) | `main`, automatically on every merge |
| Production | Not live yet (PBI-45) | Not live yet (PBI-45) | `release`, through a pull request from `main` |

- Merging into `main` updates staging: Vercel rebuilds the frontend, Render rebuilds the backend when `backend/` changes, and the `migrate` workflow applies new files in `supabase/migrations/` to the staging database.
- Every pull request also gets a Vercel preview deployment, linked on the pull request.
- The staging backend runs on Render's free tier and sleeps after 15 minutes without traffic. The first request after that takes about a minute, so open the health link and wait for `{"status":"ok"}` before a demo or a test session.

## Run locally

You need Node.js 24, Python 3.13, and Git. Ask Junhao for the environment values.

Backend (http://localhost:8000):

```bash
cd backend
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
cp .env.example .env
uvicorn app.main:app --reload
```

Frontend (http://localhost:3000):

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev
```

Each app's README lists its checks: [frontend](frontend/README.md), [backend](backend/README.md).

## Contributing

Read [CONTRIBUTING.md](CONTRIBUTING.md). Work is tracked on the PlaceChat Team Board.
