"""Comparison matrix (docs/06 §3): per-paper retrieval per column, one extraction call per paper,
strict verification of every cell. Without an LLM, cells get the best matching sentence instead."""

import csv
import io
import re
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app import db, prompts
from app.jobs.worker import JobContext, RetryableError
from app.providers.llm import ProviderError
from app.providers.registry import Providers
from app.repos import library as repo
from app.repos import papers as papers_repo
from app.services.answer import SentenceIndex, citation_payload, cosine
from app.services.retrieval import Hit, retrieve
from app.services.structured import cite_items, llm_json, sources_block

DEFAULT_COLUMNS = [
    ("task", "Task / problem", "What task or problem does the paper address?"),
    ("method", "Method", "What is the proposed method or model, in one line?"),
    ("data", "Data", "Which datasets or data sources are used?"),
    ("metrics", "Metrics", "Which evaluation metrics are reported?"),
    ("results", "Key results", "What are the headline quantitative results?"),
    ("compute", "Compute / efficiency", "What compute, training cost or efficiency figures are given?"),
    ("limitations", "Limitations", "What limitations are stated?"),
    ("code", "Code availability", "Is code or data released, and where?"),
]


def default_columns() -> list[dict[str, str]]:
    return [{"key": k, "label": label, "question": q} for k, label, q in DEFAULT_COLUMNS]


def column_key(label: str, existing: list[dict[str, str]]) -> str:
    base = re.sub(r"[^a-z0-9]+", "_", label.lower()).strip("_")[:24] or "col"
    key, n = base, 2
    keys = {c["key"] for c in existing}
    while key in keys:
        key, n = f"{base}_{n}", n + 1
    return key


async def fill_paper(
    s: AsyncSession, providers: Providers, paper_id: UUID, columns: list[dict[str, str]]
) -> dict[str, Any]:
    paper = await papers_repo.get_paper(s, paper_id)
    title = (paper or {}).get("title") or "Untitled"
    # Retrieve top chunks per column question and merge (dedupe) into one source list.
    hits: list[Hit] = []
    seen: set[Any] = set()
    for col in columns:
        r = await retrieve(s, providers, col["question"], [paper_id], tau=0.0, per_paper=3)
        for h in r.hits[:3]:
            if h.chunk["id"] not in seen:
                seen.add(h.chunk["id"])
                hits.append(h)
    hits = hits[:18]
    if not providers.llm.available:
        return await _extractive_cells(providers, hits, columns)
    cols = [{"key": c["key"], "question": c["question"]} for c in columns]
    prompt = prompts.COMPARE.format(title=title, columns=cols, sources=sources_block(hits))
    try:
        data, _ = await llm_json(providers, "chat", prompt, max_tokens=1800)
    except ProviderError as exc:
        raise RetryableError(str(exc)) from exc
    raw_cells = data.get("cells", {}) if isinstance(data, dict) else {}
    items: list[tuple[str, list[str]]] = []
    keys: list[str] = []
    for c in columns:
        cell = raw_cells.get(c["key"]) or {}
        if cell.get("value") and not cell.get("not_found"):
            items.append((str(cell["value"]), list(cell.get("sources") or [])))
            keys.append(c["key"])
    cits = await cite_items(providers, hits, items)
    out: dict[str, Any] = {}
    for c in columns:
        out[c["key"]] = {"value": None, "citations": [], "status": "not_found", "confidence": None}
    for key, (value, _), ct in zip(keys, items, cits, strict=True):
        cell = raw_cells.get(key) or {}
        out[key] = {"value": value[:220], "citations": ct, "status": "ok" if ct else "unverified",
                    "confidence": cell.get("confidence")}  # fmt: skip
    await _verify(providers, out)
    return out


async def _verify(providers: Providers, cells: dict[str, Any]) -> None:
    """Strict mode: every cell's value must be supported by its cited sentences."""
    todo = [(k, c) for k, c in cells.items() if c["status"] == "ok"]
    if not todo:
        return
    claims = "\n".join(f"{i}. {c['value']}" for i, (_, c) in enumerate(todo, 1))
    evidence = "\n".join(
        f"{i}. " + " | ".join(ct["quote"][:300] for ct in c["citations"]) for i, (_, c) in enumerate(todo, 1)
    )
    try:
        data, _ = await llm_json(providers, "chat", prompts.VERIFY.format(claims=claims, evidence=evidence),
                                 max_tokens=900)  # fmt: skip
    except Exception:
        for _, c in todo:
            c["verified"] = None
        return
    labels = {int(r.get("id", 0)): r for r in (data.get("results") or []) if isinstance(r, dict)}
    for i, (_, c) in enumerate(todo, 1):
        lab = labels.get(i, {}).get("label")
        c["verified"] = lab
        if lab == "unsupported":
            c["status"] = "unsupported"
        elif lab == "partial":
            c["status"] = "partial"


async def _extractive_cells(
    providers: Providers, hits: list[Hit], columns: list[dict[str, str]]
) -> dict[str, Any]:
    sindex = SentenceIndex(providers)
    qvecs = await providers.embeddings.embed([c["question"] for c in columns], kind="query")
    out: dict[str, Any] = {}
    for col, qv in zip(columns, qvecs, strict=True):
        best: tuple[float, Hit | None, int] = (0.0, None, 0)
        for h in hits:
            for i, v in enumerate(await sindex.vectors(h.chunk)):
                sc = cosine(qv, v)
                if sc > best[0]:
                    best = (sc, h, i)
        score, hit, i = best
        if hit is None or score < 0.6:
            out[col["key"]] = {"value": None, "citations": [], "status": "not_found", "confidence": None}
            continue
        cit = citation_payload(1, hit, [(i, score)])
        out[col["key"]] = {"value": cit["quote"][:220], "citations": [cit], "status": "extractive",
                           "confidence": "low"}  # fmt: skip
    return out


