KestrelIQ Executive Intelligence

How to run:
1. Double-click START_KESTRELIQ.bat
2. Open http://127.0.0.1:8787 in your browser
3. Add company names to the watchlist
4. Click Refresh Feeds

How it fetches news:
- The app uses Google News RSS search from the local Python backend.
- No API key is required for this first version.
- The browser does not scrape Google directly, which avoids CORS and reliability issues.

Notes:
- Companies are stored in the browser's local storage.
- News results are cached by the backend for 15 minutes.
- Sentiment is simple keyword-based tagging and can be upgraded later.
