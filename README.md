# LinkedIn Telegram Agent — Mobile Deployment Starter

Telegram-controlled invitation planner. **Preview-only**: does NOT sign in to LinkedIn, does NOT send connection requests, and does NOT verify invitations on LinkedIn. No LinkedIn password required.

## Android-only deployment

1. Create a new GitHub private repository.
2. Upload all files from this folder to the repository root (not the ZIP file itself).
3. Create Railway account at https://railway.com, link GitHub and choose New Project → Deploy from GitHub Repo. Select repository.
4. In Railway service → Variables, create:
   - `TELEGRAM_BOT_TOKEN` (secret from BotFather)
   - `TELEGRAM_OWNER_ID` (your numeric Telegram account user ID)
   - `DATA_DIR` = `/data`
5. Attach Railway Volume with mount path `/data` to preserve the SQLite database across deployments.
6. Deploy; `Dockerfile` automatically starts `python bot.py`. No public domain needed. Only one replica; do not run bot simultaneously anywhere else.
7. Open Telegram bot and send `/start`, `/status`.

## Commands

- `/start`, `/help` — instructions.
- `/add Name | https://www.linkedin.com/in/username/ | Note` — add profile.
- Upload CSV with columns `name,profile_url,note` — bulk add.
- `/queue` — next five profiles.
- `/run` — preview five profiles immediately.
- `/auto_on`, `/auto_off` — schedule preview every two hours, Baku 09:00–19:00.
- `/status` — local database counters (not LinkedIn server-confirmed).
- `/mark sent https://www.linkedin.com/in/username/` — log a manual invitation.
- `/report` — last 15 local events.
- `/export` — profile CSV report.
- `/draft Name | Position | Company | Goal` — simple **non-AI** message template.

Limits: group size five. Manual sending counts are shown against configurable-style informational 20/24h and 60/7d reference thresholds; the program **does not send anything** and does not enforce these thresholds for manual recordings. LinkedIn acceptance/rejection data is not available.

## Security

Never put the BotFather token into the repository or share it in chat. Railway Variables only. Anyone with your bot token can control your Telegram bot; rotate leaked tokens through BotFather. The agent accepts commands only from `TELEGRAM_OWNER_ID` in private chat. No LinkedIn credentials are collected.

This starter is independent of any preexisting Windows automation files, which were not provided. Railway may bill for usage; check its current plan/credit limits.
