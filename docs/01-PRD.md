# 01 · Product Requirements Document (PRD)

**Product:** Paperly — the free, open-source AI copilot for reading research papers
**Version:** 1.0 (MVP) → 1.5 → 2.0
**Owner:** Muhammad Saad · **Status:** Ready to build · **Date:** October 2026

---

## 1. Vision

> *Read any paper like an expert — and trust every answer, because every answer points to the exact line it came from.*

Paperly turns a pile of PDFs into a workspace you can question, compare and study. It is free, open source and can run fully offline, so a student in Lahore gets the same tool as a researcher at a top lab.

## 2. Problem

- Research papers are dense, long and written for specialists. Students and engineers spend hours to extract a method, a number or a limitation.
- Generic "chat with PDF" tools answer fluently but **cite loosely** (a page at best), so users cannot verify claims and stop trusting them.
- Comparing several papers (methods, datasets, results) is manual spreadsheet work.
- The strongest research assistants are paid or rate-limited; many users — especially in developing countries — cannot pay in USD.
- Users who care about privacy (unpublished drafts, company reports) have no good local option.

## 3. Target users (personas)

| Persona | Who | Job to be done | What wins them |
|---|---|---|---|
| **Ayesha — CS undergrad** | Writing her FYP literature review | "Understand 30 papers fast and write a related-work section I can defend." | ELI5/student explain modes, Urdu explanations, flashcards, lit-review drafter |
| **Bilal — ML engineer** | Evaluating methods for a product | "Which approach fits my constraints? What are the numbers?" | Comparison matrix with cited cells, fast exact answers, figure/table Q&A |
| **Dr. Sara — researcher/supervisor** | Tracks a sub-field | "Stay current, check claims, organise reading for my students." | Citation graph, claim check, shared collections, topic alerts |
| **Privacy-first user** | Works with unpublished or internal PDFs | "Use AI without uploading my files to a third party." | Self-host / local mode with Ollama, no telemetry |

## 4. Goals and non-goals

**Goals (v1)**
1. Grounded Q&A over one or many papers with sentence-level, click-to-highlight citations.
2. Fast, accurate structured summaries of any paper.
3. Multi-paper chat and a comparison view.
4. A reader experience good enough that users read *in* Paperly.
5. Run at $0 for development and the first few hundred users.
6. Measurable quality: a public eval report in the README.

**Non-goals (v1)**
- OCR for scanned PDFs (detected and flagged; OCR arrives in self-host mode later).
- Writing papers for users or detecting AI-written text.
- Reference-manager replacement (we import from and export to Zotero/BibTeX instead).
- Native mobile apps (the web app is responsive; PWA later).
- Paid plans (architecture leaves room; billing is out of scope).

## 5. Feature set

Priority: **P0** = MVP must-have · **P1** = v1.5 differentiators · **P2** = v2 moat.
Items marked ★ are additions beyond the original "PaperPilot" concept.

### 5.1 Library and import
| ID | Feature | Pri |
|---|---|---|
| F-01 | Sign in with Google or email magic link | P0 |
| F-02 | Upload PDF (drag-and-drop, multi-file, ≤ 25 MB, ≤ 100 pages on free tier) | P0 |
| F-03 | ★ Import by arXiv ID/URL or DOI (open-access PDF resolved automatically) | P0 |
| F-04 | ★ Auto-metadata: title, authors, year, venue, abstract, DOI, arXiv ID | P0 |
| F-05 | Collections (folders), tags, star, search across the library | P0 |
| F-06 | ★ Live ingestion progress (queued → parsing → indexing → ready) | P0 |
| F-07 | ★ Shared public-paper cache: an arXiv paper indexed once serves every user instantly | P1 |
| F-08 | ★ Import from Zotero and BibTeX | P2 |
| F-09 | ★ Browser extension "Send to Paperly" from arXiv / publisher pages | P2 |

