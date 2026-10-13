// Only public values live here. Server secrets never reach the web bundle.
export const env = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  googleEnabled: process.env.NEXT_PUBLIC_AUTH_GOOGLE === "1",
};
