// Public settings, inlined into the browser bundle when `next build` runs.
// Next.js only inlines a variable written out in full as `process.env.NEXT_PUBLIC_...`,
// so never read these through a computed key.
export const publicConfig = {
  apiBaseUrl: process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  supabaseUrl: process.env.NEXT_PUBLIC_SUPABASE_URL ?? "",
  supabasePublishableKey:
    process.env.NEXT_PUBLIC_SUPABASE_PUBLISHABLE_KEY ?? "",
} as const;