### 5.2 Reading
| ID | Feature | Pri |
|---|---|---|
| F-10 | Built-in PDF reader (zoom, outline, thumbnails, search in paper) | P0 |
| F-11 | Split view: reader ⟷ AI panel (Chat · Summary · Notes · Glossary · References) | P0 |
| F-12 | Highlights and notes anchored to text; colours; export to Markdown | P0 |
| F-13 | ★ Select text → Explain / Simplify / Translate / Ask about this | P0 |
| F-14 | ★ Equation explainer: select a formula → each symbol explained (KaTeX) | P1 |
| F-15 | ★ Glossary: auto-extracted key terms; hover a term in the reader to see its paper-specific definition | P1 |
| F-16 | ★ Reading path: "read these sections first" plus reading-progress tracking | P2 |

### 5.3 AI answers
| ID | Feature | Pri |
|---|---|---|
| F-20 | Grounded chat about one paper, streamed | P0 |
| F-21 | ★ Sentence-level citations `[1]` → click scrolls PDF to the highlighted sentence | P0 |
| F-22 | ★ "Not found in these papers" abstention + grounding badge on each answer | P0 |
| F-23 | Multi-paper chat (scope: this paper / selected papers / a whole collection) | P0 |
| F-24 | Structured summary: TL;DR, problem, method, data, results, limitations, contributions | P0 |
| F-25 | ★ Explain level: ELI5 · Student · Expert | P0 |
| F-26 | ★ Answer in any language (Urdu, Arabic, Hindi, Spanish…) while citing the English source | P1 |
| F-27 | ★ Visual explanations: auto Mermaid diagram of an architecture or pipeline | P1 |
| F-28 | ★ Figure and table Q&A (vision model); table → CSV export | P2 |
| F-29 | ★ Claim check: paste a claim → supporting and contradicting passages across a collection | P2 |
| F-30 | Thumbs up/down with reason on every answer (feeds eval set) | P0 |

### 5.4 Compare and synthesise
| ID | Feature | Pri |
|---|---|---|
| F-40 | Compare 2–10 papers in a matrix: task, method, data, metrics, key results, limitations, code | P1 |
| F-41 | ★ Custom columns: user types a question ("Batch size?"), every cell answered and cited | P1 |
| F-42 | ★ Export matrix to CSV/XLSX/Markdown | P1 |
| F-43 | ★ Literature-review drafter: themed related-work section with citations; export .md/.docx/.tex + .bib | P1 |
| F-44 | ★ Research agent: give a question → it searches arXiv/Semantic Scholar, imports top open-access papers, reads them and writes a cited mini-review (bounded steps and budget) | P2 |

### 5.5 Discover and connect
| ID | Feature | Pri |
|---|---|---|
| F-50 | ★ Search arXiv + Semantic Scholar inside Paperly; one-click import | P1 |
| F-51 | ★ References list parsed and linked; "cited by" list; mini citation graph | P1 |
| F-52 | Citation export: BibTeX, APA, IEEE | P0 |
| F-53 | ★ Topic/author alerts: weekly digest of new arXiv papers by email | P2 |
| F-54 | ★ MCP server: use your Paperly library from Claude Desktop / Claude Code | P2 |

### 5.6 Study
| ID | Feature | Pri |
|---|---|---|
| F-60 | ★ Flashcards and quiz generated from a paper, each card cited; Anki CSV export | P1 |
| F-61 | ★ Simple spaced repetition (due cards per day) | P2 |
| F-62 | ★ Audio overview of the summary (browser text-to-speech; $0) | P2 |

### 5.7 Platform
| ID | Feature | Pri |
|---|---|---|
| F-70 | Usage meter and fair-use quotas per user (protects free tiers) | P0 |
| F-71 | Settings: language, explain level, theme, data and privacy, delete account | P0 |
| F-72 | ★ Self-host / local mode: docker-compose with Ollama + GROBID, zero data leaves the machine | P1 |
| F-73 | Public read-only share link for a summary or comparison (never the PDF) | P1 |
| F-74 | Admin page: users, ingestion failures, provider errors, eval trend | P1 |
| F-75 | ★ Team workspaces with shared collections and comments | P2 |

## 6. Key user stories with acceptance criteria (P0)

**US-1 Import by arXiv ID.** *As a student, I paste `1706.03762` and the paper appears in my library ready to chat.*
- Given a valid arXiv ID or URL, metadata is fetched from the arXiv API and the PDF ingested; status moves through queued → parsing → indexing → ready with visible progress.
- If the same arXiv paper is already in the shared cache, it is ready in under 3 s.
- Invalid IDs show an inline error; no job is created.

