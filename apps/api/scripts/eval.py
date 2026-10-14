"""Evaluation harness (docs/07): retrieval recall, abstain accuracy and (with an LLM key) answer quality.

Usage:
  uv run python scripts/eval.py                 # full golden set (5 arXiv papers; imports them if missing)
  uv run python scripts/eval.py --smoke         # fixture-only set used as the CI gate
  uv run python scripts/eval.py --smoke --gate  # exit 1 when below thresholds

Each item: {"paper": arXiv id | "fixture:<name>", "q", "must": [phrases], "answerable", "hard"?}
- retrieval hit@8: some selected chunk contains every `must` phrase (case/space-insensitive)
- abstain: unanswerable (non-hard) items must trip the abstain gate; answerable ones must not
- with an LLM: answer cites a chunk containing the phrases; hard unanswerables must return NOT_FOUND
"""

import argparse
import asyncio
import json
import re
import statistics
import sys
import time
import uuid
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app import db
from app.auth import CurrentUser
from app.config import get_settings
from app.jobs.handlers import build_handlers
from app.jobs.worker import Worker
from app.providers.registry import build_providers
from app.services import chat, papers
from app.services.retrieval import retrieve

ROOT = Path(__file__).resolve().parents[3]
GATE = {"recall_at_8": 0.8, "abstain_accuracy": 0.85}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).replace("−", "-")


def contains(textv: str, must: list[str]) -> bool:
    t = norm(textv)
    return all(norm(m) in t for m in must)


async def ensure_user(s: AsyncSession) -> CurrentUser:
    uid = uuid.UUID("00000000-0000-4000-8000-0000000e7a11")
    await s.execute(
        text(
            'insert into "user" (id, name, email, "emailVerified") values (:i, :n, :e, true) on conflict do nothing'
        ),
        {"i": uid, "n": "eval", "e": "eval@paperly.invalid"},
    )
    await s.commit()
    return CurrentUser(uid, None, {})


async def ensure_paper(
    s: AsyncSession, settings: Any, providers: Any, user: CurrentUser, ref: str
) -> uuid.UUID:
    if ref.startswith("fixture:"):
        from tests.fixtures.make_pdfs import make_all

        pdf = make_all(ROOT / ".tmp_fixtures")[ref.split(":", 1)[1]]
        out = await papers.upload(s, settings, providers, user, pdf.read_bytes(), pdf.name, None)
    else:
        out = await papers.import_paper(s, settings, user, "arxiv", ref, None)
    return out["paper_id"]


