# Supabase

SQL migrations live in `migrations/`. They are the only way the database schema changes: never edit tables by hand in the dashboard, and never edit a migration that is already merged.

## Add a migration

You need Node.js 24. The CLI runs through `npx`, pinned to the same version CI uses:

```bash
npx supabase@2.118.0 migration new create_rooms   # from the repository root
```

This creates `migrations/<timestamp>_create_rooms.sql`. Write plain SQL in it and open a pull request as usual.

To try a migration before it is merged, push it to your own free Supabase project, never to staging:

```bash
npx supabase@2.118.0 link --project-ref <your-project-ref>
npx supabase@2.118.0 db push
```

## How migrations reach staging

When a pull request that changes `migrations/` is merged into `main`, the [`migrate`](../.github/workflows/migrate.yml) workflow runs `supabase db push` against `placechat-staging`. Check the Actions tab if your tables do not show up. Junhao applies migrations to production at release.

`config.toml` only configures the local Supabase stack (`supabase start`); staging and production settings are made in the dashboard ([PlaceChat Technical Design §12](../docs/technical-design.md#12-one-time-setup-junhao)).
