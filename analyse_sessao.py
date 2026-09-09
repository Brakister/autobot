"""Analisa sessao_reqresp.jsonl: separa pedidos que resolvem veículos."""
import json, re
from pathlib import Path

LOG = Path("data/diagnostico/sessao_reqresp.jsonl")

esq_ids = set()
for line in open(Path("data/diagnostico/resp_link4.jsonl"), encoding="utf-8"):
    try:
        d = json.loads(line)
    except Exception:
        continue
    for it in (d.get("body", {}).get("data", {}).get("array", []) or []):
        for lk in (it.get("articleLinkages", {}).get("array", []) or []):
            esq_ids.add(lk.get("linkingTargetId"))

print("linkingTargetId distintos:", len(esq_ids))

dados = []
for line in open(LOG, encoding="utf-8"):
    dados.append(json.loads(line))

print("\n== pedidos cuja resposta TEM nomes de veículo/carro ==")
for d in dados:
    resp = json.dumps(d.get("resp", {}))
    if re.search(r'(vehicle|carType|carName|passenger|ktype|linkingTargetId)', resp, re.I):
        pedido = d.get("pedido", "")[:200]
        print("-" * 60)
        print("PEDIDO:", pedido)
        resp_obj = d.get("resp", {})
        s = json.dumps(resp_obj, ensure_ascii=False)
        print("RESP:", s[:350])

print("\n== pedidos que referenciam os linkingTargetId ==")
for d in dados:
    ped = d.get("pedido", "")
    hits = [str(i) for i in esq_ids if str(i) in ped]
    if hits:
        print("-" * 60)
        print("IDs:", hits[:8], "| PEDIDO:", ped[:250])

print("\n== métodos únicos (chave raiz do JSON-RPC) ==")
met = {}
for d in dados:
    ped = d.get("pedido", "")
    try:
        obj = json.loads(ped)
        m = next(iter(obj))
        args = str(obj.get(m, {}))[:80]
        met.setdefault(m, []).append(args)
    except Exception:
        pass
for m, args in sorted(met.items()):
    print(f"  {m}  ex={args[0]}")