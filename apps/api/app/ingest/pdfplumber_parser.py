"""Default cloud PDF parser (docs/06 §1.1.3) on pdfplumber (MIT).

Pipeline per page: words → drop invisible/rotated text → detect a column gutter → lines in
reading order. Then: drop running headers/footers and page numbers, find headings, captions
and references, and split text into pysbd sentences that keep their word boxes.
Coordinates are PDF points with a top-left origin: (x0, top, x1, bottom).
"""

import io
import re
import statistics
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Literal

import pdfplumber
import pysbd

from app.errors import AppError
from app.providers.base import Block, ParsedDocument, ParsedSection, Rect, Sentence


class ScannedPdf(AppError):
    code, status = "scanned_pdf", 422
    message = "This PDF looks scanned (no text layer). OCR is not supported yet."


class UnreadablePdf(AppError):
    code, status = "unsupported_file", 422
    message = "This file could not be read as a PDF."


KNOWN_HEADINGS = {
    "abstract", "introduction", "related work", "related works", "background", "method",
    "methods", "methodology", "approach", "model", "models", "experiments", "experiment",
    "experimental setup", "experimental results", "evaluation", "results", "discussion",
    "conclusion", "conclusions", "conclusion and future work", "conclusions and future work",
    "limitations", "acknowledgments", "acknowledgements", "acknowledgment", "acknowledgement",
    "references", "bibliography", "appendix", "appendices", "preliminaries", "analysis",
    "future work", "ethics statement", "broader impact", "data", "dataset", "datasets",
}  # fmt: skip
NUMBERED = re.compile(r"^((?:\d+|[A-Z])(?:\.\d+)*)\.?\s+([A-Z][^.]{1,90})$")
CAPTION = re.compile(r"^(Figure|Fig\.|Table|Algorithm)\s*\d+[.:]?", re.IGNORECASE)
REF_HEADINGS = {"references", "bibliography"}
REF_START_NUM = re.compile(r"^\[\d{1,3}\]|^\d{1,3}\.\s")
ABSTRACT_INLINE = re.compile(r"^abstract\s*[—–\-:.]\s*", re.IGNORECASE)
DOI_RE = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+[^\s\"<>.,;])")
ARXIV_RE = re.compile(r"arXiv:(\d{4}\.\d{4,5})(v\d+)?", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19[89]\d|20[0-4]\d)\b")

_segmenter = pysbd.Segmenter(language="en", clean=False, char_span=False)


@dataclass
class Word:
    text: str
    page: int
    x0: float
    top: float
    x1: float
    bottom: float
    rects: list[tuple[int, Rect]] = field(default_factory=lambda: [])


@dataclass
class Line:
    words: list[Word]
    page: int
    x0: float
    top: float
    x1: float
    bottom: float
    size: float
    bold: bool
    column: int  # 0 full width / single column, 1 left, 2 right
    raw: list[dict[str, Any]] = field(default_factory=lambda: [])

    @property
    def text(self) -> str:
        return " ".join(w.text for w in self.words)


def _is_white(color: Any) -> bool:
    if not isinstance(color, (tuple, list)) or not color:
        return False
    vals = [float(c) for c in color if isinstance(c, (int, float))]  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if not vals:
        return False
    if len(vals) == 4:  # CMYK white is all zeros
        return all(v <= 0.02 for v in vals)
    return all(v >= 0.98 for v in vals)


def _visible_words(page: Any, page_no: int) -> tuple[list[dict[str, Any]], int]:
    words: list[dict[str, Any]] = page.extract_words(
        extra_attrs=["fontname", "size", "non_stroking_color", "upright"],
        keep_blank_chars=False,
        x_tolerance=1.5,
    )
    w_, h_ = float(page.width), float(page.height)
    kept: list[dict[str, Any]] = []
    dropped = 0
    for w in words:
        invisible = (
            float(w["size"]) < 2.0
            or _is_white(w.get("non_stroking_color"))
            or not w.get("upright", True)
            or w["x1"] < 0
            or w["x0"] > w_
            or w["bottom"] < 0
            or w["top"] > h_
        )
        if invisible:
            dropped += 1
        else:
            w["page"] = page_no
            kept.append(w)
    return kept, dropped


