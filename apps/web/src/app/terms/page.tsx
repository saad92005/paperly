import Link from "next/link";

export const metadata = { title: "Terms" };

export default function Terms() {
  return (
    <main className="prose-paperly mx-auto max-w-2xl px-4 py-12">
      <Link href="/" className="text-sm text-brand">← Paperly</Link>
      <h1 className="text-2xl">Terms of use</h1>
      <ul>
        <li>Paperly is provided free and “as is”, without warranty. AI answers can be wrong: always check the cited source.</li>
        <li>Only upload papers you have the right to use. We do not redistribute PDFs; share links never include the PDF.</li>
        <li>Fair use limits apply (daily questions, imports and comparisons) so the free service stays available to everyone.</li>
        <li>Do not abuse the service (automated scraping, attempts to bypass quotas or access other users’ data).</li>
        <li>The source code is MIT licensed.</li>
      </ul>
    </main>
  );
}
