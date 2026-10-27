"""SICAP watcher: asks the official SICAP public API (e-licitatie.ro) for an
authority's direct purchases, finds ones not seen before, and alerts on
Telegram, ntfy and/or WhatsApp (CallMeBot).

Env:
  WATCH_AUTHORITIES  authority IDs or sicap.ai / e-licitatie links, one per line
                     (default: 11866 = Orasul Deta)
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID   Telegram bot
  NTFY_TOPIC         ntfy.sh topic (use a long random name)
  CALLMEBOT_PHONE, CALLMEBOT_APIKEY      WhatsApp via CallMeBot
  FORCE_RUN=1        ignore the 08:00-22:00 window (manual runs)
  TEST_MESSAGE=1     send a test message and exit
"""
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent
STATE = ROOT / "seen.json"
TZ = ZoneInfo("Europe/Bucharest")
DEFAULT_AUTHORITIES = ["11866"]
API = "https://www.e-licitatie.ro/api-pub/DirectAcquisitionCommon/GetDirectAcquisitionList/"
VIEW = "https://e-licitatie.ro/pub/direct-acquisition/view/{}"
SICAP_AI = "https://sicap.ai/achizitii/autoritate/{}"
LOOKBACK_DAYS = 60
MONTHS = "ian feb mar apr mai iun iul aug sep oct noi dec".split()


def now_local():
    return datetime.now(TZ)


def in_window():
    if os.environ.get("FORCE_RUN") == "1":
        return True
    return 8 <= now_local().hour <= 22


# ---------- alerts ----------

def _env(name):
    return os.environ.get(name, "").strip()


def _chunks(text, limit):
    out, buf = [], ""
    for block in text.split("\n\n"):
        if len(buf) + len(block) > limit and buf:
            out.append(buf)
            buf = ""
        buf = f"{buf}\n\n{block}" if buf else block
    if buf:
        out.append(buf)
    return out


def _request(name, url, data=None, headers=None):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, data=data, headers=headers or {})
            with urllib.request.urlopen(req, timeout=60) as r:
                if r.status == 200:
                    return True
                print(f"{name} HTTP {r.status}")
        except Exception as e:  # noqa: BLE001
            print(f"{name} error: {e}")
        time.sleep(10 * (attempt + 1))
    return False


def send_callmebot(text):
    phone, key = _env("CALLMEBOT_PHONE"), _env("CALLMEBOT_APIKEY")
    ok = True
    for chunk in _chunks(text, 900):
        q = urllib.parse.urlencode({"phone": phone, "text": chunk, "apikey": key})
        ok &= _request("CallMeBot", f"https://api.callmebot.com/whatsapp.php?{q}")
        time.sleep(5)
    return ok


def send_telegram(text):
    token, chat = _env("TELEGRAM_BOT_TOKEN"), _env("TELEGRAM_CHAT_ID")
    ok = True
    for chunk in _chunks(text, 3500):
        data = urllib.parse.urlencode({"chat_id": chat, "text": chunk,
                                       "disable_web_page_preview": "true"}).encode()
        ok &= _request("Telegram", f"https://api.telegram.org/bot{token}/sendMessage", data)
    return ok


def send_ntfy(text):
    title, _, body = text.partition("\n")
    q = urllib.parse.urlencode({"title": title})
    return _request("ntfy", f"https://ntfy.sh/{urllib.parse.quote(_env('NTFY_TOPIC'))}?{q}",
                    (body.strip() or title).encode("utf-8"))


def notify(text):
    channels = []
    if _env("TELEGRAM_BOT_TOKEN") and _env("TELEGRAM_CHAT_ID"):
        channels.append(send_telegram)
    if _env("NTFY_TOPIC"):
        channels.append(send_ntfy)
    if _env("CALLMEBOT_PHONE") and _env("CALLMEBOT_APIKEY"):
        channels.append(send_callmebot)
    if not channels:
        print("No alert channel configured; message would have been:\n" + text)
        return False
    return any([ch(text) for ch in channels])


# ---------- SICAP ----------

