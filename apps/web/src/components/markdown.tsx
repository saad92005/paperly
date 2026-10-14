"use client";

import "katex/dist/katex.min.css";

import { Children, isValidElement, useEffect, useId, useState, type ReactNode } from "react";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import type { Citation } from "@/lib/types";
import { cn } from "@/lib/utils";

const PALETTE = ["#4338CA", "#0F766E", "#B45309", "#BE185D", "#1D4ED8", "#6D28D9"];
export function paperHue(paperId: string, order: string[]): string {
  const i = order.indexOf(paperId);
  return PALETTE[(i < 0 ? 0 : i) % PALETTE.length];
}

export function CitationChip({
  c,
  onClick,
  color,
}: {
  c: Citation | undefined;
  n: number;
  onClick?: (c: Citation) => void;
  color?: string;
}) {
  if (!c) return null;
  const label = `Source ${c.n}: ${c.paper_title ?? "paper"}, page ${c.page}`;
  return (
    <button
      type="button"
      onClick={() => onClick?.(c)}
      title={`${c.section ? c.section + " · " : ""}p.${c.page}\n“${c.quote.slice(0, 220)}”`}
      aria-label={label}
      style={color ? { backgroundColor: color, color: "white" } : undefined}
      className="mx-0.5 inline-flex h-[1.15rem] min-w-[1.15rem] -translate-y-0.5 items-center justify-center rounded-full bg-brand px-1 align-middle text-[10px] font-semibold text-white hover:opacity-80 focus-visible:ring-2 focus-visible:ring-ring"
    >
      {c.n}
    </button>
  );
}

/** Splits plain text on [n] markers and renders citation chips inline. */
function withChips(children: ReactNode, cites: Map<number, Citation>, onCite?: (c: Citation) => void, hue?: (c: Citation) => string): ReactNode {
  return Children.map(children, (child) => {
    if (typeof child === "string") {
      const parts = child.split(/(\[\d+\])/g);
      return parts.map((p, i) => {
        const m = /^\[(\d+)\]$/.exec(p);
        if (m && cites.has(Number(m[1]))) {
          const c = cites.get(Number(m[1]));
          return <CitationChip key={i} c={c} n={Number(m[1])} onClick={onCite} color={c && hue ? hue(c) : undefined} />;
        }
        return p;
      });
    }
    if (isValidElement<{ children?: ReactNode }>(child) && child.props.children) {
      return child;
    }
    return child;
  });
}

let mermaidLoaded: Promise<typeof import("mermaid")["default"]> | null = null;

function Mermaid({ code }: { code: string }) {
  const id = useId().replace(/:/g, "");
  const [svg, setSvg] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    let alive = true;
    mermaidLoaded ??= import("mermaid").then((m) => {
      m.default.initialize({ startOnLoad: false, securityLevel: "strict", theme: "neutral" });
      return m.default;
    });
    mermaidLoaded
      .then((m) => m.render(`m${id}`, code))
      .then((r) => alive && setSvg(r.svg))
      .catch(() => alive && setFailed(true));
    return () => {
      alive = false;
    };
  }, [code, id]);
  if (failed) return <pre className="overflow-auto rounded-lg bg-muted p-3 text-xs">{code}</pre>;
  if (!svg) return <div className="h-24 animate-pulse rounded-lg bg-muted" />;
  // Mermaid output is produced in strict security mode from our own model output.
  return <div className="my-3 overflow-auto rounded-lg border border-line bg-surface p-3" dangerouslySetInnerHTML={{ __html: svg }} />;
}

export function Markdown({
  text,
  citations = [],
  onCite,
  hue,
  className,
  streaming,
}: {
  text: string;
  citations?: Citation[];
  onCite?: (c: Citation) => void;
  hue?: (c: Citation) => string;
  className?: string;
  streaming?: boolean;
}) {
  const cites = new Map(citations.map((c) => [c.n, c]));
  const wrap = (children: ReactNode) => withChips(children, cites, onCite, hue);
  return (
    <div dir="auto" className={cn("prose-paperly", className)}>
      <ReactMarkdown
        remarkPlugins={[remarkGfm, remarkMath]}
        rehypePlugins={[[rehypeKatex, { trust: false, strict: "ignore" }]]}
        skipHtml
        components={{
          p: ({ children }) => <p>{wrap(children)}</p>,
          li: ({ children }) => <li>{wrap(children)}</li>,
          td: ({ children }) => <td>{wrap(children)}</td>,
          strong: ({ children }) => <strong>{wrap(children)}</strong>,
          em: ({ children }) => <em>{wrap(children)}</em>,
          a: ({ href, children }) => (
            <a href={href} target="_blank" rel="noopener noreferrer nofollow" className="text-brand underline">
              {children}
            </a>
          ),
          code: ({ className: cls, children }) => {
            const lang = /language-(\w+)/.exec(cls ?? "")?.[1];
            if (lang === "mermaid" && !streaming) return <Mermaid code={String(children).trim()} />;
            return <code className={cls}>{children}</code>;
          },
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
