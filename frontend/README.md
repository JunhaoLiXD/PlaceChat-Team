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

This Next.js version has breaking changes from older releases. Read [AGENTS.md](AGENTS.md) and the docs in `node_modules/next/dist/docs/` before relying on older examples.