def fetch(authority_id):
    """Recent direct purchases for one authority, keyed by DA code."""
    since = (datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)).strftime(
        "%Y-%m-%dT00:00:00.000Z")
    base = {
        "pageSize": 100, "pageIndex": 0, "showOngoingDa": False, "cookieContext": None,
        "sysDirectAcquisitionStateId": None, "publicationDateStart": None,
        "publicationDateEnd": None, "finalizationDateStart": None,
        "finalizationDateEnd": None, "cpvCategoryId": None, "cpvCodeId": None,
        "contractingAuthorityId": int(authority_id), "supplierId": None,
        "directAcquisitionName": None, "uniqueIdentificationCode": None,
    }
    queries = [
        {**base, "publicationDateStart": since},
        {**base, "finalizationDateStart": since},
        {**base, "publicationDateStart": since, "showOngoingDa": True},
    ]
    items, errors = {}, 0
    for body in queries:
        req = urllib.request.Request(API, data=json.dumps(body).encode(), method="POST", headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "Culture": "ro",
            "Origin": "https://www.e-licitatie.ro",
            "Referer": "https://www.e-licitatie.ro/pub/direct-acquisitions/list/1",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            print(f"SICAP API error ({authority_id}): {e}")
            errors += 1
            continue
        for it in data.get("items") or []:
            code = it.get("uniqueIdentificationCode")
            if code:
                items[code] = it
        time.sleep(1)
    if errors == len(queries):
        return None
    return items


def ron(v):
    if v is None:
        return None
    whole = f"{round(v):,}".replace(",", ".")
    return f"{whole} RON"


def ro_date(s):
    try:
        d = datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def format_item(it):
    supplier = re.sub(r"^RO?\d+\s+", "", it.get("supplier") or "").strip()
    value = it.get("closingValue") or it.get("estimatedValueRon")
    meta = [m for m in (
        f"💰 {ron(value)}" if value else None,
        f"🏢 {supplier[:60]}" if supplier else None,
        f"📅 {ro_date(it.get('publicationDate'))}" if it.get("publicationDate") else None,
    ) if m]
    lines = [f"🆕 {(it.get('directAcquisitionName') or it['uniqueIdentificationCode'])[:150]}"]
    if meta:
        lines.append(" · ".join(meta))
    lines.append(VIEW.format(it["directAcquisitionId"]))
    return "\n".join(lines)


def authority_ids():
    raw = _env("WATCH_AUTHORITIES").replace(",", "\n")
    ids = []
    for line in raw.splitlines():
        m = re.search(r"(\d+)\D*$", line.strip())
        if m:
            ids.append(m.group(1))
    return ids or DEFAULT_AUTHORITIES


def load_state():
    if STATE.exists():
        data = json.loads(STATE.read_text(encoding="utf-8") or "{}")
        return {k: v for k, v in data.items() if k.isdigit()}  # drop old sicap.ai keys
    return {}


def save_state(state):
    STATE.write_text(json.dumps(state, ensure_ascii=False, indent=1, sort_keys=True) + "\n",
                     encoding="utf-8")


def main():
    if os.environ.get("TEST_MESSAGE") == "1":
        sys.exit(0 if notify("✅ SICAP watcher: test message. Alerts will arrive here.") else 1)

    if not in_window():
        print(f"Outside 08:00-22:00 Bucharest ({now_local():%H:%M}); skipping.")
        return

    state = load_state()
    failed = []

    for aid in authority_ids():
        items = fetch(aid)
        if items is None:
            failed.append(aid)
            continue
        prev = state.get(aid)
        seen = set(prev["ids"]) if prev else set()
        new = sorted((it for code, it in items.items() if code not in seen),
                     key=lambda it: it.get("publicationDate") or "")
        name = next((re.sub(r"^RO?\d+\s+", "", it.get("contractingAuthority") or "")
                     for it in items.values()), "") or f"autoritate {aid}"
        print(f"{name} ({aid}): {len(items)} recent, {len(new)} new, first_run={prev is None}")

        if prev is None:
            notify(f"✅ SICAP watcher active · {name}\n{len(items)} recent purchases saved, "
                   f"you'll only get alerts for new ones.\n🔗 {SICAP_AI.format(aid)}")
        elif new:
            header = f"🔔 SICAP · {name} – {len(new)} new"
            body = "\n\n".join(format_item(it) for it in new)
            if not notify(f"{header}\n\n{body}\n\n🔗 {SICAP_AI.format(aid)}"):
                failed.append(aid)
                continue  # retry next run

        state[aid] = {"ids": sorted(seen | set(items)),
                      "last_ok": now_local().strftime("%Y-%m-%d")}

    save_state(state)
    if failed:
        print("Failed for:", ", ".join(failed))
        sys.exit(1)


if __name__ == "__main__":
    main()
