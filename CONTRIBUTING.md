# Contributing

1. `make setup`, copy `.env.example` → `.env`, `make db-migrate`, `make dev`.
2. Keep the layering: `routers → services → repos` (API), with business rules in services.
3. Before a PR: `make lint test`. If you touch retrieval, prompts or the parser, run `make eval` and
   include the metrics diff. CI blocks merges when `make eval-smoke` drops below its gate.
4. Conventional Commits (`feat:`, `fix:`, `docs:` …). Record non-trivial decisions as ADRs in `docs/DECISIONS.md`.
5. Only permissively licensed dependencies (MIT/BSD/Apache). No secrets in code or in the web bundle.