async def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--smoke", action="store_true")
    ap.add_argument("--gate", action="store_true")
    ap.add_argument("--no-llm", action="store_true")
    args = ap.parse_args()
    settings = get_settings()
    settings.quota_questions_per_day = 10_000
    settings.quota_imports_per_day = 10_000
    providers = build_providers(settings)
    use_llm = providers.llm.available and not args.no_llm
    items = [
        json.loads(x)
        for x in (ROOT / "evals" / ("smoke.jsonl" if args.smoke else "golden.jsonl")).read_text().splitlines()
        if x.strip()
    ]
    engine = db.get_engine()

    async with AsyncSession(engine) as s:
        user = await ensure_user(s)
        pids: dict[str, uuid.UUID] = {}
        for ref in dict.fromkeys(i["paper"] for i in items):
            pids[ref] = await ensure_paper(s, settings, providers, user, ref)
    worker = Worker(build_handlers(providers, settings), 1)
    while await worker.run_once():
        pass
    bad: list[Any] = []
    for _ in range(120):  # another worker (e.g. a running dev server) may be indexing them
        async with engine.connect() as c:
            bad = list((await c.execute(text("select id, status from papers where id = any(:i) and status <> 'ready'"),
                                        {"i": list(pids.values())})).all())  # fmt: skip
        if not bad or any(b[1] == "failed" for b in bad):
            break
        await worker.run_once() or await asyncio.sleep(5)
    if bad:
        print("papers not ready:", bad)
        return 1

    rows: list[dict[str, Any]] = []
    for it in items:
        pid = pids[it["paper"]]
        t0 = time.perf_counter()
        async with AsyncSession(engine) as s:
            r = await retrieve(s, providers, it["q"], [pid], tau=settings.abstain_threshold)
        ms = (time.perf_counter() - t0) * 1000
        abstained = r.abstain(settings.abstain_threshold, settings.abstain_vsim, it["q"])
        rank = (
            next((k for k, h in enumerate(r.hits[:8], 1) if contains(h.chunk["text"], it["must"])), None)
            if it["must"]
            else None
        )
        row: dict[str, Any] = {**it, "abstained": abstained, "rank": rank, "retrieval_ms": round(ms),
                               "best_rerank": round(r.best_score, 3), "best_vsim": round(r.best_vsim, 3)}  # fmt: skip
        if use_llm and (it["answerable"] or it.get("hard")):
            async with AsyncSession(engine) as s:
                t = await chat.create_thread(s, user, {"paper_ids": [str(pid)]}, "eval")
                t0 = time.perf_counter()
                answer, cits, done = "", [], {}
                async for ev in chat.ask(s, settings, providers, user, t, it["q"], mode="grounded", level="student",
                                         lang="en", selection=None):  # fmt: skip
                    kind, data = ev.split("\n")[0][7:], json.loads(ev.split("\n")[1][6:])
                    if kind == "token":
                        answer += data["t"]
                    elif kind == "citation":
                        cits.append(data)
                    elif kind == "done":
                        done = data
                row.update(
                    answer=answer[:600], not_found=bool(done.get("not_found")), grounded=done.get("grounded"),
                    support=done.get("support_score"), ttft_ms=done.get("ttft_ms"),
                    total_ms=round((time.perf_counter() - t0) * 1000), provider=done.get("provider"),
                    answer_has_fact=contains(answer, it["must"]) if it["must"] else None,
                    cites_fact=any(contains(c["quote"], it["must"]) for c in cits) if it["must"] else None,
                )  # fmt: skip
        rows.append(row)
        print(("✓" if (rank or (not it["answerable"] and abstained)) else "✗"), it["q"][:70], "| rank", rank,
              "| abstain", abstained, "|", row.get("answer", "")[:80].replace("\n", " "))  # fmt: skip

    ans = [r for r in rows if r["answerable"]]
    easy_un = [r for r in rows if not r["answerable"] and not r.get("hard")]
    metrics: dict[str, Any] = {
        "items": len(rows),
        "recall_at_8": round(sum(1 for r in ans if r["rank"]) / max(1, len(ans)), 3),
        "mrr": round(statistics.mean([1 / r["rank"] if r["rank"] else 0 for r in ans]) if ans else 0, 3),
        "false_abstain_rate": round(sum(1 for r in ans if r["abstained"]) / max(1, len(ans)), 3),
        "abstain_accuracy": round(
            (sum(1 for r in ans if not r["abstained"]) + sum(1 for r in easy_un if r["abstained"]))
            / max(1, len(ans) + len(easy_un)),
            3,
        ),
        "retrieval_p95_ms": round(sorted(r["retrieval_ms"] for r in rows)[int(len(rows) * 0.95) - 1]),
        "llm": use_llm,
    }
    if use_llm:
        llm_rows = [r for r in rows if "answer" in r]
        a = [r for r in llm_rows if r["answerable"]]
        hard = [r for r in llm_rows if r.get("hard")]
        metrics.update(
            answer_correct=round(sum(1 for r in a if r["answer_has_fact"]) / max(1, len(a)), 3),
            citation_hit=round(sum(1 for r in a if r["cites_fact"]) / max(1, len(a)), 3),
            grounded_rate=round(sum(1 for r in a if r["grounded"]) / max(1, len(a)), 3),
            hard_unanswerable_not_found=round(sum(1 for r in hard if r["not_found"]) / max(1, len(hard)), 3) if hard else None,
            ttft_p95_ms=round(sorted(r["ttft_ms"] or 0 for r in a)[max(0, int(len(a) * 0.95) - 1)]) if a else None,
        )  # fmt: skip
    name = "smoke" if args.smoke else "golden"
    out = ROOT / "evals" / f"report-{name}.md"
    lines = [f"# Paperly eval — {name}", "", f"Run: {time.strftime('%Y-%m-%d %H:%M')} · LLM: {'yes' if use_llm else 'no (retrieval + abstain only)'}", "",
             "| Metric | Value |", "|---|---|", *[f"| {k} | {v} |" for k, v in metrics.items()], "",
             "## Misses", ""]  # fmt: skip
    for r in rows:
        miss = (r["answerable"] and (not r["rank"] or r["abstained"])) or (
            not r["answerable"] and not r.get("hard") and not r["abstained"]
        )
        if miss:
            lines.append(
                f"- `{r['paper']}` {r['q']} — rank {r['rank']}, abstained {r['abstained']}, rerank {r['best_rerank']}, vsim {r['best_vsim']}"
            )
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    (ROOT / "evals" / f"baseline-{name}.json").write_text(json.dumps(metrics, indent=2) + "\n")
    print(json.dumps(metrics, indent=2))
    await db.dispose()
    if args.gate:
        failed = {k: metrics[k] for k, v in GATE.items() if metrics[k] < v}
        if failed:
            print("EVAL GATE FAILED:", failed)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
