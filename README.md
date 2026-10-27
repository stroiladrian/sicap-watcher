# SICAP watcher

Checks Orasul Deta's direct purchases every 2 hours, 08:00–22:00 Bucharest time, straight from the official SICAP public API (e-licitatie.ro), and sends only new ones to your alert channels. Runs on GitHub, free, no MacBook needed.

## Alert channels

Repo secrets (Settings → Secrets and variables → Actions → *Secrets*). Alerts go to every channel that's set.

- **Telegram**: `TELEGRAM_BOT_TOKEN` (from @BotFather) and `TELEGRAM_CHAT_ID`
- **ntfy**: `NTFY_TOPIC`, a long random name you subscribe to in the ntfy app
- **WhatsApp via CallMeBot**: `CALLMEBOT_PHONE` (e.g. `+40712345678`) and `CALLMEBOT_APIKEY`

## Use

- **Test alert**: Actions → *SICAP watcher* → *Run workflow*, tick "Only send a test alert".
- **Check now**: *Run workflow*, unticked. The very first check saves what's already there and sends "SICAP watcher active"; after that you only hear about new purchases.

## More authorities

Add a repo *variable* `WATCH_AUTHORITIES` (same settings page, *Variables* tab): one per line, either the ID (`11866`) or a sicap.ai link like `https://sicap.ai/achizitii/autoritate/11866`. If you set it, include Deta too.

## If it breaks

A failed run (API down, alert not sent) shows red in Actions and GitHub emails you. Unsent alerts are retried on the next run.
