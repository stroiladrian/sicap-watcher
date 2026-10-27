# SICAP watcher

Checks https://sicap.ai/achizitii/autoritate/11866 (Orasul Deta) every 2 hours, 08:00–22:00 Bucharest time, on GitHub's servers, and sends only new listings to WhatsApp via CallMeBot. Free.

## Setup

1. **CallMeBot key**: follow the WhatsApp steps on callmebot.com. You save their number, send it the activation message, and it replies with your API key.
2. **Repo secrets** (Settings → Secrets and variables → Actions → *Secrets*):
   - `CALLMEBOT_PHONE`: your number, e.g. `+40712345678`
   - `CALLMEBOT_APIKEY`: the key from step 1
3. **Test**: Actions → *SICAP watcher* → *Run workflow*, tick "Only send a test WhatsApp message".
4. **First real run**: *Run workflow* again, unticked. It saves the current listings and sends "SICAP watcher active". After that you only hear about new items.

## More pages

Add a repo *variable* `WATCH_URLS` (same settings page, *Variables* tab) with one URL per line. Each page is tracked separately.

## If it breaks

A failed run (page blocked, layout changed, WhatsApp not sent) shows red in Actions and GitHub emails you. The page screenshot is attached to the run as the `debug` artifact.
