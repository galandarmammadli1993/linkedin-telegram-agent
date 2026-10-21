# LinkedIn Telegram Agent — Tencent EdgeOne Makers

This is a **preview-only** personal Telegram bot. It does not log in to LinkedIn or send automatic invitations.

## Android deployment

1. In Tencent [EdgeOne Makers](https://pages.edgeone.ai/), choose **Create Project → Import Git Repository**, authorize GitHub, choose `galandarmammadli1993/linkedin-telegram-agent`.
2. Select **Other/None/Static**; build and install commands empty, output directory **`public`**, root directory **`./`**. Click **Start Deployment**. The `edgeone.json` file holds these defaults.
3. Under **Project Settings → Environment Management → Production → Environment Variables**, enter:
   - `TELEGRAM_BOT_TOKEN` — your BotFather HTTP API token (never share).
   - `TELEGRAM_OWNER_ID` — your private Telegram numeric user ID.
   - `WEBHOOK_SECRET` — long random string (letters, numbers, underscores or hyphens).
   - `SETUP_KEY` — different long random string.
   - `CRON_SECRET` — third independent random string.
   Redeploy after adding variables (a prior deployment does not pick up changed environment variables).
4. Storage → **KV Storage → Apply Now** (approval may be required). Create namespace and bind it to the project as **`agent_kv`**. The bot responds to `/start` without KV; state-changing commands need KV.
5. Obtain your EdgeOne public production URL, e.g. `https://YOUR-PROJECT.edgeone.app`. In your **private** Android browser address bar open:
   `https://YOUR-PROJECT.edgeone.app/api/telegram?setup=YOUR_SETUP_KEY`
   It should say **webhook registered**. The query setup key may remain in browser history; never paste it into chat.
6. Visit your bot in Telegram and send `/start`, `/status`. Try:
   `/add Ad Soyad | https://www.linkedin.com/in/username/ | Qeyd`
   `/queue`, `/run`, `/report`, `/draft Ad | Vəzifə | Şirkət | Məqsəd`
7. For scheduled previews, in GitHub repository **Settings → Secrets and variables → Actions**, create:
   - `EDGEONE_ENDPOINT` = `https://YOUR-PROJECT.edgeone.app/api/telegram`
   - `EDGEONE_CRON_SECRET` = same secret as EdgeOne `CRON_SECRET`.
   The included `.github/workflows/two-hour-preview.yml` invokes the endpoint at **09:17, 11:17, 13:17, 15:17, 17:17, 19:17 (Asia/Baku)** every day. GitHub Actions timing is best-effort and may be delayed.
8. Telegram: send `/auto_on` to enable automatic previews; `/auto_off` disables. These never send LinkedIn invitations.

## Notes
- The old `bot.py` and `Dockerfile` are preserved as the prior Railway long-running process; they are **not used** by EdgeOne.
- The new code is `edge-functions/api/telegram.js`. It uses webhook delivery rather than long polling.
- KV is eventually consistent; immediate concurrent updates on different edge nodes can conflict. This lightweight single-user starter is not a transactional CRM.
- Initial variant: 5 profiles per preview, no auto-sending, no AI API, no CSV import. `/mark sent` records the owner's manual statement, not server verification.
- Bot token and other secrets belong only in EdgeOne/GitHub secrets—not in any repository file.
- The EdgeOne KV service may require applying and waiting for approval. The platform currently documents a free tier but does not guarantee permanent pricing.

Useful documentation:
- https://pages.edgeone.ai/document/importing-a-git-repository
- https://pages.edgeone.ai/document/edge-functions
- https://pages.edgeone.ai/document/kv-storage
- https://pages.edgeone.ai/document/edgeone-json
- https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows
