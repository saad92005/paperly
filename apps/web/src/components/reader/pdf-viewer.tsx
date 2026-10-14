"use client";

import type { PDFDocumentProxy, PDFPageProxy } from "pdfjs-dist";
import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";

import { cn } from "@/lib/utils";

export type Highlight = {
  id: string;
  page: number;
  rect: [number, number, number, number]; // PDF points, top-left origin
  kind: "cite" | "yellow" | "green" | "blue" | "pink" | "purple";
  pulse?: boolean;
  title?: string;
};

export type SelectionInfo = {
  text: string;
  page: number;
  rects: [number, number, number, number][];
  clientX: number;
  clientY: number;
};

export type PdfViewerHandle = {
  scrollTo: (page: number, rect?: [number, number, number, number]) => void;
  find: (q: string) => Promise<number[]>;
};

type Props = {
  data: ArrayBuffer;
  zoom: number;
  highlights: Highlight[];
  onSelection: (s: SelectionInfo | null) => void;
  onPage: (page: number, pages: number) => void;
  onLoaded?: (pages: number) => void;
};

const HL_CLASS: Record<Highlight["kind"], string> = {
  cite: "bg-cite-hl ring-1 ring-brand/40",
  yellow: "bg-hl-yellow",
  green: "bg-hl-green",
  blue: "bg-hl-blue",
  pink: "bg-hl-pink",
  purple: "bg-brand-soft",
};

let pdfjsPromise: Promise<typeof import("pdfjs-dist")> | null = null;
function loadPdfjs() {
  pdfjsPromise ??= import("pdfjs-dist").then((m) => {
    m.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();
    return m;
  });
  return pdfjsPromise;
}

