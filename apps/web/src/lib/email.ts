import "server-only";

type Email = { to: string; subject: string; text: string };

/**
 * Sends via Resend's free tier when RESEND_API_KEY is set; otherwise (local dev) prints the
 * message to the server console so magic links work with zero setup.
 */
export async function sendEmail(email: Email): Promise<void> {
  const key = process.env.RESEND_API_KEY;
  if (!key) {
    if (process.env.NODE_ENV === "production") throw new Error("RESEND_API_KEY is not set");
    console.info(`\n[dev email] to=${email.to} subject="${email.subject}"\n${email.text}\n`);
    return;
  }
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: { Authorization: `Bearer ${key}`, "Content-Type": "application/json" },
    body: JSON.stringify({
      from: process.env.EMAIL_FROM ?? "Paperly <onboarding@resend.dev>",
      to: email.to,
      subject: email.subject,
      text: email.text,
    }),
  });
  if (!res.ok) throw new Error(`Email send failed (${res.status})`);
}
