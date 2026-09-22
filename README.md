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

### Google Drive notebook images

New Learning Experience page images are stored as private files in a Google
Drive folder. Supabase continues to provide authentication and notebook data.
Configure these server-only Render environment variables:

```text
GOOGLE_DRIVE_SERVICE_ACCOUNT_JSON={the complete service-account JSON object}
GOOGLE_DRIVE_FOLDER_ID=the_target_shared_drive_folder_id
GOOGLE_DRIVE_SHARED_DRIVE_ID=the_shared_drive_id
```

Enable the Google Drive API and add the service-account email as a Content
manager of the target Shared Drive or folder. Never expose the service-account
JSON in browser code or commit it to Git. The application stores the returned
Drive file ID in the private notebook content and streams images through the
authenticated backend; it does not create public Drive links.

Existing notebook images with Supabase Storage paths remain readable during
the transition. New images use Drive IDs prefixed with `gdrive:`. Existing
files should be migrated separately after Drive configuration is verified.

### Shared timeline refresh

The timeline reads its normal views and filters from Supabase. **Refresh timeline** performs a cached 48-hour discovery scan and inserts only URL-unique articles. To let a refresh initiated by any user save to the shared database, add the server-only Supabase service role key in Render:

```text
SUPABASE_SERVICE_ROLE_KEY=your_supabase_service_role_key
```

Never expose this key in browser code. Without it, automatic saving is limited to the signed-in timeline administrator; other users still read the shared timeline.

### Vivawise AI Quick Bytes feed

Vivawise can read a narrowly scoped, read-only feed containing only the
configured user's notebook named **Daily Learnings**. The endpoint does not
return any other notebook, profile, watchlist, or intelligence data.

Configure these server-only values in Render:

```text
QUICK_BYTES_SYNC_TOKEN=use-a-long-random-shared-secret
QUICK_BYTES_SOURCE_EMAIL=anoopviswanathan@outlook.com
```

`QUICK_BYTES_SOURCE_USER_ID` may be used instead of the email when a stable
Supabase user UUID is preferred. `SUPABASE_SERVICE_ROLE_KEY` is also required.
Vivawise must send the shared token as a Bearer token to
`GET /api/vivawise/quick-bytes`. Never place the token or service-role key in
browser code.

## Notes

- No paid news API is required for the regular Ask and intelligence-feed workflows.
- News is fetched from Google News RSS by the Python backend.
- Guest watchlist settings are stored in the user's browser local storage.
- Signed-in users can manage their account details and multiple named Supabase watchlists from their profile. Run `supabase_profiles.sql` and `supabase_watchlists.sql` once in the Supabase SQL editor before enabling these features in production.
- The current sentiment and strategy scoring are lightweight keyword-based rules and can be upgraded later.

### StatLens statistical analysis (local toolkit)

Open **Tool Kit > Data & Analytics > StatLens — Statistical Analysis**.
Administrators can enable `statlens` in the existing user tool-access list.
The signed-in launch route starts the bundled Python app on a free loopback
port and opens it in the toolkit tab. Repeat launches reuse that process.
This integration is for KestrelIQ running on the same computer as the browser;
remote launches show a local-use explanation rather than redirecting to the
remote visitor's computer. StatLens itself remains a local, single-user tool.

### BLEU Score Calculator

Open **Tool Kit > Data & Analytics > BLEU Score Calculator**. Administrators
can enable `bleu-calculator` in the existing user tool-access list. The BLEU-4
calculation and its n-gram explanation run in the browser. Translation and
AI-estimated semantic metrics use the server-side `OPENAI_API_KEY`.

### TextForge text and data studio

Open **Tool Kit > Productivity Tool Kit > TextForge — Text & Data Studio**.
Administrators can enable `textforge` in the existing user tool-access list.
TextForge provides browser-based formatting, conversion, preview, parsing, and
analysis tools for HTML, CSV, Excel, JSON, Markdown, XML, YAML, SQL, URLs, and text.

The app is bundled in `tools/statlens`. The launcher uses its `.venv` when
available, otherwise the Codex bundled Python runtime, then the current Python.
On another machine, install `tools/statlens/requirements.txt` into its virtual
environment. PPT export also requires the Node/artifact-tool runtime described
by the StatLens setup. Uploaded datasets stay in local process memory.
Restart KestrelIQ after installing this integration.


### Slide Studio PPT Maker (local toolkit)

Open **Tool Kit > Presenters > Slide Studio — PPT Maker**.
Administrators can enable `slide-studio` in the existing user tool-access list.
The authenticated, local-only launch starts the offline Flask app on a free
loopback port and reuses it for subsequent launches. It supports editable
slides, statistical charts, images, themes, previews and PowerPoint export.
The files live in `tools/slide-studio`. The launcher uses that folder's `.venv`,
otherwise the bundled Codex Python runtime, then the current Python interpreter.
On another machine install `tools/slide-studio/requirements.txt` into its `.venv`.
No AI or external service is used by Slide Studio. KestrelIQ sign-in still uses
its existing authentication. Save project files before closing KestrelIQ:
browser autosave belongs to the app's port, which may change after a restart.
Use Open project to transfer a project from the standalone app on port 5050.
Restart KestrelIQ after installing this integration.
