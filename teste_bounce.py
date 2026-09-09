"""Teste isolado: ver se o TecDoc bounceia pra '/' sozinho (~2s pós-busca).

Fluxo: login (sessão salva), digita o código, Enter, e FICA PARADO monitorando
frame.navigated + URL a cada 1s por 20 segundos. Nenhuma leitura de grid, nada.

Se a página for pra 'https://web.tecalliance.net/' sozinha -> é o SITE.
Se ficar 20s parada na busca -> é ALGO DO NOSSO CÓDIGO (buscamos depois).

Uso: python teste_bounce.py [codigo]
"""
from __future__ import annotations

import os
import sys
import time

from playwright.sync_api import Page

from tecdoc import TecDocAutomator

CODIGO = (sys.argv[1] if len(sys.argv) > 1 else "LR164029")
USUARIO = os.environ.get("TECDOC_USER") or input("Usuário do TecDoc: ")
SENHA = os.environ.get("TECDOC_PASS")
if not SENHA:
    SENHA = input("Senha do TecDoc: ")


def log(texto: str) -> None:
    print(f"[{time.strftime('%H:%M:%S')}] {texto}", flush=True)


def monitora(page: Page, rotulo: str, segundos: int = 20) -> bool:
    """Observa; True se percebeu um bounce (id + url: url/ou catalog-not-found)."""
    bounceou = False
    inicio = time.time()
    ultima_url = page.url
    while time.time() - inicio < segundos:
        url = page.url
        if url.rstrip("/") == "https://web.tecalliance.net" or \
                "catalog-not-found" in url:
            log(f"  {rotulo}: BOUNCE -> {url}")
            bounceou = True
            break
        if url != ultima_url:
            log(f"  {rotulo}: url mudou -> {url[:120]}")
            ultima_url = url
        time.sleep(1)
    if not bounceou:
        log(f"  {rotulo}: 20s sem bounce (última url: {page.url[:120]})")
    return bounceou


def main() -> None:
    print("== teste_bounce ==", flush=True)
    auto = TecDocAutomator(USUARIO, SENHA,
                           headless=False, marcas=None, on_mensagem=log,
                           capturar_api=False)
    try:
        auto.iniciar()
        for tentativa in range(3):
            log(f"--- tentativa {tentativa + 1}: garantir_login ---")
            auto.garantir_login()
            page = auto._page

            # só espera a tela do catálogo estabilizar (sem ler grid)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except Exception:
                pass
            log(f"url inicial: {page.url}")

            # usa o mesmo mecanismo de busca do app (dispara de verdade)
            log(f"disparando busca de '{CODIGO}'...")
            auto._preencher_busca(CODIGO)
            page.wait_for_timeout(5000)  # deixa o SITE renderizar a grid sozinho
            log(f"url após busca: {page.url[:160]}")
            bounceou = monitora(page, "pós-busca", segundos=20)

            if not bounceou:
                log("NADA BOUNCEOU. O gatilho está no nosso código.")
                time.sleep(5)
                break
            log("Bounce confirmado no site. Tentando nova busca na sessão "
                "recém-autenticada (pra ver se ela também bounceia)...")
            time.sleep(3)
    finally:
        auto.encerrar()
        log("encerrado")


if __name__ == "__main__":
    main()