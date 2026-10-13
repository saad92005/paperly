# 05 · UI / UX Specification

## 1. Design principles

1. **The paper is the hero.** The PDF gets the most space; AI lives in a side panel that never covers the text.
2. **Every claim is one click from its proof.** Citations are visible, numbered and clickable everywhere (chat, summaries, matrix cells, flashcards).
3. **Calm and academic, not flashy.** Paper-white surfaces, ink text, one confident accent, generous line height. Motion only to explain state changes.
4. **Fast feels trustworthy.** Stream everything, skeletons instead of spinners, optimistic UI for notes and tags.
5. **Keyboard first, touch friendly.** Every action has a shortcut and a 44 px touch target.

## 2. Design tokens

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#FAF9F6` | `#0F1115` | App background ("paper") |
| `--surface` | `#FFFFFF` | `#171A21` | Panels, cards |
| `--ink` | `#16181D` | `#E8E6E1` | Primary text |
| `--muted` | `#5B6170` | `#9BA1AE` | Secondary text |
| `--line` | `#E6E3DC` | `#262A33` | Borders, dividers |
| `--accent` | `#4338CA` | `#8B93FF` | Primary actions, citation chips, focus ring |
| `--accent-soft` | `#EEF0FF` | `#23264A` | Selected rows, chip backgrounds |
| `--cite-hl` | `rgba(67,56,202,.22)` | `rgba(139,147,255,.28)` | Cited-sentence highlight in PDF |
| `--hl-yellow / green / blue / pink` | `#FFE58A` `#B7F0C0` `#BBD7FF` `#FFC4DD` (45% alpha) | same, 35% | User highlights |
| `--ok / --warn / --danger` | `#15803D` `#B45309` `#B91C1C` | `#4ADE80` `#FBBF24` `#F87171` | Status |

**Type:** Inter for UI (14/20 base, 13 for dense tables); Source Serif 4 (or Lora) for summaries and long answers (16/26); JetBrains Mono for code and IDs. Headings: Inter Semibold, tight tracking.
**Shape:** radius 10 px (cards), 8 px (inputs), 999 px (chips). Shadow only on floating layers. **Spacing:** 4-pt grid. **Icons:** Lucide (MIT).

## 3. Information architecture

```
Library ─┬─ All papers / Collections / Starred / Recently read
         ├─ Import (Upload · arXiv/DOI · Search)
         └─ Paper ── Reader + AI panel [Chat | Summary | Notes | Glossary | References]
Compare ── Matrix (rows = papers, columns = questions)
Discover ── Search arXiv + Semantic Scholar
Study ── Due flashcards · Quizzes
Settings ── Profile · Language & level · Appearance · Data & privacy · Usage
```

## 4. Key screens

**4.1 Library.** Left sidebar (collections, starred, recent, "+ New collection"). Main: search bar with filters (status, year, tag), grid/list toggle, paper cards (title, authors · year · venue, status pill, progress bar while indexing, star, read-progress ring). Primary button "Add papers" opens the Import dialog. Empty state: three large import tiles + "Try with a classic: *Attention Is All You Need*" one-click demo.

**4.2 Import dialog.** Tabs: *Upload* (drop zone, multiple files, size/page limits shown), *arXiv / DOI* (paste ID or URL, live validation, preview of title before import), *Search* (inline Discover). After import: items appear immediately in the library with a stepper: Fetching → Parsing → Indexing → Ready.

