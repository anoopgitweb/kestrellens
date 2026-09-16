# Agentic AI Customer Operations - Maya Journey

A runnable experience-center prototype: FastAPI, vanilla HTML/CSS/JS and SQLite. Nine deterministic specialist agents work under an orchestrator, pausing for Maya’s installation choice and purchase approval. No LLM key, build step, phone account or external business system is required.

## Run

Use Python 3.10 or later. From this folder:

```bash
python -m venv .venv
```

Activate on Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Or macOS/Linux:

```bash
source .venv/bin/activate
```

Install and launch:

```bash
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open http://127.0.0.1:8000. API documentation is at http://127.0.0.1:8000/docs.
On Windows after the one-time installation, you can double-click **Launch Maya Journey.cmd**. Do not open `static/index.html` directly; the interactive experience requires the local FastAPI server.
The first launch creates `data/maya.sqlite3`. Set `MAYA_DB` to use another database path. Restarting preserves the journey; Reset restores sample records. Internet is only used for optional Google Fonts; system font fallbacks work offline after dependencies are installed.

## Present the journey

1. **Opening sequence:** the big-screen story moves through Maya arriving, iXHello/IVR self-service, iXHero real-time agent assist, Language Translation and Agentic AI. The attract screen runs for 12 seconds, IVR for 60 seconds, iXHero for 120 seconds, Translation for 60 seconds, Maya’s goal for 25 seconds and the Agentic AI handoff for 20 seconds. Use **Pause** to hold any frame and **Move forward** to advance immediately. After the operating journey completes, Forward opens the Tech Replication close.
   A persistent portfolio ribbon keeps iXHello, IVR, iXHero, Language Translation, Agentic AI and Tech Replication visible throughout, with the current experience highlighted.
2. **Set the scene:** Maya Chen is opening a second office next week. She needs the same two-printer configuration, supplies, installation and ongoing support without coordinating every party herself.
3. **Start journey:** context, solution, sourcing and commercial agents coordinate automatically, one handoff every 2.2 seconds while the page is open. Pause stops automatic progress; Forward advances one step or supplies the scripted fallback response for a pending call.
3. **First simulated call:** “Calling Maya” offers two installation windows, three and four days after reset. Choose either window as Maya. **Simulate call** chooses the first window for a hands-free scripted path. The window is held, pending purchase approval.
4. **Second simulated call:** review the $1,500 quote: $1,290 equipment, $150 installation, $60 starter supplies, demo tax included. **Approve** or **Simulate call** records Maya’s simulated approval. **Force approval** is a presenter override, clearly recorded in the feed.
5. **Finish:** supplies, maintenance, monitoring and communication complete their handoffs. **Complete** accelerates these remaining steps after approval. The summary shows the installation booking and ongoing care arrangements.
6. **Reset:** immediately restore all sample systems for the next visitor. Reset is destructive only to this demo’s local journey data.

Use **Script** for the in-app presenter guide. A full presentation takes about three minutes with narration; automatic agent work takes under 30 seconds excluding decisions. The non-modal call card leaves presenter controls available.

Alternate path: choose **Not now** on the purchase call. The journey stops, inventory is released, the tentative installation is cancelled, and no downstream care is scheduled. Reset to replay.

## Design and boundaries

- `app/main.py`: transactional state machine, orchestrator, specialist actions, event log and simulated system repository. State transitions and reservations are serialized and committed together. Repeated Start and Complete do not duplicate orders or stock reservations.
- `app/voice.py`: provider protocol, working simulated provider, server-side Twilio outbound adapter, and a Vapi extension interface. Twilio credentials and phone numbers remain outside the browser and repository.
- `static/`: responsive browser interface, live feed, decision card, summary and presenter controls.
- SQLite `systems` table holds structured JSON records for CRM/customer, stock, quote, installation slots, supplies, maintenance and monitoring. Dedicated tables hold agents, journey state and activity events.
- The orchestrator is deterministic Python, not an autonomous LLM system. Stock, orders, bookings, care and device signals are simulated. Readiness means **prepared for installation**, not installed or operational.
- The browser advances the shared journey through `/api/action` ticks. Closing the page pauses automatic progress. Use one presenter tab; multiple tabs share state and can accelerate ticks. This is a local, single-process demo, not a multi-user production deployment. Keep the server bound to localhost; endpoints intentionally have no authentication.
- Real calls occur only when Twilio is configured and a presenter clicks **Real call**. Purchases, payments, messages and business-system updates remain simulated. Sample customer data is fictional.

## Enable a real Twilio call

Twilio currently offers a 30-day trial. Trial Voice calls are limited to verified recipients (up to five), the account's signup country, and Twilio-approved templates or restricted custom TwiML. Verify the consented test recipient in Twilio before continuing. Never put credentials or a phone number in browser code or commit them to this project.

Set these server-side environment variables before starting FastAPI:

```powershell
$env:TWILIO_ACCOUNT_SID = "AC..."
$env:TWILIO_AUTH_TOKEN = "..."
$env:TWILIO_FROM_NUMBER = "+..."
$env:TWILIO_TO_NUMBER = "+..." # one consented fallback number for all three demo roles
$env:TWILIO_TWIML_URL = "https://webhooks.twilio.com/v1/Voice/Template/voice_text_to_speech"
```

For three separate participants, replace the single fallback with `TWILIO_RESELLER_NUMBER`, `TWILIO_INSTALLER_NUMBER`, and `TWILIO_MAYA_NUMBER`. Each number must be verified on a trial account.

Use E.164 phone-number format. On a trial, take the caller number and allowed template URL from **Twilio Console → Try out → Voice** because trial numbers can vary by recipient. Start the server from the same terminal. During either “Calling Maya” decision, **Real call** becomes available and queues one external call. The call SID and masked destination are recorded in the feed. The browser never receives credentials or the full destination number.

The trial template proves outbound connectivity but does not capture Maya's installation choice or approval into this prototype. Record that decision with the on-screen choice or presenter control. For the full interactive call, upgrade as required, host a public HTTPS TwiML endpoint using `<Gather>`, set `TWILIO_TWIML_URL` to it, and optionally set `TWILIO_STATUS_CALLBACK_URL`. Verify Twilio webhook signatures before trusting callbacks. The included adapter deliberately does not expose an inbound webhook until that verification is implemented.

## Optional natural OpenAI voice

The **Talk naturally with OpenAI** control connects Maya to the OpenAI Realtime API over browser WebRTC. FastAPI proxies session setup so the API key stays server-side. Set it before launch:

```powershell
$env:OPENAI_API_KEY = "sk-..."
$env:OPENAI_REALTIME_MODEL = "gpt-realtime" # optional
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Allow microphone access when prompted. Without a key, the simulated voice-over remains available.

## Verify

```bash
python -m unittest discover -s tests -v
```

Tests use a temporary SQLite database and cover both installation windows, approval gates, duplicate actions, rejection cleanup, full readiness and reset.
