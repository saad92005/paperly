import { BookOpen, Columns3, Code2, FileSearch, Languages, Quote, ShieldCheck, Sparkles } from "lucide-react";
import Link from "next/link";

import { ThemeToggle } from "@/components/theme-toggle";
import { buttonVariants } from "@/components/ui/button";
import { site } from "@/lib/site";
import { cn } from "@/lib/utils";

const FEATURES = [
  { icon: Quote, title: "Every claim, one click from its proof", body: "Answers cite the exact sentence. Click a citation and the PDF scrolls there and highlights it." },
  { icon: ShieldCheck, title: "Says “not found” instead of guessing", body: "An abstain gate and a support check flag anything the paper doesn’t back up — numbers included." },
  { icon: Columns3, title: "Compare papers side by side", body: "A cited matrix of task, method, data, metrics, results, compute and limitations. Export CSV, XLSX or Markdown." },
  { icon: Sparkles, title: "Summaries, glossary, flashcards", body: "Structured cited summaries at ELI5, student or expert level, plus spaced-repetition cards." },
  { icon: Languages, title: "Explain, simplify, translate", body: "Select any passage or equation in the PDF and get an explanation in your language." },
  { icon: FileSearch, title: "Discover and draft", body: "Search arXiv and Semantic Scholar, import open-access papers, and draft a cited literature review." },
];

export default function Home() {
  return (
    <div className="min-h-dvh">
      <header className="flex h-14 items-center justify-between border-b border-line bg-surface px-4">
        <span className="flex items-center gap-2 font-semibold tracking-tight">
          <BookOpen className="size-5 text-brand" aria-hidden /> {site.name}
        </span>
        <div className="flex items-center gap-2">
          <ThemeToggle />
          <Link href="/login" className={cn(buttonVariants({ variant: "ghost" }), "h-10")}>Sign in</Link>
        </div>
      </header>
      <main>
        <section className="mx-auto max-w-4xl px-4 pb-12 pt-16 text-center sm:pt-24">
          <p className="mb-4 inline-flex rounded-full bg-brand-soft px-3 py-1 text-xs font-medium text-brand">Open source · free · no credit card</p>
          <h1 className="text-balance text-4xl font-semibold tracking-tight sm:text-5xl">
            Read research papers with an AI that <span className="text-brand">shows its sources</span>.
          </h1>
          <p className="mx-auto mt-5 max-w-2xl text-pretty text-lg text-muted-foreground">
            {site.name} answers questions about your papers with sentence-level citations, highlights the exact evidence in the PDF,
            and tells you when the paper doesn&apos;t say.
          </p>
          <div className="mt-8 flex flex-wrap justify-center gap-3">
            <Link href="/login" className={cn(buttonVariants(), "h-12 px-6 text-base")}>Start reading — free</Link>
            <a href="https://github.com" target="_blank" rel="noopener noreferrer" className={cn(buttonVariants({ variant: "outline" }), "h-12 px-6 text-base")}>
              <Code2 aria-hidden /> Source code
            </a>
          </div>
        </section>

        <section aria-label="Example answer" className="mx-auto max-w-3xl px-4">
          <div className="rounded-2xl border border-line bg-surface p-5 shadow-sm">
            <p className="mb-3 ml-auto w-fit rounded-2xl rounded-br-sm bg-brand-soft px-3 py-2 text-sm">What BLEU score does the big Transformer reach on English→German?</p>
            <p className="font-serif text-[15px] leading-relaxed">
              The big Transformer reaches <strong>28.4 BLEU</strong> on WMT 2014 English-to-German, more than 2.0 BLEU above the best
              previous models including ensembles
              <span className="mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] -translate-y-0.5 items-center justify-center rounded-full bg-brand px-1 align-middle text-[10px] font-semibold text-white">1</span>.
            </p>
            <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
              <span className="rounded-full bg-ok/10 px-2 py-0.5 font-medium text-ok">Grounded</span>
              <span>[1] 6.1 Machine Translation · p.8</span>
            </div>
          </div>
        </section>

        <section className="mx-auto grid max-w-5xl gap-4 px-4 py-16 sm:grid-cols-2 lg:grid-cols-3">
          {FEATURES.map(({ icon: Icon, title, body }) => (
            <div key={title} className="rounded-xl border border-line bg-surface p-5">
              <Icon className="size-5 text-brand" aria-hidden />
              <h2 className="mt-3 font-semibold">{title}</h2>
              <p className="mt-1 text-sm text-muted-foreground">{body}</p>
            </div>
          ))}
        </section>
      </main>
      <footer className="border-t border-line px-4 py-6 text-center text-xs text-muted-foreground">
        MIT licensed · <Link href="/privacy" className="underline">Privacy</Link> · <Link href="/terms" className="underline">Terms</Link>
      </footer>
    </div>
  );
}
