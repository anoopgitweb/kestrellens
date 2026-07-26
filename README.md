# KestrelIQ

KestrelIQ is an executive intelligence web app for tracking company news, strategic signals, competitor movement, and market risk/opportunity indicators.

## Run Locally

```powershell
python app.py
```

Then open:

```text
http://127.0.0.1:8787
```

## Deploy

The app is ready for services such as Render, Railway, Fly.io, or Azure App Service.

Start command:

```bash
python app.py
```

The app automatically uses the hosting provider's `PORT` environment variable when present.

### OpenAI-powered learning

The **Ask OpenAI** and **Create Notebook** modes require a server-side OpenAI API key:

```text
OPENAI_API_KEY=your_openai_api_key
```

Set this as a secret environment variable in Render. Never place the key in `templates/index.html`, browser storage, or Supabase.

Optional model overrides:

```text
OPENAI_ASK_MODEL=gpt-5.6-luna
OPENAI_NOTEBOOK_MODEL=gpt-5.6-terra
```

The regular **Ask** mode continues to use the existing Wikipedia and Google News workflow without OpenAI. OpenAI-generated notebooks remain drafts until the signed-in user confirms that they should be saved to their private Supabase Jot Down workspace.

### Shared timeline refresh

The timeline reads its normal views and filters from Supabase. **Refresh timeline** performs a cached 48-hour discovery scan and inserts only URL-unique articles. To let a refresh initiated by any user save to the shared database, add the server-only Supabase service role key in Render:

```text
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

Never expose this key in browser code. Without it, automatic saving is limited to the signed-in timeline administrator; other users still read the shared timeline.

## Notes

- No paid news API is required for the regular Ask and intelligence-feed workflows.
- News is fetched from Google News RSS by the Python backend.
- Guest watchlist settings are stored in the user's browser local storage.
- Signed-in users can manage their account details and multiple named Supabase watchlists from their profile. Run `supabase_profiles.sql` and `supabase_watchlists.sql` once in the Supabase SQL editor before enabling these features in production.
- The current sentiment and strategy scoring are lightweight keyword-based rules and can be upgraded later.