**4.3 Reader (core screen).**
```
┌─────────────────────────────────────────────────────────────────────────────┐
│ ◀ Library   Attention Is All You Need · Vaswani et al. 2017   ★  ⋯  ⌘K      │
├────────┬─────────────────────────────────────┬──────────────────────────────┤
│Outline │                                     │ Chat Summary Notes Glossary  │
│1 Intro │          PDF page (pdf.js)          │──────────────────────────────│
│2 Back  │   ░░ cited sentence highlighted ░░  │ Q: Explain the architecture  │
│3 Model │                                     │ A: The model replaces        │
│ 3.1    │     user highlight ▓▓▓ (yellow)     │ recurrence with self-attn    │
│ 3.2    │                                     │ [1][2] …                     │
│thumbs  │                                     │ ▸ Sources (2)   +1  -1  copy │
│        │      page 3 / 15    −  100%  +      │ [Ask about this paper…    ↵] │
└────────┴─────────────────────────────────────┴──────────────────────────────┘
```
- Panel width resizable (min 360 px), collapsible (`]`).
- Selecting text in the PDF shows a floating toolbar: Highlight · Note · Explain · Simplify · Translate · Ask.
- Clicking a citation chip: smooth-scroll to page, flash the highlight (600 ms pulse), keep it visible until the next action. `J/K` cycles citations of the current answer.
- Answer footer: Sources list (paper initials badge, section, page), grounding badge (`Grounded` / `Partly grounded` / `Not found`), provider name (small, muted), actions: copy, save to notes, regenerate, thumbs up/down.
- Scope switcher above the input: *This paper* · *Selected papers* · *Collection*.
- Level and language selectors in the input bar (ELI5 · Student · Expert; language dropdown).

**4.4 Summary tab.** Cards for TL;DR, Problem, Method, Data, Results, Limitations, Contributions; each bullet ends with citation chips. Buttons: Regenerate · Copy as Markdown · Share link · Listen (browser TTS).

**4.5 Compare.** Spreadsheet-like matrix, sticky first column (paper), columns = questions. Cells stream in; each cell shows the value + citation chips; hover expands the quote; click opens the paper at that sentence in a side sheet. "+ Add column" with a question input and suggestions (Dataset size, Compute, Code available?, Best metric). Export menu (CSV, XLSX, Markdown). Share link.

**4.6 Discover.** Search input, filters (year, open access only), result cards with abstract preview and "Add to library" (disabled with tooltip when no open-access PDF).

**4.7 Study.** Due cards count; flip card UI (front/back + citation chip); grades Again/Hard/Good/Easy (SM-2). Quiz mode: 5 MCQs with explanations and citations.

**4.8 Settings.** Profile; Language and default explain level; Appearance (system/light/dark, reader font size); Data & privacy (which AI providers process data, download my data, delete account); Usage meter (questions/imports/comparisons today vs limits, reset time).

## 5. States (required for every screen)

| State | Pattern |
|---|---|
| Empty | Illustration-free, helpful: one sentence + primary action + example |
| Loading | Skeletons matching final layout; streamed text appears progressively |
| Waking server | Top banner: "Starting Paperly's free server… this can take ~30 s the first time." + spinner, auto-retry |
| Error | Plain-language message + Retry + "copy error ID" (request_id) |
| Quota reached | Friendly card with reset time and what still works (reading, notes) |
| Provider busy | "AI is busy — switched to a backup model" toast (non-blocking) |
| Offline | Reader still works for cached pages; actions queue with a badge |
| Failed ingestion | Card shows reason (scanned PDF, too large, unreadable) + suggested fix |

## 6. Interaction details

- **Shortcuts:** `⌘/Ctrl K` command palette · `/` focus ask box · `J/K` next/previous citation · `H` highlight selection · `N` note · `]` toggle panel · `G S` go to summary · `?` shortcut sheet.
- **Streaming:** render Markdown incrementally; KaTeX for `$…$`; Mermaid blocks render when complete.
- **Citation chip:** superscript-sized pill `1` in accent; tooltip with paper initials, section and page; screen-reader label "Source 1: Attention Is All You Need, page 3".
- **Multi-paper colour:** each paper in scope gets a stable hue (6-colour palette) used in chips and source list.
- **Microcopy examples:** "Not found in these papers. Try asking about the method section, or widen the scope to your collection." · "Indexed 15 pages · 62 passages · ready to chat."

## 7. Accessibility and responsiveness

- WCAG 2.2 AA contrast for all tokens (verify with axe in Playwright).
- Focus ring 2 px `--accent`; logical tab order; `aria-live="polite"` for streamed answers.
- Respect `prefers-reduced-motion` (no pulse; instant scroll).
- Breakpoints: ≥ 1200 three-column reader; 768–1199 reader + panel overlay sheet; < 768 tabs: *Paper* / *Ask* / *Notes*, citation tap switches to *Paper* tab and highlights.
- RTL rendering for answers in Urdu/Arabic (`dir="auto"` on message bubbles).
