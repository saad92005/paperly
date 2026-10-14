"use client";

import { useQueryClient } from "@tanstack/react-query";

import { AppShell, PageTitle, useRequireUser } from "@/components/app-shell";
import { SearchTab } from "@/components/import-dialog";

export default function DiscoverPage() {
  useRequireUser();
  const qc = useQueryClient();
  return (
    <AppShell>
      <PageTitle title="Discover" sub="Search arXiv and Semantic Scholar. Only open-access papers can be added." />
      <div className="max-w-3xl">
        <SearchTab onAdded={() => void qc.invalidateQueries({ queryKey: ["papers"] })} />
      </div>
    </AppShell>
  );
}