def make_compare_handler(providers: Providers):
    async def handle(job: dict[str, Any], ctx: JobContext) -> None:
        cid = UUID(job["payload"]["comparison_id"])
        only = job["payload"].get("column_keys")
        async with AsyncSession(db.get_engine()) as s:
            cmp = await repo.get_comparison(s, cid)
            if cmp is None:
                return
            await repo.set_comparison(s, cid, status="running")
            await s.commit()
            columns = [c for c in cmp["columns"] if not only or c["key"] in only]
            n = len(cmp["paper_ids"])
            for i, pid in enumerate(cmp["paper_ids"]):
                await ctx.progress(f"paper {i + 1} of {n}", int(100 * i / n))
                cells = await fill_paper(s, providers, pid, columns)
                await repo.set_cells(s, cid, str(pid), cells)
                await s.commit()
            await repo.set_comparison(s, cid, status="done")
            await s.commit()

    async def on_final_failure(job: dict[str, Any], message: str) -> None:
        async with AsyncSession(db.get_engine()) as s:
            await repo.set_comparison(s, UUID(job["payload"]["comparison_id"]), status="failed")
            await s.commit()

    handle.on_final_failure = on_final_failure  # type: ignore[attr-defined]
    return handle


def export_rows(cmp: dict[str, Any], titles: dict[str, str]) -> tuple[list[str], list[list[str]]]:
    header = ["Paper", *[c["label"] for c in cmp["columns"]]]
    rows: list[list[str]] = []
    for pid in cmp["paper_ids"]:
        cells = cmp["cells"].get(str(pid), {})
        row = [titles.get(str(pid), "Untitled")]
        for c in cmp["columns"]:
            cell = cells.get(c["key"]) or {}
            v = cell.get("value") or "—"
            pages = sorted({ct["page"] for ct in cell.get("citations", [])})
            row.append(f"{v} (p.{', '.join(map(str, pages))})" if pages else v)
        rows.append(row)
    return header, rows


def to_csv(header: list[str], rows: list[list[str]]) -> str:
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def to_markdown(header: list[str], rows: list[list[str]]) -> str:
    def esc(x: str) -> str:
        return x.replace("|", "\\|").replace("\n", " ")

    lines = ["| " + " | ".join(map(esc, header)) + " |", "|" + "---|" * len(header)]
    lines += ["| " + " | ".join(map(esc, r)) + " |" for r in rows]
    return "\n".join(lines) + "\n"


def to_xlsx(header: list[str], rows: list[list[str]]) -> bytes:
    """Minimal standards-compliant .xlsx (inline strings, bold header, wrapped cells) with the stdlib only."""
    import zipfile
    from xml.sax.saxutils import escape

    def col(i: int) -> str:
        out = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            out = chr(65 + r) + out
        return out

    def row_xml(r: int, cells: list[str], style: int) -> str:
        cs = "".join(
            f'<c r="{col(i)}{r}" t="inlineStr" s="{style}"><is><t xml:space="preserve">{escape(v)}</t></is></c>'
            for i, v in enumerate(cells)
        )
        return f'<row r="{r}">{cs}</row>'

    data = row_xml(1, header, 1) + "".join(row_xml(i + 2, r, 2) for i, r in enumerate(rows))
    cols = f'<cols><col min="1" max="{len(header)}" width="40" customWidth="1"/></cols>'
    sheet = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        f"{cols}<sheetData>{data}</sheetData></worksheet>"
    )
    styles = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="2"><font><sz val="11"/><name val="Calibri"/></font>'
        '<font><b/><sz val="11"/><name val="Calibri"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill>'
        '<fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellStyleXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellStyleXfs>'
        '<cellXfs count="3"><xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0"/>'
        '<xf numFmtId="0" fontId="1" fillId="0" borderId="0" xfId="0" applyFont="1" applyAlignment="1">'
        '<alignment wrapText="1" vertical="top"/></xf>'
        '<xf numFmtId="0" fontId="0" fillId="0" borderId="0" xfId="0" applyAlignment="1">'
        '<alignment wrapText="1" vertical="top"/></xf></cellXfs></styleSheet>'
    )
    files = {
        "[Content_Types].xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
            '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
            '<Default Extension="xml" ContentType="application/xml"/>'
            '<Override PartName="/xl/workbook.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
            '<Override PartName="/xl/worksheets/sheet1.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
            '<Override PartName="/xl/styles.xml" '
            'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/></Types>'
        ),
        "_rels/.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>'
        ),
        "xl/workbook.xml": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
            'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
            '<sheets><sheet name="Comparison" sheetId="1" r:id="rId1"/></sheets></workbook>'
        ),
        "xl/_rels/workbook.xml.rels": (
            '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/worksheet" Target="worksheets/sheet1.xml"/>'
            '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/'
            'relationships/styles" Target="styles.xml"/></Relationships>'
        ),
        "xl/worksheets/sheet1.xml": sheet,
        "xl/styles.xml": styles,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, body in files.items():
            z.writestr(name, body)
    return buf.getvalue()