export const PdfViewer = forwardRef<PdfViewerHandle, Props>(function PdfViewer(
  { data, zoom, highlights, onSelection, onPage, onLoaded },
  ref,
) {
  const [doc, setDoc] = useState<PDFDocumentProxy | null>(null);
  const [sizes, setSizes] = useState<{ w: number; h: number }[]>([]);
  const [error, setError] = useState<string | null>(null);
  const scroller = useRef<HTMLDivElement>(null);
  const pageEls = useRef<(HTMLDivElement | null)[]>([]);
  const textCache = useRef<Map<number, string>>(new Map());

  useEffect(() => {
    let alive = true;
    let task: { destroy: () => Promise<void> } | null = null;
    (async () => {
      try {
        const pdfjs = await loadPdfjs();
        // pdf.js transfers the buffer to its worker: give it a copy.
        const t = pdfjs.getDocument({ data: new Uint8Array(data.slice(0)) });
        task = t;
        const loaded = await t.promise;
        const s: { w: number; h: number }[] = [];
        for (let i = 1; i <= loaded.numPages; i++) {
          const vp = (await loaded.getPage(i)).getViewport({ scale: 1 });
          s.push({ w: vp.width, h: vp.height });
        }
        if (!alive) return;
        setSizes(s);
        setDoc(loaded);
        onLoaded?.(loaded.numPages);
      } catch (e) {
        if (alive) setError(e instanceof Error ? e.message : "Could not open the PDF.");
      }
    })();
    return () => {
      alive = false;
      void task?.destroy();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload only when the bytes change
  }, [data]);

  // Track the most visible page.
  useEffect(() => {
    const root = scroller.current;
    if (!root || !doc) return;
    const onScroll = () => {
      const mid = root.scrollTop + root.clientHeight / 3;
      let page = 1;
      pageEls.current.forEach((el, i) => {
        if (el && el.offsetTop <= mid) page = i + 1;
      });
      onPage(page, doc.numPages);
    };
    onScroll();
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, [doc, onPage]);

  useImperativeHandle(
    ref,
    () => ({
      scrollTo(page, rect) {
        const el = pageEls.current[page - 1];
        const root = scroller.current;
        if (!el || !root) return;
        const y = el.offsetTop + (rect ? rect[1] * zoom - root.clientHeight / 3 : -12);
        const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
        root.scrollTo({ top: Math.max(0, y), behavior: reduce ? "auto" : "smooth" });
      },
      async find(q) {
        if (!doc || !q.trim()) return [];
        const needle = q.toLowerCase();
        const hits: number[] = [];
        for (let i = 1; i <= doc.numPages; i++) {
          let t = textCache.current.get(i);
          if (t === undefined) {
            const content = await (await doc.getPage(i)).getTextContent();
            t = content.items.map((it) => ("str" in it ? it.str : "")).join(" ").toLowerCase();
            textCache.current.set(i, t);
          }
          if (t.includes(needle)) hits.push(i);
        }
        return hits;
      },
    }),
    [doc, zoom],
  );

  const onMouseUp = useCallback(() => {
    const sel = window.getSelection();
    if (!sel || sel.isCollapsed || !sel.rangeCount) {
      onSelection(null);
      return;
    }
    const text = sel.toString().replace(/\s+/g, " ").trim();
    const range = sel.getRangeAt(0);
    const pageEl = (range.startContainer.parentElement ?? null)?.closest<HTMLElement>("[data-page]");
    if (!text || !pageEl) return onSelection(null);
    const page = Number(pageEl.dataset.page);
    const box = pageEl.getBoundingClientRect();
    const rects = Array.from(range.getClientRects())
      .filter((r) => r.width > 1 && r.height > 1)
      .map(
        (r) =>
          [
            (r.left - box.left) / zoom,
            (r.top - box.top) / zoom,
            (r.right - box.left) / zoom,
            (r.bottom - box.top) / zoom,
          ] as [number, number, number, number],
      )
      .slice(0, 40);
    const last = range.getBoundingClientRect();
    onSelection({ text: text.slice(0, 4000), page, rects, clientX: last.left + last.width / 2, clientY: last.top });
  }, [onSelection, zoom]);

  if (error) return <div className="p-6 text-sm text-danger">Couldn&apos;t open the PDF: {error}</div>;

  return (
    <div ref={scroller} className="h-full overflow-auto bg-muted/40 px-2 py-4" onMouseUp={onMouseUp} onTouchEnd={onMouseUp}>
      {!doc && <div className="mx-auto h-[80vh] max-w-3xl animate-pulse rounded bg-surface" />}
      {doc &&
        sizes.map((s, i) => (
          <PageView
            key={i}
            doc={doc}
            pageNo={i + 1}
            width={s.w}
            height={s.h}
            zoom={zoom}
            highlights={highlights.filter((h) => h.page === i + 1)}
            setRef={(el) => (pageEls.current[i] = el)}
          />
        ))}
    </div>
  );
});

function PageView({
  doc,
  pageNo,
  width,
  height,
  zoom,
  highlights,
  setRef,
}: {
  doc: PDFDocumentProxy;
  pageNo: number;
  width: number;
  height: number;
  zoom: number;
  highlights: Highlight[];
  setRef: (el: HTMLDivElement | null) => void;
}) {
  const wrap = useRef<HTMLDivElement | null>(null);
  const canvas = useRef<HTMLCanvasElement>(null);
  const textLayer = useRef<HTMLDivElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const io = new IntersectionObserver(([e]) => e.isIntersecting && setVisible(true), { rootMargin: "800px 0px" });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (!visible) return;
    let cancelled = false;
    let task: ReturnType<PDFPageProxy["render"]> | null = null;
    (async () => {
      const pdfjs = await loadPdfjs();
      const page = await doc.getPage(pageNo);
      if (cancelled || !canvas.current || !textLayer.current) return;
      const vp = page.getViewport({ scale: zoom });
      const ratio = Math.min(window.devicePixelRatio || 1, 2);
      const c = canvas.current;
      c.width = Math.floor(vp.width * ratio);
      c.height = Math.floor(vp.height * ratio);
      task = page.render({
        canvas: c,
        canvasContext: c.getContext("2d")!,
        viewport: vp,
        transform: ratio !== 1 ? [ratio, 0, 0, ratio, 0, 0] : undefined,
      });
      await task.promise.catch(() => undefined);
      if (cancelled) return;
      const tl = textLayer.current;
      tl.replaceChildren();
      tl.style.setProperty("--total-scale-factor", String(zoom));
      const layer = new pdfjs.TextLayer({ textContentSource: page.streamTextContent(), container: tl, viewport: vp });
      await layer.render().catch(() => undefined);
    })();
    return () => {
      cancelled = true;
      task?.cancel();
    };
  }, [visible, doc, pageNo, zoom]);

  return (
    <div
      ref={(el) => {
        wrap.current = el;
        setRef(el);
      }}
      data-page={pageNo}
      className="relative mx-auto mb-4 bg-white shadow-sm"
      style={{ width: width * zoom, height: height * zoom }}
      aria-label={`Page ${pageNo}`}
    >
      <canvas ref={canvas} className="absolute inset-0 h-full w-full" />
      <div ref={textLayer} className="textLayer" />
      <div className="pointer-events-none absolute inset-0 z-[3]">
        {highlights.map((h) => (
          <div
            key={h.id}
            title={h.title}
            data-kind={h.kind}
            className={cn("absolute rounded-[2px] mix-blend-multiply dark:mix-blend-normal", HL_CLASS[h.kind], h.pulse && "cite-pulse")}
            style={{
              left: h.rect[0] * zoom - 1,
              top: h.rect[1] * zoom - 1,
              width: (h.rect[2] - h.rect[0]) * zoom + 2,
              height: (h.rect[3] - h.rect[1]) * zoom + 2,
            }}
          />
        ))}
      </div>
      <span className="absolute bottom-1 right-2 text-[10px] text-neutral-400">{pageNo}</span>
    </div>
  );
}
