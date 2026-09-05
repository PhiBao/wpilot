# wpilot-ui

Coordinator console + live demo console + volunteer confirm page (Next.js).

## Setup

```bash
pnpm install
```

## Run (needs the API)

```bash
# terminal 1 — API (from wpilot-agent/, venv active)
uvicorn wpilot.server:app --port 8000

# terminal 2 — UI
NEXT_PUBLIC_WPILOT_API=http://localhost:8000 pnpm dev
```

Pages: `/` coordinator console · `/demo` live demo console ·
`/confirm/[messageId]` no-login volunteer accept page.
