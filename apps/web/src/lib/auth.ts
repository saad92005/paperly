import "server-only";

import { betterAuth } from "better-auth";
import { nextCookies } from "better-auth/next-js";
import { jwt, magicLink } from "better-auth/plugins";
import { Pool } from "pg";

import { sendEmail } from "@/lib/email";
import { site } from "@/lib/site";

// DATABASE_URL is written for the API's asyncpg driver (`postgresql+asyncpg://…?ssl=require`);
// node-postgres wants the plain scheme and `sslmode=require` instead.
const connectionString = (process.env.DATABASE_URL ?? "")
  .replace("postgresql+asyncpg://", "postgresql://")
  .replace(/([?&])ssl=require\b/, "$1sslmode=require");

const google =
  process.env.GOOGLE_CLIENT_ID && process.env.GOOGLE_CLIENT_SECRET
    ? {
        google: {
          clientId: process.env.GOOGLE_CLIENT_ID,
          clientSecret: process.env.GOOGLE_CLIENT_SECRET,
        },
      }
    : undefined;

export const googleEnabled = Boolean(google);

export const auth = betterAuth({
  appName: site.name,
  baseURL: process.env.WEB_BASE_URL ?? "http://localhost:3000",
  secret: process.env.BETTER_AUTH_SECRET,
  database: new Pool({ connectionString, max: 5 }),
  advanced: { database: { generateId: "uuid" } },
  // Defaults allow only 3 sign-ins per 10 s, which real users hit after a mistyped password.
  rateLimit: {
    enabled: true,
    window: 60,
    max: 100,
    customRules: {
      "/sign-in/email": { window: 60, max: 10 },
      "/sign-up/email": { window: 60, max: 5 },
      "/sign-in/magic-link": { window: 60, max: 5 },
    },
  },
  emailAndPassword: { enabled: true, minPasswordLength: 8 },
  socialProviders: google,
  plugins: [
    magicLink({
      expiresIn: 600,
      sendMagicLink: async ({ email, url }) => {
        await sendEmail({
          to: email,
          subject: `Sign in to ${site.name}`,
          text: `Click to sign in to ${site.name}: ${url}\n\nThis link expires in 10 minutes.`,
        });
      },
    }),
    // Short-lived ES256 JWTs for the FastAPI service, verified there via /api/auth/jwks.
    jwt({
      jwks: { keyPairConfig: { alg: "ES256" } },
      jwt: { audience: "paperly-api", expirationTime: "15m" },
    }),
    nextCookies(),
  ],
});
