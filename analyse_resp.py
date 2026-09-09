import json
from pathlib import Path

LOG = Path("data/diagnostico/resp_endpoints.jsonl")

for line in open(LOG, encoding="utf-8"):
    d = json.loads(line)
    body = d.get("body", {})
    arts = body.get("articles") or []
    for a in arts:
        an = a.get("articleNumber")
        if an != "116263":
            continue
        print("== artigo", an, "(", a.get("mfrName"), ") ==")
        print("dataSupplierId:", a.get("dataSupplierId"))
        print("totalLinkages:", a.get("totalLinkages"))
        print()
        print("--- linkages[0] (estrutura) ---")
        lk = a.get("linkages") or []
        print("len linkages:", len(lk))
        for it in lk[:3]:
            print(json.dumps(it, ensure_ascii=False, indent=1)[:1800])
            print()
        print("--- oemNumbers[0:3] ---")
        for it in (a.get("oemNumbers") or [])[:3]:
            print(json.dumps(it, ensure_ascii=False)[:400])
            print()
        print("--- tradeNumbersDetails[0:2] ---")
        for it in (a.get("tradeNumbersDetails") or [])[:2]:
            print(json.dumps(it, ensure_ascii=False)[:400])
        break