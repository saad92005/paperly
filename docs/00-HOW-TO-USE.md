# 00 · How to use this blueprint with Claude Code

1. **Create the repo.** `mkdir paperly && cd paperly && git init`. Copy this whole pack in: `CLAUDE.md`, `MASTER_PROMPT.md` and the `docs/` folder (with `docs/diagrams/`).
2. **Install the basics** on your machine: Git, Docker Desktop (for the local Supabase stack), Node.js LTS + pnpm, Python 3.12 + `uv`, the Supabase CLI. Claude Code can install project dependencies, but these system tools should exist first.
3. **Get free API keys** (5 minutes): Groq Console, Google AI Studio (Gemini), OpenRouter. Optional later: Langfuse, Sentry. Keep them for the `.env` file Claude Code will create — never paste keys into the chat.
4. **Open the folder in VS Code → start Claude Code → paste the box from `MASTER_PROMPT.md`.** Claude Code reads every doc, summarises its plan and builds Phase 0.
5. **One phase per session.** When a phase is done (its Definition of Done is met), start a new session with the *Phase kickoff prompt* from `MASTER_PROMPT.md`. Fresh sessions keep Claude Code focused; `docs/PROGRESS.md` and `docs/DECISIONS.md` carry the memory between sessions.
6. **Check the work yourself** at the end of each phase: run the commands Claude Code gives you, click through the feature, and look at the debug view for ingestion. Ask for fixes with the *Fix-it prompt*.
7. **Ship the MVP (Phase 6) before any v1.5 feature.** A live, working, measured MVP beats a half-built feature list — for users, for your portfolio and for future clients.

**Tip — rename freely.** "Paperly" is a working name. Change it in one place (`APP_NAME` in config and the web `site.ts`) before launch.

**Tip — tools.** If the Context7 MCP server is connected in Claude Code, it fetches current library docs (Next.js, FastAPI, pdf.js, Supabase) so the generated code matches today's APIs.
