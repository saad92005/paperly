import Link from "next/link";

export const metadata = { title: "Privacy" };

export default function Privacy() {
  return (
    <main className="prose-paperly mx-auto max-w-2xl px-4 py-12">
      <Link href="/" className="text-sm text-brand">← Paperly</Link>
      <h1 className="text-2xl">Privacy</h1>
      <p>Paperly is an open-source project. This page explains what happens to your data on this instance.</p>
      <h2>What we store</h2>
      <ul>
        <li>Your email and sign-in data (handled by Better Auth in our database).</li>
        <li>PDFs you upload, the text extracted from them, and your notes, chats, comparisons and flashcards.</li>
        <li>Daily usage counters (to enforce free quotas) and anonymous error logs with request IDs.</li>
      </ul>
      <h2>Who processes it</h2>
      <p>
        To answer a question, the relevant excerpts of your paper and your question are sent to the configured AI provider
        (Groq, Google Gemini or OpenRouter). Embeddings and search run on our own server. Papers imported from arXiv or open-access
        DOIs are cached once and shared between users; private uploads are never shared.
      </p>
      <h2>Your controls</h2>
      <p>You can download your data and permanently delete your account at any time from Settings. Deletion removes your PDFs, notes, chats and profile.</p>
      <h2>Contact</h2>
      <p>Open an issue on the project repository for privacy questions or takedown requests.</p>
    </main>
  );
}
