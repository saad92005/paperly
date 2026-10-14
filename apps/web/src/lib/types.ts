// Response shapes from the FastAPI service (docs/04 §3). Kept small and hand-written for the UI;
// the full generated OpenAPI types live in @paperly/api-types.

export type PaperStatus = "queued" | "fetching" | "parsing" | "indexing" | "ready" | "failed";
export type Level = "eli5" | "student" | "expert";

export type PaperCard = {
  id: string;
  title: string | null;
  authors: { name: string }[];
  year: number | null;
  venue: string | null;
  source: "upload" | "arxiv" | "doi" | "url";
  source_ref: string | null;
  status: PaperStatus;
  error: string | null;
  page_count: number | null;
  starred: boolean;
  read_progress: number;
  collection_id: string | null;
  tags: string[];
  added_at: string;
  arxiv_id: string | null;
  doi: string | null;
};

export type Section = {
  id: string;
  idx: number;
  heading: string;
  level: number;
  page_start: number | null;
  page_end: number | null;
};

export type Paper = PaperCard & {
  abstract: string | null;
  visibility: "private" | "public_cache";
  parser: string | null;
  sections: Section[];
};

export type Rect = { page: number; rect: [number, number, number, number] };

export type Citation = {
  n: number;
  paper_id: string;
  paper_title?: string | null;
  chunk_id: string;
  page: number;
  section: string | null;
  sentence_idx: number[];
  quote: string;
  rects: Rect[];
};

export type Message = {
  id: string;
  role: "user" | "assistant";
  content: string;
  citations: Citation[];
  grounded: boolean | null;
  support_score: number | null;
  provider: string | null;
  model: string | null;
  latency_ms: number | null;
  created_at: string;
  not_found?: boolean;
  closest?: { paper_id: string; chunk_id: string; page: number; section: string | null; quote: string }[];
  diagram?: string | null;
};

export type Thread = {
  id: string;
  title: string | null;
  scope: { paper_ids?: string[]; collection_id?: string };
  created_at: string;
  updated_at: string;
};

export type ThreadDetail = Thread & { messages: Message[] };

export type Note = {
  id: string;
  paper_id: string;
  anchor: { page: number; rects: number[][]; text: string } | null;
  body_md: string;
  color: "yellow" | "green" | "blue" | "pink" | "purple";
  origin: "manual" | "ai";
  created_at: string;
  updated_at: string;
};

export type Collection = {
  id: string;
  name: string;
  description: string | null;
  paper_count: number;
  created_at: string;
};

export type CitedText = { text: string; citations: Citation[] };
export type Summary = {
  tldr: CitedText[];
  problem: CitedText[];
  method: CitedText[];
  data: CitedText[];
  results: CitedText[];
  limitations: CitedText[];
  contributions: CitedText[];
  keywords: string[];
  extractive?: boolean;
  model?: string;
};

export type GlossaryTerm = { term: string; definition: string; page: number | null; citations: Citation[] };

export type Chunk = {
  id: string;
  paper_id: string;
  idx: number;
  kind: string;
  text: string;
  context_header: string;
  page_start: number;
  page_end: number;
  section: string | null;
  sentences: { s: number; e: number; page: number; rects: number[][] }[];
  token_count: number;
};

export type Reference = {
  idx: number;
  raw: string;
  title: string | null;
  year: number | null;
  doi: string | null;
  arxiv_id: string | null;
  in_library: boolean;
};

export type Job = {
  id: string;
  type: string;
  status: "queued" | "running" | "succeeded" | "failed" | "cancelled";
  stage: string | null;
  progress: number;
  error: string | null;
};

export type Cell = {
  value: string | null;
  citations: Citation[];
  status: "ok" | "not_found" | "unverified" | "unsupported" | "partial" | "extractive";
  confidence: string | null;
  verified?: string | null;
};

export type Comparison = {
  id: string;
  title: string | null;
  paper_ids: string[];
  columns: { key: string; label: string; question: string }[];
  cells: Record<string, Record<string, Cell>>;
  status: string;
  share_id: string | null;
  created_at: string;
  papers: { id: string; title: string | null; year: number | null; authors: string[] }[];
};

export type DiscoverResult = {
  title: string | null;
  authors: string[];
  year: number | null;
  venue: string | null;
  abstract: string;
  arxiv_id: string | null;
  doi: string | null;
  oa_pdf: string | null;
  citation_count: number | null;
  importable: boolean;
  in_library: boolean;
  source: "arxiv" | "s2";
};

export type Flashcard = {
  id: string;
  paper_id: string;
  front: string;
  back: string;
  citation: Citation | null;
  ease: number;
  interval_d: number;
  reps: number;
  due_at: string;
  paper_title: string | null;
};

export type Usage = {
  used: { questions: number; imports: number; compares: number; tokens: number };
  limits: { questions: number; imports: number; compares: number };
  reset_at: string;
};

export type ReviewItem = {
  id: string;
  job_id: string;
  collection_id: string | null;
  topic: string | null;
  style: string;
  created_at: string;
  preview: string;
};