**US-2 Cited answer.** *As a reader, I ask "What problem does this paper solve?" and get a streamed answer with numbered citations.*
- Every factual sentence has ≥ 1 citation; citations are numbered in order of appearance.
- Clicking `[n]` scrolls the reader to the page and highlights the supporting sentence(s) within 300 ms.
- A sources list under the answer shows paper title, section heading and page for each citation.
- If retrieval finds no supporting passage, the answer says the information was not found and suggests a rephrase; no fabricated content.

**US-3 Structured summary.** *As a reader, I open the Summary tab and see a structured summary within 20 s on first open and instantly afterwards.*
- Sections: TL;DR (≤ 3 sentences), Problem, Method, Data, Results (with numbers), Limitations, Contributions — each bullet cited.
- Cached per paper + language + level; regenerate button available.

**US-4 Multi-paper chat.** *As an engineer, I select three papers and ask "Which uses the least compute?"*
- Retrieval draws from all selected papers with diversity (no single paper dominates unless only it is relevant).
- Citations show which paper each claim came from (colour/initials per paper).

**US-5 Notes.** *As a student, I highlight a sentence, add a note, and export all notes for the paper as Markdown with page references.*

**US-6 Quotas.** *As the operator, I need free-tier limits respected.*
- Default per-user daily caps (configurable): 50 questions, 10 imports, 5 comparisons. Reaching a cap shows a friendly message and the reset time.
- Provider rate limits trigger automatic fallback to the next provider before the user sees an error.

## 7. Success metrics

| Type | Metric | Target (3 months after launch) |
|---|---|---|
| Quality | Faithfulness on golden set | ≥ 0.90 |
| Quality | Citation precision (cited passage supports the sentence) | ≥ 0.90 |
| Quality | Abstention accuracy on unanswerable questions | ≥ 0.85 |
| Speed | Time to first token, p95 (warm) | ≤ 2.5 s |
| Speed | Ingestion of a 15-page paper, p95 | ≤ 60 s |
| Engagement | Thumbs-up share of rated answers | ≥ 80% |
| Engagement | Weekly active users who return next week | ≥ 35% |
| Growth | GitHub stars | 500+ |
| Cost | Monthly infrastructure spend | $0 |

## 8. Competitive landscape (qualitative)

| Product | Strength | Gap Paperly targets |
|---|---|---|
| Elicit | Systematic-review style extraction tables | Heavy use is paid; not open source; no offline mode |
| SciSpace | Paper copilot, explanations | Freemium limits; citations not sentence-precise |
| Consensus | Search answers across literature | Search-first, not a reading workspace |
| NotebookLM (Google) | Free, multi-source, audio overviews | General-purpose; no paper-specific tools (comparison matrix, references, BibTeX); cloud only |
| ChatPDF and similar | Simple and fast | Generic; weak multi-paper and research workflow |
| Semantic Scholar | Huge index, TLDRs, Semantic Reader | Not a private library chat assistant |
| Zotero | Reference management standard | No built-in grounded AI |

**Positioning:** *The open-source, free, privacy-respecting research reader whose citations you can actually verify.* Differentiators: sentence-level highlighted citations, cited comparison matrix, local mode, MCP server, multilingual explanations, published eval numbers.

## 9. Assumptions and constraints

- Budget is $0; free tiers can change, so all providers are swappable (see TRD §5).
- Built mainly by one developer with Claude Code; scope is phased (see Roadmap).
- Only user-uploaded files and open-access sources are processed; Paperly never redistributes PDFs publicly.
- English-language papers first; questions and answers in any language from v1.5.

## 10. Release plan (summary)

| Release | Contents | Target |
|---|---|---|
| **MVP 1.0** | F-01…06, F-10…13, F-20…25, F-30, F-52, F-70, F-71 | ~8 weeks |
| **1.5** | F-07, F-14, F-15, F-26, F-27, F-40…43, F-50, F-51, F-60, F-72…74 | +5 weeks |
| **2.0** | F-08, F-09, F-16, F-28, F-29, F-44, F-53, F-54, F-61, F-62, F-75 | +6–8 weeks |

Detailed phases and definitions of done: `docs/10-ROADMAP-AND-PHASES.md`.
