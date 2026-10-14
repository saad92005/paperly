from pathlib import Path

import pytest

from app.ingest.chunker import MAX_TOKENS, chunk_document, count_tokens
from app.ingest.fetch import FetchBlocked, check_url
from app.ingest.pdfplumber_parser import ScannedPdf, UnreadablePdf, parse_pdf_bytes
from app.ingest.sources import normalize_arxiv, normalize_doi
from app.services.papers import bibtex
from tests.fixtures.make_pdfs import HIDDEN, make_all


@pytest.fixture(scope="module")
def pdfs(tmp_path_factory: pytest.TempPathFactory) -> dict[str, Path]:
    return make_all(tmp_path_factory.mktemp("pdfs"))


def all_text(pdf: Path) -> str:
    doc = parse_pdf_bytes(pdf.read_bytes())
    return " ".join(s.text for b in doc.blocks for s in b.sentences)


def test_two_column_structure(pdfs: dict[str, Path]) -> None:
    doc = parse_pdf_bytes(pdfs["two_column"].read_bytes())
    assert doc.title == "Sparrow: Grounded Answers for Paper Reading"
    headings = [s.heading for s in doc.sections]
    assert headings[1:] == [
        "Abstract", "1 Introduction", "2 Method", "2.1 Retrieval", "3 Results", "4 Conclusion", "References",
    ]  # fmt: skip
    assert [s.level for s in doc.sections if s.heading == "2.1 Retrieval"] == [2]
    assert doc.abstract and doc.abstract.startswith("We introduce Sparrow")
    assert doc.doi == "10.1234/sparrow.2024.001"
    assert doc.arxiv_id == "2401.01234"
    assert len(doc.references) == 3
    assert doc.references[1].startswith("[2] C. Lee.")


def test_reading_order_is_column_by_column(pdfs: dict[str, Path]) -> None:
    text = all_text(pdfs["two_column"])
    # Introduction (left column) must come entirely before Results (right column/page 2).
    assert text.index("Reading research papers is slow") < text.index("Sparrow splits each paper")
    assert text.index("Sparrow splits each paper") < text.index("On PaperQA, Sparrow scores")


def test_hidden_text_headers_and_page_numbers_removed(pdfs: dict[str, Path]) -> None:
    text = all_text(pdfs["two_column"])
    assert HIDDEN not in text and "IGNORE ALL" not in text
    assert "Preprint under review" not in text


def test_references_excluded_from_body_chunks(pdfs: dict[str, Path]) -> None:
    doc = parse_pdf_bytes(pdfs["two_column"].read_bytes())
    chunks = chunk_document(doc, doc.title)
    body = " ".join(c.text for c in chunks if c.kind != "reference")
    assert "Citation-aware generation" not in body
    assert any(c.kind == "reference" and "Citation-aware" in c.text for c in chunks)
    assert any(c.kind == "caption" and c.text.startswith("Figure 1") for c in chunks)


def test_sentences_have_boxes_on_the_right_page(pdfs: dict[str, Path]) -> None:
    doc = parse_pdf_bytes(pdfs["two_column"].read_bytes())
    for block in doc.blocks:
        for s in block.sentences:
            assert s.rects, s.text
            for page, (x0, top, x1, bottom) in s.rects:
                w, h = doc.page_sizes[page - 1]
                assert 0 <= x0 < x1 <= w and 0 <= top < bottom <= h


def test_hanging_indent_references(pdfs: dict[str, Path]) -> None:
    doc = parse_pdf_bytes(pdfs["single_column"].read_bytes())
    assert doc.references == [
        "Brown, T. (2020). Language models are few-shot learners. In NeurIPS.",
        "Vaswani, A. (2017). Attention is all you need. In NeurIPS, pages 5998-6008.",
    ]


def test_scanned_and_garbage_rejected(pdfs: dict[str, Path]) -> None:
    with pytest.raises(ScannedPdf):
        parse_pdf_bytes(pdfs["scanned"].read_bytes())
    with pytest.raises(UnreadablePdf):
        parse_pdf_bytes(b"%PDF-1.4 not really")


def test_chunker_respects_sections_size_and_offsets(pdfs: dict[str, Path]) -> None:
    doc = parse_pdf_bytes(pdfs["two_column"].read_bytes())
    chunks = chunk_document(doc, doc.title)
    assert [c.idx for c in chunks] == list(range(len(chunks)))
    for c in chunks:
        assert c.token_count <= MAX_TOKENS + 40
        assert c.context_header.startswith("Sparrow: Grounded Answers for Paper Reading — ")
        for s in c.sentences:
            assert 0 <= s["s"] < s["e"] <= len(c.text)
            assert s["rects"] and len(s["rects"][0]) == 5
    sub = next(c for c in chunks if "reciprocal rank fusion" in c.text)
    assert sub.context_header.endswith("2 Method › 2.1 Retrieval")
    # Long sections are split with a one-sentence overlap.
    method = [c for c in chunks if c.section_idx == 3 and c.kind == "body"]
    assert len(method) >= 2
    last_sentence = method[0].text[method[0].sentences[-1]["s"] :]
    assert method[1].text.startswith(last_sentence)


def test_token_count_approximation() -> None:
    assert count_tokens("one two three") == 4


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("1706.03762", "1706.03762"),
        ("https://arxiv.org/abs/1706.03762v7", "1706.03762"),
        ("arXiv:2401.01234", "2401.01234"),
        ("https://arxiv.org/pdf/2401.01234v2.pdf", "2401.01234"),
        ("hep-th/9901001", "hep-th/9901001"),
        ("not an id", None),
    ],
)
def test_normalize_arxiv(value: str, expected: str | None) -> None:
    assert normalize_arxiv(value) == expected


def test_normalize_doi() -> None:
    assert normalize_doi("https://doi.org/10.1145/3292500.3330701") == "10.1145/3292500.3330701"
    assert normalize_doi("doi: 10.1000/xyz123.") == "10.1000/xyz123"
    assert normalize_doi("hello") is None


@pytest.mark.parametrize(
    "url",
    ["file:///etc/passwd", "http://127.0.0.1/x.pdf", "http://localhost/x.pdf", "http://10.0.0.5/a",
     "http://169.254.169.254/latest/meta-data", "https://example.com:8443/a.pdf", "ftp://example.com/a"],
)  # fmt: skip
async def test_ssrf_guard_blocks_private_targets(url: str) -> None:
    with pytest.raises(FetchBlocked):
        await check_url(url)


def test_bibtex_formats() -> None:
    card = {
        "title": "Attention Is All You Need",
        "authors": [{"name": "Ashish Vaswani"}, {"name": "Noam Shazeer"}],
        "year": 2017, "venue": "NeurIPS", "doi": None, "arxiv_id": "1706.03762",
    }  # fmt: skip
    bib = bibtex(card, "bibtex")
    assert bib.startswith("@article{vaswani2017attention,")
    assert "author = {Ashish Vaswani and Noam Shazeer}" in bib
    assert bib.count("{") == bib.count("}")
    assert bibtex(card, "apa").startswith("Vaswani, A., & Shazeer, N. (2017). Attention Is All You Need.")
    assert bibtex(card, "ieee").startswith('A. Vaswani, and N. Shazeer, "Attention Is All You Need,"')
