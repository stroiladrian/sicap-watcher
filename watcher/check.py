"""SICAP watcher: opens a sicap.ai authority page in headless Chromium,
finds listings not seen before, and sends them to WhatsApp via CallMeBot.

Env:
  WATCH_URLS         newline/comma separated pages to watch (default: Orasul Deta)
  CALLMEBOT_PHONE    your WhatsApp number in international format, e.g. +40712345678
  CALLMEBOT_APIKEY   key CallMeBot sent you
  FORCE_RUN=1        ignore the 08:00-22:00 window (manual runs)
  TEST_MESSAGE=1     send a test WhatsApp message and exit
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "seen.json"
DEBUG = ROOT.parent / "debug"
TZ = ZoneInfo("Europe/Bucharest")
DEFAULT_URLS = ["https://sicap.ai/achizitii/autoritate/11866"]

# SICAP notice / direct-purchase IDs, e.g. DA41381570, ADV1234567, CAN1234567
ID_RE = re.compile(r"\b(?:DA|ADV|CAN|SCN|RFQ|CN|PI|DAN)\d{6,}\b")


def now_local():
    return datetime.now(TZ)


def in_window():
    """Runs are scheduled for both summer and winter time; keep only the ones
    that land between 08:00 and 22:59 Bucharest time."""
    if os.environ.get("FORCE_RUN") == "1":
        return True
    return 8 <= now_local().hour <= 22


def send_whatsapp(text):
    phone = os.environ.get("CALLMEBOT_PHONE", "").strip()
    key = os.environ.get("CALLMEBOT_APIKEY", "").strip()
    if not phone or not key:
        print("CallMeBot secrets missing; message would have been:\n" + text)
        return False
    # CallMeBot works best with short messages; split long ones.
    chunks, buf = [], ""
    for block in text.split("\n\n"):
        if len(buf) + len(block) > 900 and buf:
            chunks.append(buf)
            buf = ""
        buf = f"{buf}\n\n{block}" if buf else block
    if buf:
        chunks.append(buf)
    ok = True
    for i, chunk in enumerate(chunks):
        q = urllib.parse.urlencode({"phone": phone, "text": chunk, "apikey": key})
        url = f"https://api.callmebot.com/whatsapp.php?{q}"
        for attempt in range(3):
            try:
                with urllib.request.urlopen(url, timeout=60) as r:
                    body = r.read().decode("utf-8", "replace")
                if r.status == 200:
                    break
                print(f"CallMeBot HTTP {r.status}: {body[:200]}")
            except Exception as e:  # noqa: BLE001
                print(f"CallMeBot error: {e}")
            time.sleep(10 * (attempt + 1))
        else:
            ok = False
        if i < len(chunks) - 1:
            time.sleep(5)  # CallMeBot rate limit
    return ok


EXTRACT_JS = r"""
(idSource) => {
  const idRe = new RegExp(idSource, 'g');
  const out = {};
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  const hits = [];
  while (walker.nextNode()) {
    const t = walker.currentNode.nodeValue;
    const m = t && t.match(idRe);
    if (m) for (const id of m) hits.push([id, walker.currentNode.parentElement]);
  }
  const countIds = (el) => new Set((el.innerText || '').match(idRe) || []).size;
  for (const [id, start] of hits) {
    if (out[id]) continue;
    // climb to the largest ancestor that still contains only this one ID = the listing card/row
    let el = start, best = start;
    while (el && el !== document.body) {
      if (countIds(el) > 1) break;
      best = el;
      el = el.parentElement;
    }
    const link = best.querySelector('a[href]') || best.closest('a[href]');
    out[id] = {
      text: (best.innerText || '').trim(),
      href: link ? link.href : null,
    };
  }
  return out;
}
"""


def scrape(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            locale="ro-RO",
            timezone_id="Europe/Bucharest",
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
        )
        page = ctx.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=90_000)
        items = {}
        # bot checks usually resolve within a few seconds; poll for listings
        for _ in range(12):
            page.wait_for_timeout(5_000)
            items = page.evaluate(EXTRACT_JS, ID_RE.pattern)
            if items:
                page.wait_for_timeout(3_000)  # let the rest of the list render
                items = page.evaluate(EXTRACT_JS, ID_RE.pattern)
                break
        if not items:
            DEBUG.mkdir(exist_ok=True)
            page.screenshot(path=str(DEBUG / "page.png"), full_page=True)
            (DEBUG / "page.html").write_text(page.content(), encoding="utf-8")
            (DEBUG / "title.txt").write_text(page.title(), encoding="utf-8")
        browser.close()
        return items


MONEY_RE = re.compile(r"[\d][\d.\s]*(?:,\d+)?\s*(?:RON|LEI|lei|EUR)")
DATE_RE = re.compile(
    r"\b\d{1,2}[./ ](?:\d{1,2}|ian|feb|mar|apr|mai|iun|iul|aug|sep|oct|noi|nov|dec)[a-z.]*[./ ]\d{2,4}\b",
    re.I,
)


def format_item(item_id, item):
    lines = [l.strip() for l in item["text"].splitlines() if l.strip()]
    title = next((l for l in lines if not ID_RE.fullmatch(l) and len(l) > 3
                  and not MONEY_RE.search(l) and not DATE_RE.fullmatch(l)), item_id)
    money = next((MONEY_RE.search(l).group(0) for l in lines if MONEY_RE.search(l)), None)
    date = next((DATE_RE.search(l).group(0) for l in lines if DATE_RE.search(l)), None)
    others = [l for l in lines if l != title and item_id not in l
              and not MONEY_RE.search(l) and not (date and date in l)]
    supplier = others[0] if others else None
    out = [f"🆕 {title[:140]}"]
    meta = []
    if money:
        meta.append(f"💰 {money}")
    if supplier:
        meta.append(f"🏢 {supplier[:60]}")
    if date:
        meta.append(f"📅 {date}")
    if meta:
        out.append(" · ".join(meta))
    out.append(f"#{item_id}" + (f" {item['href']}" if item.get("href") else ""))
    return "\n".join(out)


def load_state():
    if STATE.exists():
        return json.loads(STATE.read_text(encoding="utf-8"))
    return {}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")


def main():
    if os.environ.get("TEST_MESSAGE") == "1":
        ok = send_whatsapp("✅ SICAP watcher: test message. Alerts will arrive here.")
        sys.exit(0 if ok else 1)

    if not in_window():
        print(f"Outside 08:00-22:00 Bucharest ({now_local():%H:%M}); skipping.")
        return

    raw = os.environ.get("WATCH_URLS", "").replace(",", "\n")
    urls = [u.strip() for u in raw.splitlines() if u.strip()] or DEFAULT_URLS
    state = load_state()
    failed = []

    for url in urls:
        items = scrape(url)
        if not items:
            print(f"No listings found on {url} (blocked or layout changed). See debug/.")
            failed.append(url)
            continue
        seen = set(state.get(url, {}).get("ids", []))
        first_run = url not in state
        new = [i for i in items if i not in seen]
        print(f"{url}: {len(items)} listings, {len(new)} new, first_run={first_run}")

        if first_run:
            send_whatsapp(
                f"✅ SICAP watcher active\n{len(items)} existing listings saved, "
                f"you'll only get alerts for new ones.\n🔗 {url}"
            )
        elif new:
            header = f"🔔 SICAP – {len(new)} new" if len(new) > 1 else "🔔 SICAP – 1 new"
            body = "\n\n".join(format_item(i, items[i]) for i in new)
            if not send_whatsapp(f"{header}\n\n{body}\n\n🔗 {url}"):
                failed.append(url)
                continue  # don't mark as seen, retry next run

        state[url] = {
            "ids": sorted(seen | set(items)),
            "last_ok": now_local().strftime("%Y-%m-%d"),
        }

    save_state(state)
    if failed:
        sys.exit(1)  # GitHub emails you when a run fails


if __name__ == "__main__":
    main()
