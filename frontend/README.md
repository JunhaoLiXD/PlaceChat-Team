# PlaceChat frontend

Next.js (App Router) + React + TypeScript + Tailwind CSS. See the root [README](../README.md) for the whole project.

## Run locally

```bash
cp .env.example .env.local   # then fill in the values (ask Junhao)
npm install
npm run dev                  # http://localhost:3000
```

## Checks (the same ones CI runs)

```bash
npm run lint
npm run typecheck
npm test
npm run build
npm run format:check         # npm run format to fix
```

## Browser sessions

Client code can call `ensureSession()` from `src/lib/session.ts` to reuse the stored Supabase session or create an anonymous identity without requesting personal information. Calls in the same tab share in-flight work; browsers supporting Web Locks also serialize first sign-ins across tabs. The shared browser client persists sessions and automatically refreshes tokens.

Call `getAccessToken()` immediately before each authenticated API request rather than keeping an access token in component state. Public room-list requests do not need a token. These helpers require the frontend Supabase URL and publishable key from `.env.local`; never use a backend secret key. Connecting the existing demo join/message flows to authenticated endpoints remains separate work.

## API types

`src/lib/api-types.ts` is generated from the backend's OpenAPI schema, so the frontend uses the exact request and response shapes FastAPI defines ([PlaceChat Technical Design §7.1](../docs/technical-design.md#71-rest-endpoints-prefix-apiv1)). Never edit it by hand. Whoever changes a backend route or Pydantic model regenerates it in the same pull request; otherwise the `api-types` CI check fails:

```bash
cd backend && python scripts/export_openapi.py ../frontend/openapi.json   # backend venv active
cd ../frontend && npm run api-types
```

Commit the updated `src/lib/api-types.ts`. `openapi.json` itself is not committed.

This Next.js version has breaking changes from older releases. Read [AGENTS.md](AGENTS.md) and the docs in `node_modules/next/dist/docs/` before relying on older examples.
