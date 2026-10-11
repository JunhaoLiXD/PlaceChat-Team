# Supabase

SQL migrations live in `migrations/`. They are the only way the database schema changes: never edit tables by hand in the dashboard, and never edit a migration that is already merged.

The Supabase CLI setup and the workflow that applies migrations to staging come with PBI-05 (#9).
