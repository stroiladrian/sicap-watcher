"""One-off check: can GitHub's servers read Orasul Deta's direct acquisitions
from the official SICAP public API (e-licitatie.ro)? Prints what comes back."""
import json
import urllib.request
from datetime import datetime, timedelta, timezone

AUTHORITY_ID = 11866
HOSTS = ["https://www.e-licitatie.ro", "https://e-licitatie.ro"]
PATH = "/api-pub/DirectAcquisitionCommon/GetDirectAcquisitionList/"
since = (datetime.now(timezone.utc) - timedelta(days=120)).strftime("%Y-%m-%dT00:00:00.000Z")

BODY = {
    "pageSize": 5,
    "pageIndex": 0,
    "showOngoingDa": False,
    "cookieContext": None,
    "sysDirectAcquisitionStateId": None,
    "publicationDateStart": None,
    "publicationDateEnd": None,
    "finalizationDateStart": since,
    "finalizationDateEnd": None,
    "cpvCategoryId": None,
    "cpvCodeId": None,
    "contractingAuthorityId": AUTHORITY_ID,
    "supplierId": None,
    "directAcquisitionName": None,
    "uniqueIdentificationCode": None,
}

for host in HOSTS:
    req = urllib.request.Request(
        host + PATH,
        data=json.dumps(BODY).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json;charset=UTF-8",
            "Accept": "application/json, text/plain, */*",
            "Culture": "ro",
            "Origin": host,
            "Referer": f"{host}/pub/direct-acquisitions/list/1",
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36",
        },
    )
    print(f"=== {host}")
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read().decode("utf-8", "replace")
            print("HTTP", r.status)
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        print("HTTP", e.code)
    except Exception as e:  # noqa: BLE001
        print("ERROR", repr(e))
        continue
    try:
        data = json.loads(raw)
        print("top-level keys:", list(data)[:20] if isinstance(data, dict) else type(data))
        items = data.get("items") if isinstance(data, dict) else None
        print("total:", data.get("total") if isinstance(data, dict) else None,
              "items:", len(items) if items else 0)
        if items:
            print(json.dumps(items[:2], ensure_ascii=False, indent=1)[:4000])
    except ValueError:
        print(raw[:1500])
