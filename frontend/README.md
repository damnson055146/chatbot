# Study Abroad Assistant Frontend

This Vite + React + TypeScript workspace implements the web client described in `docs/frontend.md`. It ships with React Query, TailwindCSS, React Router, React Hook Form, Zod, Axios, and i18next pre-wired so feature teams can focus on RAG UX rather than boilerplate.

## Getting Started

```bash
npm install
npm run dev
```

The dev server defaults to <http://localhost:5173>. Configure backend connectivity via a local `.env` file (see **Environment Variables** below).

## Available Scripts

| Command | Description |
| --- | --- |
| `npm run dev` | Start the Vite dev server with HMR. |
| `npm run build` | Type-check and generate a production build (`dist/`). |
| `npm run preview` | Serve the production build locally. |
| `npm run lint` | Run ESLint across the codebase. |
| `npm run test` | Execute Vitest unit tests (jsdom environment). |
| `npm run test:watch` | Run Vitest in watch mode. |

## Environment Variables

Create `frontend/.env` (ignored by git) based on the sample below:

```
VITE_API_BASE=http://localhost:8000/v1
VITE_API_KEY=dev-secret-token
VITE_DEFAULT_LANGUAGE=en
VITE_STREAMING_MODE=server
VITE_STREAMING_CHUNK_SIZE=18
VITE_STREAMING_TICK_MS=35
```

Values cascade from the backend config; adjust per environment. The app reads them via `import.meta.env` when creating the Axios client, i18n bootstrap, and the streaming renderer:

- `VITE_STREAMING_MODE=server`: use backend SSE (`POST /v1/query?stream=true`) with Stop/Cancel support.
- `VITE_STREAMING_MODE=off`: fall back to non-streaming replies.

## Admin Console

The frontend also includes a lightweight admin console at `/admin` for inspecting `/v1/status`, `/v1/metrics`, and key governance endpoints. It requires the same `VITE_API_KEY` as the rest of the app.

## Project Layout

```
src/
  app/                # App shell & routing
  components/         # UI modules (layout, query console, etc.)
  hooks/              # Custom React hooks
  locales/            # i18next resource bundles (en/zh)
  services/           # API client wrappers
  state/              # React Query key helpers
  styles/             # Tailwind helpers / design tokens
  utils/              # Cross-cutting utilities (i18n init)
```

TailwindCSS utilities are available via `src/index.css`. Theme colors for brand elements are defined in `tailwind.config.js`.

## Testing

- Unit/spec tests: Vitest + React Testing Library (`npm run test`).
- Request stubbing: MSW is pre-installed; place handlers under `src/mocks` (to be added with feature work).
- Coverage reports: `npm run test -- --coverage` (HTML + text summary).

## Next Steps

1. Implement API data hooks and query console UI.
2. Build slot guidance components aligned with backend schemas.
3. Add observability pages consuming `/v1/status` and tracing metadata when available.

Refer back to `docs/frontend.md` for detailed requirements and roadmap.
