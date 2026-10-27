# SICAP watcher

Checks https://sicap.ai/achizitii/autoritate/11866 (Orasul Deta) every 2 hours, 08:00–22:00 Bucharest time, on GitHub's servers, and sends only new listings to every alert channel you've set up. Free.

## Alert channels

Set any of these as repo secrets (Settings → Secrets and variables → Actions → *Secrets*). Alerts go to all channels that are set.

- **ntfy** (push notification app, no account): `NTFY_TOPIC`, a long random name you also subscribe to in the ntfy app.
- **Telegram**: `TELEGRAM_BOT_TOKEN` (from @BotFather) and `TELEGRAM_CHAT_ID`.
- **WhatsApp via CallMeBot**: `CALLMEBOT_PHONE` (e.g. `+40712345678`) and `CALLMEBOT_APIKEY` (from the steps on callmebot.com).

## Setup

1. Add the secrets for at least one channel.
2. **Test**: Actions → *SICAP watcher* → *Run workflow*, tick "Only send a test alert".
3. **First real run**: *Run workflow* again, unticked. It saves the current listings and sends "SICAP watcher active". After that you only hear about new items.

## More pages

Add a repo *variable* `WATCH_URLS` (same settings page, *Variables* tab) with one URL per line. Each page is tracked separately.

## If it breaks

A failed run (page blocked, layout changed, alert not sent) shows red in Actions and GitHub emails you. The page screenshot is attached to the run as the `debug` artifact.
