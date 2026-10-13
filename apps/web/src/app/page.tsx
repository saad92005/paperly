import { Quote } from "lucide-react";
import Link from "next/link";

import { AppHeader } from "@/components/app-header";
import { buttonVariants } from "@/components/ui/button";
import { site } from "@/lib/site";

export default function Home() {
  return (
    <>
      <AppHeader />
      <main className="mx-auto flex w-full max-w-2xl flex-1 flex-col items-start justify-center gap-6 px-6 py-16">
        <Quote className="size-8 text-brand" aria-hidden />
        <h1 className="text-4xl font-semibold tracking-tight">
          Read any paper like an expert.
        </h1>
        <p className="font-serif text-lg leading-relaxed text-muted-foreground">
          {site.name} answers questions about your research papers, and every answer points to the exact
          sentence it came from. Free, open source, and private by default.
        </p>
        <Link href="/library" className={buttonVariants({ size: "lg", className: "h-11 px-5" })}>
          Open your library
        </Link>
      </main>
    </>
  );
}
