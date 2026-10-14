"""Structure-aware chunking (docs/06 §1.2).

Never crosses a section; abstract, captions and references are their own chunks; body text is
packed from whole sentences to ~380 tokens (max 512) with a 1-sentence overlap.
"""

from dataclasses import dataclass
from typing import Any

from app.providers.base import Block, ParsedDocument, Sentence

TARGET_TOKENS = 380
MAX_TOKENS = 512
CHUNKER_VERSION = "c1"


def count_tokens(text: str) -> int:
    """Fast approximation of cl100k token counts (≈ 1.33 tokens per word)."""
    return max(1, round(len(text.split()) * 1.33))


@dataclass
class ChunkDraft:
    idx: int
    kind: str
    section_idx: int
    text: str
    context_header: str
    page_start: int
    page_end: int
    sentences: list[dict[str, Any]]
    token_count: int

    @property
    def embed_text(self) -> str:
        return f"{self.context_header}\n\n{self.text}"


def section_path(doc: ParsedDocument, idx: int) -> str:
    """'3 Model › 3.2 Attention' using heading levels."""
    if not doc.sections:
        return ""
    path = [doc.sections[idx]]
    level = doc.sections[idx].level
    for s in reversed(doc.sections[:idx]):
        if s.level < level:
            path.insert(0, s)
            level = s.level
        if level <= 1:
            break
    return " › ".join(s.heading for s in path)


def _pack(sentences: list[Sentence]) -> list[list[Sentence]]:
    groups: list[list[Sentence]] = []
    cur: list[Sentence] = []
    tokens = 0
    for s in sentences:
        t = count_tokens(s.text)
        if cur and (tokens + t > MAX_TOKENS or tokens >= TARGET_TOKENS):
            groups.append(cur)
            overlap = cur[-1:] if len(cur) > 1 else []
            cur, tokens = list(overlap), sum(count_tokens(x.text) for x in overlap)
        cur.append(s)
        tokens += t
    if cur:
        groups.append(cur)
    return groups


def _draft(idx: int, kind: str, sidx: int, sents: list[Sentence], header: str) -> ChunkDraft:
    parts: list[str] = []
    meta: list[dict[str, Any]] = []
    pos = 0
    for s in sents:
        if parts:
            parts.append(" ")
            pos += 1
        meta.append(
            {
                "s": pos,
                "e": pos + len(s.text),
                "page": s.page,
                "rects": [[p, *r] for p, r in s.rects],
            }
        )
        parts.append(s.text)
        pos += len(s.text)
    text = "".join(parts)
    pages = [p for s in sents for p, _ in s.rects] or [s.page for s in sents]
    return ChunkDraft(idx, kind, sidx, text, header, min(pages), max(pages), meta, count_tokens(text))


def chunk_document(doc: ParsedDocument, title: str | None) -> list[ChunkDraft]:
    title = title or doc.title or "Untitled paper"
    out: list[ChunkDraft] = []
    pending_refs: list[Block] = []

    def header(sidx: int) -> str:
        path = section_path(doc, sidx)
        return f"{title} — {path}" if path else title

    def flush_refs() -> None:
        if not pending_refs:
            return
        sents = [s for b in pending_refs for s in b.sentences]
        for group in _pack(sents):
            out.append(_draft(len(out), "reference", pending_refs[0].section_idx, group,
                              header(pending_refs[0].section_idx)))  # fmt: skip
        pending_refs.clear()

    for block in doc.blocks:
        if block.kind == "reference":
            pending_refs.append(block)
            continue
        flush_refs()
        if block.kind == "caption":
            # Captions stay whole (they are short); split only if absurdly long.
            groups = (
                [block.sentences]
                if sum(count_tokens(s.text) for s in block.sentences) <= MAX_TOKENS
                else _pack(block.sentences)
            )
        else:
            groups = _pack(block.sentences)
        for group in groups:
            out.append(_draft(len(out), block.kind, block.section_idx, group, header(block.section_idx)))
    flush_refs()
    return out
