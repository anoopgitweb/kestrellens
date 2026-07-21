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

## Notes

- No paid news API is required for this first version.
- News is fetched from Google News RSS by the Python backend.
- Guest watchlist settings are stored in the user's browser local storage.
- Signed-in users can manage multiple named Supabase watchlists from their profile. Run `supabase_watchlists.sql` once in the Supabase SQL editor before enabling this feature in production.
- The current sentiment and strategy scoring are lightweight keyword-based rules and can be upgraded later.