def _find_gutter(words: list[dict[str, Any]], width: float) -> float | None:
    """x of a vertical gap in the middle of the page that most lines don't cross."""
    if len(words) < 40:
        return None
    bins = 200
    cover = [0] * bins
    for w in words:
        a, b = int(max(0, w["x0"]) / width * bins), int(min(width, w["x1"]) / width * bins)
        for i in range(a, min(b + 1, bins)):
            cover[i] += 1
    limit = max(2, len(words) // 60)
    best: tuple[int, int] | None = None
    i = int(bins * 0.3)
    while i < int(bins * 0.7):
        if cover[i] <= limit:
            j = i
            while j < int(bins * 0.7) and cover[j] <= limit:
                j += 1
            if best is None or (j - i) > (best[1] - best[0]):
                best = (i, j)
            i = j
        i += 1
    if best is None or (best[1] - best[0]) < 2:  # ≥ 1% of the width
        return None
    # Both sides must hold real text, otherwise it's just a centred figure.
    mid = (best[0] + best[1]) / 2 / bins * width
    left = sum(1 for w in words if w["x1"] <= mid)
    right = sum(1 for w in words if w["x0"] >= mid)
    if min(left, right) < len(words) * 0.2:
        return None
    return mid


def _group_lines(words: list[dict[str, Any]], column: int) -> list[Line]:
    words = sorted(words, key=lambda w: (round(w["top"]), w["x0"]))
    rows: list[list[dict[str, Any]]] = []
    for w in words:
        if rows and abs(rows[-1][0]["top"] - w["top"]) <= 2.5:
            rows[-1].append(w)
        else:
            rows.append([w])
    lines: list[Line] = []
    for row in rows:
        row.sort(key=lambda w: w["x0"])
        sizes = [float(w["size"]) for w in row]
        bold = sum(len(w["text"]) for w in row if _bold(w["fontname"])) > 0.6 * sum(
            len(w["text"]) for w in row
        )
        ws = [
            Word(
                w["text"], w["page"], w["x0"], w["top"], w["x1"], w["bottom"],
                [(w["page"], (w["x0"], w["top"], w["x1"], w["bottom"]))],
            )
            for w in row
        ]  # fmt: skip
        lines.append(
            Line(
                ws, row[0]["page"], min(w["x0"] for w in row), min(w["top"] for w in row),
                max(w["x1"] for w in row), max(w["bottom"] for w in row),
                statistics.median(sizes), bold, column, row,
            )
        )  # fmt: skip
    return lines


def _bold(fontname: str) -> bool:
    f = fontname.lower()
    return any(k in f for k in ("bold", "black", "heavy", "semibold", "demi", "-medi", ".b", "-b", "cmbx"))


def _page_lines(words: list[dict[str, Any]], width: float) -> list[Line]:
    """Reading order: full-width rows act as separators; between them, left col then right."""
    gutter = _find_gutter(words, width)
    if gutter is None:
        return _group_lines(words, 0)
    rows = _group_lines(words, 0)
    out: list[Line] = []
    left: list[dict[str, Any]] = []
    right: list[dict[str, Any]] = []

    def flush() -> None:
        out.extend(_group_lines(left, 1))
        out.extend(_group_lines(right, 2))
        left.clear()
        right.clear()

    for row in rows:
        crosses = any(w.x0 < gutter < w.x1 for w in row.words) or (
            row.x0 < gutter - width * 0.1 and row.x1 > gutter + width * 0.1
            and _max_gap_across(row, gutter) < width * 0.02
        )  # fmt: skip
        if crosses:
            flush()
            out.append(row)
            continue
        for d in row.raw:
            (left if d["x1"] <= gutter else right).append(d)
    flush()
    return out


def _max_gap_across(row: Line, gutter: float) -> float:
    for a, b in zip(row.words, row.words[1:], strict=False):
        if a.x1 <= gutter <= b.x0:
            return b.x0 - a.x1
    return 0.0


def _norm_margin(text: str) -> str:
    return re.sub(r"\d+", "#", text.strip().lower())


def _drop_running(lines: list[Line], heights: dict[int, float], pages: int) -> tuple[list[Line], int]:
    def in_margin(ln: Line) -> bool:
        h = heights[ln.page]
        return ln.top < h * 0.08 or ln.bottom > h * 0.92

    counts: Counter[str] = Counter()
    seen: dict[str, set[int]] = {}
    for ln in lines:
        if in_margin(ln):
            seen.setdefault(_norm_margin(ln.text), set()).add(ln.page)
    counts.update({k: len(v) for k, v in seen.items()})
    kept: list[Line] = []
    dropped = 0
    for ln in lines:
        if in_margin(ln):
            key = _norm_margin(ln.text)
            if re.fullmatch(r"[#\s\-–—|/of]*", key) or (pages >= 2 and counts[key] >= max(2, pages * 0.5)):
                dropped += 1
                continue
        kept.append(ln)
    return kept, dropped


def _heading_level(text: str, ln: Line, body_size: float) -> int | None:
    t = text.strip()
    if len(t) > 100 or len(t) < 3:
        return None
    emphasised = ln.size >= body_size * 1.15 or ln.bold
    bare = re.sub(r"^((\d+|[A-Z])(\.\d+)*)\.?\s+", "", t).strip().rstrip(".:").lower()
    if bare in KNOWN_HEADINGS and (emphasised or t.isupper() or bare in ("abstract", "references")):
        m = re.match(r"^(\d+(?:\.\d+)*)", t)
        return m.group(1).count(".") + 1 if m else 1
    m = NUMBERED.match(t)
    if m and emphasised and not t.endswith((",", ";")) and len(t.split()) <= 12:
        return m.group(1).count(".") + 1
    return None


@dataclass
class _Stream:
    kind: Literal["abstract", "body", "caption", "reference"]
    section_idx: int
    words: list[Word] = field(default_factory=lambda: [])


def _merge_hyphen(words: list[Word], nxt: Word) -> bool:
    if words and words[-1].text.endswith("-") and len(words[-1].text) > 2 and nxt.text[:1].islower():
        last = words[-1]
        last.text = last.text[:-1] + nxt.text
        last.rects.extend(nxt.rects)
        return True
    return False


def _sentences(words: list[Word]) -> list[Sentence]:
    if not words:
        return []
    text_parts: list[str] = []
    spans: list[tuple[int, int, Word]] = []
    pos = 0
    for w in words:
        if text_parts:
            text_parts.append(" ")
            pos += 1
        text_parts.append(w.text)
        spans.append((pos, pos + len(w.text), w))
        pos += len(w.text)
    text = "".join(text_parts)
    out: list[Sentence] = []
    cursor = 0
    wi = 0
    for seg in _segmenter.segment(text):  # pyright: ignore[reportUnknownVariableType]
        seg_s = str(seg).strip()  # pyright: ignore[reportUnknownArgumentType]
        if not seg_s:
            continue
        start = text.find(seg_s, cursor)
        if start < 0:
            continue
        end = start + len(seg_s)
        cursor = end
        sw: list[Word] = []
        while wi < len(spans) and spans[wi][0] < end:
            if spans[wi][1] > start:
                sw.append(spans[wi][2])
            wi += 1
        if not sw:
            continue
        out.append(Sentence(seg_s, sw[0].page, _line_rects(sw)))
    return out


def _line_rects(words: list[Word]) -> list[tuple[int, Rect]]:
    """Union word boxes per visual line → a few rects per sentence."""
    rects: list[tuple[int, Rect]] = []
    for w in words:
        for page, (x0, t, x1, b) in w.rects:
            if rects:
                p, (a0, at, a1, ab) = rects[-1]
                if p == page and abs(at - t) < 3 and x0 >= a0 - 1 and x0 - a1 < 30:
                    rects[-1] = (p, (min(a0, x0), min(at, t), max(a1, x1), max(ab, b)))
                    continue
            rects.append((page, (round(x0, 1), round(t, 1), round(x1, 1), round(b, 1))))
    return [(p, (round(r[0], 1), round(r[1], 1), round(r[2], 1), round(r[3], 1))) for p, r in rects]


def _split_references(lines: list[Line]) -> list[list[Line]]:
    numbered = sum(1 for ln in lines if REF_START_NUM.match(ln.text)) >= max(2, len(lines) * 0.1)
    entries: list[list[Line]] = []
    left_edge: dict[tuple[int, int], float] = {}
    for ln in lines:
        k = (ln.page, ln.column)
        left_edge[k] = min(left_edge.get(k, ln.x0), ln.x0)
    for ln in lines:
        start = (
            bool(REF_START_NUM.match(ln.text)) if numbered else ln.x0 <= left_edge[(ln.page, ln.column)] + 2
        )
        if start or not entries:
            entries.append([ln])
        else:
            entries[-1].append(ln)
    return entries


def parse_pdf_bytes(pdf: bytes, *, max_pages: int = 500) -> ParsedDocument:
    try:
        doc = pdfplumber.open(io.BytesIO(pdf))
    except Exception as exc:
        raise UnreadablePdf() from exc
    with doc:
        pages = doc.pages[:max_pages]
        page_sizes = [(float(p.width), float(p.height)) for p in pages]
        heights = {i + 1: h for i, (_, h) in enumerate(page_sizes)}
        all_lines: list[Line] = []
        dropped = 0
        sparse_pages = 0
        first_page_text = ""
        for i, page in enumerate(pages, start=1):
            words, d = _visible_words(page, i)
            dropped += d
            if sum(len(w["text"]) for w in words) < 20:
                sparse_pages += 1
            lines = _page_lines(words, float(page.width))
            if i == 1:
                first_page_text = " ".join(ln.text for ln in lines)
            all_lines.extend(lines)
    page_count = len(page_sizes)
    if page_count == 0 or sparse_pages > page_count * 0.5:
        raise ScannedPdf()

    lines, d = _drop_running(all_lines, heights, page_count)
    dropped += d
    weights = Counter[float]()
    for ln in lines:
        weights[round(ln.size, 1)] += len(ln.text)
    body_size = weights.most_common(1)[0][0] if weights else 10.0

    # Title: the largest text in the top half of page 1 (consecutive lines of that size).
    title: str | None = None
    p1 = [ln for ln in lines if ln.page == 1 and ln.top < heights[1] * 0.5]
    if p1:
        big = max(ln.size for ln in p1)
        if big >= body_size * 1.2:
            parts = [ln.text for ln in p1 if abs(ln.size - big) < 0.5]
            title = " ".join(parts[:4]).strip() or None

    sections: list[ParsedSection] = [ParsedSection("Front matter", 1, 1, 1)]
    streams: list[_Stream] = [_Stream("body", 0)]
    ref_lines: list[Line] = []
    in_refs = False
    for ln in lines:
        text = ln.text
        if title and ln.page == 1 and text in title and ln.size >= body_size * 1.2:
            continue
        m_abs = ABSTRACT_INLINE.match(text)
        level = _heading_level(text, ln, body_size)
        if level is None and m_abs and ln.page <= 2:
            level = 1
        if level is not None:
            heading = "Abstract" if m_abs else text.strip()
            bare = re.sub(r"^((\d+|[A-Z])(\.\d+)*)\.?\s+", "", heading).strip().lower()
            sections[-1].page_end = max(sections[-1].page_end, ln.page)
            sections.append(ParsedSection(heading, level, ln.page, ln.page))
            sidx = len(sections) - 1
            if bare in REF_HEADINGS:
                in_refs = True
                continue
            if bare.startswith("appendi") or bare in ("acknowledgments", "acknowledgements"):
                in_refs = False
            elif in_refs and level == 1:
                in_refs = False
            kind: Literal["abstract", "body"] = "abstract" if bare == "abstract" else "body"
            streams.append(_Stream(kind, sidx))
            if m_abs:
                rest = list(ln.words)
                # Drop the "Abstract—" token(s) and keep the remainder as abstract text.
                while rest and re.match(r"^abstract\W*$", rest[0].text, re.IGNORECASE):
                    rest = rest[1:]
                if rest and rest[0].text.lower().startswith("abstract"):
                    rest[0].text = ABSTRACT_INLINE.sub("", rest[0].text)
                streams[-1].words.extend(w for w in rest if w.text)
            continue
        sections[-1].page_end = max(sections[-1].page_end, ln.page)
        if in_refs:
            ref_lines.append(ln)
            continue
        cur = streams[-1]
        if CAPTION.match(text):
            streams.append(_Stream("caption", cur.section_idx))
            cur = streams[-1]
        elif cur.kind == "caption" and cur.words:
            last = cur.words[-1]
            # A caption ends at a vertical gap, a column change or a new page.
            if ln.page != last.page or ln.top - last.bottom > (ln.bottom - ln.top) * 0.9:
                base = next(s for s in reversed(streams) if s.kind != "caption")
                streams.append(_Stream(base.kind, base.section_idx))
                cur = streams[-1]
        for w in ln.words:
            if not _merge_hyphen(cur.words, w):
                cur.words.append(w)

    blocks: list[Block] = []
    for s in streams:
        sents = _sentences(s.words)
        if sents:
            blocks.append(Block(s.kind, s.section_idx, sents))
    references: list[str] = []
    ref_sidx = next(
        (i for i, s in enumerate(sections) if s.heading.lower().strip(" .0123456789") in REF_HEADINGS),
        len(sections) - 1,
    )
    for entry in _split_references(ref_lines):
        rwords: list[Word] = []
        for ln in entry:
            for w in ln.words:
                if not _merge_hyphen(rwords, w):
                    rwords.append(w)
        raw = " ".join(w.text for w in rwords).strip()
        if len(raw) < 15:
            continue
        references.append(raw)
        blocks.append(Block("reference", ref_sidx, [Sentence(raw, rwords[0].page, _line_rects(rwords))]))

    abstract = " ".join(s.text for b in blocks if b.kind == "abstract" for s in b.sentences).strip() or None
    doi_m = DOI_RE.search(first_page_text)
    arxiv_m = ARXIV_RE.search(first_page_text)
    years = [int(y) for y in YEAR_RE.findall(first_page_text)]
    return ParsedDocument(
        page_count=page_count,
        title=title,
        abstract=abstract,
        year=max(years) if years else None,
        doi=doi_m.group(1) if doi_m else None,
        arxiv_id=arxiv_m.group(1) if arxiv_m else None,
        sections=sections,
        blocks=blocks,
        references=references,
        page_sizes=page_sizes,
        dropped_lines=dropped,
    )


class PdfPlumberParser:
    name = "pdfplumber"

    def __init__(self, max_pages: int = 500) -> None:
        self.max_pages = max_pages

    async def parse(self, pdf: bytes) -> ParsedDocument:
        import anyio

        return await anyio.to_thread.run_sync(lambda: parse_pdf_bytes(pdf, max_pages=self.max_pages))
