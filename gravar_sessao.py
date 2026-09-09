# -*- coding: utf-8 -*-
"""Gravador de sessao manual no TecDoc.

Abre o TecDoc ja logado (usa a sessao salva) e registra TUDO o que voce fizer:
  - video em data/grava_sessao/video/
  - cada clique (elemento, classe, ta-name, text) em cliques.json
  - mudancas de URL em urls.txt
  - chamadas /rest/* (API) em requests.jsonl
  - DOM final + screenshot no fim

Use para mostrar o fluxo manual (buscar codigo, abrir filtro de marcas,
digitar a marca, esperar, clicar no resultado). Quando terminar, volte aqui
e pressione ENTER.
"""
import json
import pathlib
import time

import config
import tecdoc
from playwright.sync_api import sync_playwright

SAIDA = pathlib.Path("data/grava_sessao")
LOGS_URLS = SAIDA / "urls.txt"
LOGS_REQ = SAIDA / "requests.jsonl"
LOGS_CLICKS = SAIDA / "cliques.jsonl"

JS_CLICKS = """if (window.__clicsJ) return; window.__clicsJ = true;
window.__clics = [];
document.addEventListener('click', function(ev){
  var info = {t: Date.now(), tag: (ev.target.tagName||'').toLowerCase(), ta:'', cls:'', txt:'', html:'', path:[]};
  var el = ev.target, n = 0;
  while (el && n < 14){
    if (el.getAttribute) { var t = el.getAttribute('ta-name'); if (t) info.ta = t; }
    try { var c = el.className; if (c && typeof c === 'string') info.cls = c.split(/\\s+/).slice(0,3).join(' '); } catch(e){}
    info.path.push((el.tagName||'').toLowerCase() + (el.id ? '#'+el.id : ''));
    el = el.parentElement; n++;
  }
  info.path = info.path.join(' > ');
  try { info.txt = (ev.target.innerText || '').trim().slice(0, 80); } catch(e){}
  try { info.html = (ev.target.outerHTML || '').slice(0, 1200); } catch(e){}
  window.__clics.push(info);
}, true);"""


def main() -> None:
    SAIDA.mkdir(parents=True, exist_ok=True)
    for arq in (LOGS_CLICKS, LOGS_REQ):
        if arq.exists():
            arq.unlink()

    LOGS_URLS.write_text("", encoding="utf-8")

    pw = sync_playwright().start()
    browser = pw.chromium.launch(headless=False, slow_mo=180)
    context = browser.new_context(
        storage_state=str(config.SESSION_FILE) if config.SESSION_FILE.exists() else None,
        record_video_dir=str(SAIDA / "video"),
        viewport={"width": 1500, "height": 950},
    )
    page = context.new_page()
    page.set_default_timeout(20_000)
    page.add_init_script(JS_CLICKS)

    aut = tecdoc.TecDocAutomator("", "", headless=False)
    aut._pw, aut._context, aut._page = pw, context, page
    aut._restaurar_sessionstorage()

    def on_nav(frame):
        try:
            if frame == page.main_frame:
                with open(LOGS_URLS, "a", encoding="utf-8") as f:
                    f.write(f"{time.strftime('%H:%M:%S')}  {frame.url}\n")
        except Exception:
            pass

    visto = [0]

    def on_resp(resp):
        # despeja os cliques capturados (main thread é seguro p/ Playwright)
        try:
            rec = page.evaluate("() => window.__clics || []")
            if len(rec) > visto[0]:
                with open(LOGS_CLICKS, "a", encoding="utf-8") as f:
                    for c in rec[visto[0]:]:
                        f.write(json.dumps(c, ensure_ascii=False) + "\n")
                visto[0] = len(rec)
        except Exception:
            pass
        if "/rest/" in resp.url or "brands" in resp.url.lower() or resp.url.endswith(".json"):
            try:
                corpo = ""
                if "json" in (resp.headers.get("content-type", "") or ""):
                    try:
                        corpo = json.dumps(resp.json(), ensure_ascii=False)[:200_000]
                    except Exception:
                        corpo = resp.text()[:200_000] if resp.url.endswith(".json") else ""
                with open(LOGS_REQ, "a", encoding="utf-8") as f:
                    f.write(json.dumps({
                        "t": time.strftime("%H:%M:%S"),
                        "status": resp.status,
                        "method": resp.request.method,
                        "url": resp.url,
                        "ct": resp.headers.get("content-type", ""),
                        "corpo": corpo,
                    }, ensure_ascii=False) + "\n")
            except Exception:
                pass

    def on_req(req):
        # registra TODAS as chamadas (até as respondidas de cache, p/ achar a API)
        if "tecalliance" in req.url:
            with open(LOGS_REQ, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "t": time.strftime("%H:%M:%S"),
                    "req": True,
                    "method": req.method,
                    "url": req.url,
                }, ensure_ascii=False) + "\n")

    page.on("framenavigated", on_nav)
    page.on("response", on_resp)
    page.on("request", on_req)

    page.goto(config.TECDOC_URL, wait_until="domcontentloaded")
    try:
        page.wait_for_load_state("networkidle", timeout=25_000)
    except Exception:
        pass

    print("\nBrowser aberto e logado. Agora faca o fluxo NORMAL:")
    print("  1. busque o codigo da peca")
    print("  2. abra o filtro de marcas, digite a marca, espere e selecione")
    print("  3. clique no resultado e veja a pagina do artigo")
    input("\nQuando terminar, volte aqui e pressione ENTER...")

    try:
        page.screenshot(path=str(SAIDA / "fim.png"), full_page=True)
    except Exception:
        pass
    try:
        (SAIDA / "dom_fim.html").write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    (SAIDA / "url_final.txt").write_text(page.url, encoding="utf-8")

    try:
        context.close()
    except Exception:
        pass
    try:
        pw.stop()
    except Exception:
        pass

    vids = sorted((SAIDA / "video").glob("*.webm")) if (SAIDA / "video").exists() else []
    print("\nGravacao concluida:")
    print("  * cliques:  ", LOGS_CLICKS.relative_to("."))
    print("  * urls:     ", LOGS_URLS.relative_to("."))
    print("  * requests: ", LOGS_REQ.relative_to("."))
    print("  * dom_fim:  ", (SAIDA / "dom_fim.html").relative_to("."))
    print("  * video:", *[v.relative_to(".") for v in vids[-2:]], sep="\n      ")
    print(f"\nURL final: {page.url}")


if __name__ == "__main__":
    main()