"""Diagnóstico do TecDoc — busca REAL para descobrir seletores e campos.

Reutiliza a automação do tecdoc.py (sessão salva + login automático/Manual MFA)
e faz 1 busca real com um código de peça, gravando em data/diagnostico/:

  - captura_api_TIMESTAMP.jsonl   todas as trocas com a API /rest/*
  - dom_resultados.html           HTML da tabela de resultados (AG-Grid)
  - texto_visivel.txt             texto visível da página de resultados
  - filtros_marca.json            filtros de marca nativos do site
  - dom_detalhe.html              página de DETALHE (após clicar no 1º resultado)
  - col_ids_detalhe.json          col-id da AG-Grid do detalhe
  - dom_referencias.html          aba de referências cruzadas (se existir)
  - scan_disponibilidade.json     campos de disponibilidade vistos nos JSONs

Depois da busca, o script CLICA no primeiro resultado e aguarda carregar a
página de detalhe (é nela que ficam os dados/cross-references).

Uso:
    python diagnostico.py           (pergunta login/senha/código)
    python diagnostico.py <codigo>  (usa o código passado)
"""
from __future__ import annotations

import getpass
import json
import sys
from collections import Counter
from pathlib import Path
import config
import tecdoc


def main() -> None:
    codigo = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
    login = input("Usuário TecDoc (Enter = usar salvo): ").strip()
    if not login:
        login = config.get_config("tecdoc_usuario") or ""
    senha = getpass.getpass("Senha (não será salva): ")
    if not codigo:
        codigo = input("Código de peça para testar (Enter = '0460907501'): ").strip()
    codigo = codigo or "0460907501"

    pasta = config.data_dir() / "diagnostico"
    pasta.mkdir(parents=True, exist_ok=True)

    aut = tecdoc.TecDocAutomator(
        login, senha, headless=False, capturar_api=True,
        on_mensagem=lambda m: print(f"  [{m.splitlines()[0]}]"),
    )
    try:
        aut.iniciar()
        aut.garantir_login()

        _foto(aut._page, pasta, "01_apos_login")
        print("\nTexto visível na tela após login:")
        print(_texto_visivel(aut._page)[:800])

        print(f"\n=== Buscando '{codigo}' ===")
        aut._preencher_busca(codigo)
        _aguardar_resultados(aut._page)

        _foto(aut._page, pasta, "02_apos_busca")
        aut._page.wait_for_timeout(3500)
        _foto(aut._page, pasta, "03_apos_busca_espera")

        url = aut._page.url
        print("URL atual:", url)

        # ---- dump do DOM da área de resultados ----
        _dump_resultados(aut._page, pasta)
        print("\nTexto visível após busca (início):")
        print(_texto_visivel(aut._page)[:1200])
        _aviso_resultado_vazio(aut._page)
        # página inteira (o filtro de marcas fica FORA da grid)
        (pasta / "pagina_busca.html").write_text(
            aut._page.content(), encoding="utf-8")
        print("  página inteira salva: pagina_busca.html")
        _picar_filtros(aut._page, pasta)
        _abrir_filtro_marcas(aut._page, pasta)

        print("\n=== Clicando no primeiro resultado (abre o detalhe) ===")
        _explorar_detalhe(aut._page, pasta)

        # ---- varredura: campos de disponibilidade vistos na API ----
        scan = _scan_disponibilidade(pasta)
        archivo = pasta / "scan_disponibilidade.json"
        archivo.write_text(json.dumps(scan, ensure_ascii=False, indent=2),
                           encoding="utf-8")
        _imprimir_scan(scan)

        resumo = {
            "codigo": codigo,
            "url_final": url,
            "scan_disponibilidade": _arq_scan(pasta),
        }
        print("\nArquivos gerados em:", pasta)
    finally:
        aut.encerrar()


def _foto(page, pasta: Path, nome: str) -> None:
    try:
        caminho = pasta / f"{nome}.png"
        page.screenshot(path=str(caminho))
        print("  screenshot:", caminho.name)
    except Exception as exc:
        print("  screenshot falhou:", exc)


def _texto_visivel(page) -> str:
    try:
        return page.evaluate("() => document.body.innerText") or ""
    except Exception:
        return ""


def _aviso_resultado_vazio(page) -> None:
    try:
        txt = _texto_visivel(page).lower()
    except Exception:
        return
    for termo in ("nenhum resultado", "no result", "nachen", "0 result",
                  "sem resultado", "não encontrado", "nao encontrado"):
        if termo in txt:
            print(f"\n[!] Página mostra: '{termo}' — provável busca sem resultado.")
            return
    print("\n[ok] Nenhum aviso de 'sem resultado' encontrado no texto visível.")


def _aguardar_resultados(page) -> None:
    """Espera aparecer uma tabela/lista de resultados na página."""
    import time
    inicio = time.time()
    while time.time() - inicio < 15:
        if page.locator(tecdoc.SELETORES["resultado"]["lista"]).count() > 0:
            try:
                page.wait_for_load_state("networkidle", timeout=5_000)
            except Exception:
                pass
            break
        time.sleep(1)


def _picar_filtros(page, pasta) -> None:
    """Procura o filtro de marcas (dropdown/autocomplete) e descreve-o."""
    import time as _t
    info: dict = {}

    def descrever_el(el, nome: str) -> dict:
        d = {"tag": el.evaluate("e => e.tagName.toLowerCase()"),
             "texto": (el.inner_text().replace("\n", " ") or "")[:80]}
        for attr in ("name", "id", "type", "placeholder", "aria-label",
                     "class", "role"):
            try:
                v = el.get_attribute(attr)
                if v:
                    d[attr.split("-")[-1]] = v[:80]
            except Exception:
                pass
        return d

    # 1) inputs visíveis (o filtro de marca costuma ser um autocomplete=texto)
    inputs = []
    try:
        for i, el in enumerate(page.locator("input, .p-autocomplete input").all()):
            if not el.is_visible():
                continue
            inputs.append(descrever_el(el, f"input[{i}]"))
    except Exception:
        pass
    if inputs:
        info["inputs_visiveis"] = inputs
        print("\n  Inputs visíveis na página de busca:")
        for inp in inputs:
            print(f"    {inp}")

    # 2) dropdowns/multiselect candidatos (PrimeNG, TA, Angular Material)
    cands = (
        "p-dropdown, p-multiselect, .p-dropdown, .p-multiselect, "
        "[role='combobox'], [role='listbox'], ta-dropdown"
    )
    tries = 0
    for el in page.locator(cands).all():
        if not el.is_visible() or tries >= 6:
            continue
        tries += 1
        try:
            txt = (el.inner_text().replace("\n", " ") or "").strip()[:40]
        except Exception:
            txt = ""
        try:
            el.click()
            _t.sleep(0.5)
            opts = [
                o.strip() for o in
                page.locator(".p-dropdown-item, .p-multiselect-item, "
                             "p-dropdownitem li, [role='option']").all_text_contents()
                if o.strip()
            ][:40]
            page.keyboard.press("Escape")
            _t.sleep(0.3)
            info[f"dropdown[{tries}]"] = {"trigger": txt,
                                          "opcoes": list(dict.fromkeys(opts))}
            print(f"    dropdown[{tries}] trigger={txt!r} opcoes={opts[:8]}")
        except Exception:
            continue

    # 3) elementos cujo rótulo contém 'Marca' (procura o seletor de marcas)
    try:
        rotulos = page.locator("*:has-text('Marca'):visible").all()[:8]
        achados = []
        for r in rotulos:
            tag = r.evaluate("e => e.tagName.toLowerCase()")
            txt = (r.inner_text().replace("\n", " ") or "").strip()[:60]
            if tag in ("a", "span", "div", "label", "p-dropdown-label",
                       "p-multiselect-label") and len(txt) <= 40:
                achados.append(f"<{tag}> {txt!r}")
        if achados:
            info["rotulos_marca"] = achados
            print("  Rótulos 'Marca':", achados[:6])
    except Exception:
        pass

    (pasta / "filtros_marca.json").write_text(
        json.dumps(info, ensure_ascii=False, indent=2), encoding="utf-8")


def _abrir_filtro_marcas(page, pasta) -> None:
    """Abre o seletor de marcas do site e despeja o DOM do painel aberto.

    O filtro de marcas é um PrimeNG p-multiselect dentro de um SIDEBAR
    (div#pn_id_89_list + p-scroller). Precisamos ver esse DOM com o painel
    aberto para achar o campo onde se digita o nome da marca.
    """
    print("\n=== Abrindo o filtro de marcas (site) ===")
    sel = tecdoc.SELETORES["filtros"]["marca_selector"]
    try:
        loc = page.locator(sel)
        print("  trigger count:", loc.count())
        if loc.count() == 0:
            return
        loc.first.click()
        page.wait_for_timeout(1200)
    except Exception as exc:
        print("  click falhou:", exc)
        return

    html = []
    for s in ("[ta-name='brand-selector'] div[id^='pn_id_']",
              "div[id^='pn_id_'] [role='option']",
              "ul[id^='pn_id_']",
              ".p-multiselect-panel",
              "[role='listbox']"):
        try:
            l2 = page.locator(s)
            if l2.count() > 0:
                html.append(f"<!-- SELEC: {s}  ({l2.count()}) -->\n"
                            + l2.first.evaluate("e => e.outerHTML"))
        except Exception:
            pass
    (pasta / "filtro_aberto.html").write_text(
        "\n\n".join(html), encoding="utf-8")
    print("  filtro_aberto.html salvo")

    # inputs visíveis (prioriza dentro do brand-selector)
    infos = []
    for base in ("[ta-name='brand-selector'] input", "input"):
        try:
            locs = page.locator(base)
            for i in range(locs.count()):
                try:
                    inp = locs.nth(i)
                    if not inp.is_visible():
                        continue
                    info = inp.evaluate(
                        "e => ({sel:'" + base.replace("'", "\\'") +
                        "', idx:" + str(i) + ", id:e.id, cls:e.className, "
                        "type:e.type, ph:e.placeholder||'', "
                        "ta:e.getAttribute('ta-name')||'', "
                        "name:e.name||'', "
                        "aria:e.getAttribute('aria-label')||''})"
                    )
                    infos.append(info)
                except Exception:
                    continue
        except Exception:
            continue
    (pasta / "inputs_filtro_aberto.json").write_text(
        json.dumps(infos, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  inputs visiveis:", len(infos))

    try:
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
    except Exception:
        pass


def _explorar_detalhe(page, pasta) -> None:
    """Clica no primeiro resultado e captura a página de detalhe do artigo."""
    import time
    linhas = page.locator(tecdoc.SELETORES["resultado"]["linha"])
    if linhas.count() == 0:
        print("  Nenhuma linha de resultado para clicar.")
        return
    primeiro = linhas.first
    try:
        primeiro.scroll_into_view_if_needed()
        primeiro.click()
    except Exception as exc:
        print("  Clique falhou:", exc)
        return
    time.sleep(6)  # deixa a página de detalhe carregar
    try:
        page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass

    print("  URL após clique:", page.url)

    # ---- detecta 404 / página de erro ----
    try:
        corpo = page.content()
    except Exception:
        corpo = ""
    url_low = page.url.lower()
    eh_erro = ("404" in url_low) or ("notfound" in url_low) or \
        ("error" in url_low) or ("não encontrad" in _texto_visivel(page).lower()) or \
        ("nao encontrad" in _texto_visivel(page).lower())
    if eh_erro:
        print("  [!] PÁGINA DE ERRO detectada (404 ou semelhante).")
        (pasta / "erro_404.html").write_text(corpo, encoding="utf-8")
        (pasta / "erro_404.txt").write_text(
            _texto_visivel(page)[:20_000], encoding="utf-8")
        print("      Salvo em: erro_404.html / erro_404.txt")

    _foto(page, pasta, "04_detalhe")
    try:
        html = page.content()
        (pasta / "dom_detalhe.html").write_text(html, encoding="utf-8")
        (pasta / "texto_detalhe.txt").write_text(
            _texto_visivel(page)[:60_000], encoding="utf-8")
        print("  Detalhe salvo: dom_detalhe.html / texto_detalhe.txt")
    except Exception as exc:
        print("  Falha ao salvar detalhe:", exc)

    cols_det = {}
    for cid in ("articleNo", "articleNumber", "description", "brand",
                "brandName", "stateText", "typeNumber", "oeNumbers",
                "articleLink", "cross", "refBrand", "refNumber"):
        n = len(page.locator(f"[col-id='{cid}']").all())
        if n:
            cols_det[cid] = n
    (pasta / "col_ids_detalhe.json").write_text(
        json.dumps(cols_det, ensure_ascii=False, indent=2), encoding="utf-8")
    print("  col-ids encontrados no detalhe:", cols_det or "nenhum")

    # tenta achar uma aba/entrada de referências cruzadas
    abas = page.locator(
        "ta-tab:has-text('Refer'), .mat-tab-label:has-text('Refer'), "
        "button:has-text('Refer'), a:has-text('Refer'), "
        "ta-tab:has-text('Cruzad'), .tab:has-text('Cruzad')"
    )
    if abas.count() > 0:
        try:
            abas.first.click()
            time.sleep(3)
            _foto(page, pasta, "05_aba_referencias")
            (pasta / "dom_referencias.html").write_text(
                page.content(), encoding="utf-8")
            (pasta / "texto_referencias.txt").write_text(
                _texto_visivel(page)[:80_000], encoding="utf-8")
            print("  Aba de referências salva: dom_referencias.html")
        except Exception as exc:
            print("  Falha ao abrir aba de referências:", exc)
    else:
        print("  (não achei aba de referências com esses seletores)")


def _dump_resultados(page, pasta) -> None:
    try:
        container = page.locator(tecdoc.SELETORES["resultado"]["lista"]).first
        if container.count() > 0:
            html = container.evaluate("el => el.outerHTML")
        else:
            html = page.content()
        (pasta / "dom_resultados.html").write_text(html, encoding="utf-8")
        (pasta / "texto_visivel.txt").write_text(
            _texto_visivel(page)[:60_000], encoding="utf-8")

        # cabeçalhos das tabelas (para achar a coluna de disponibilidade)
        cabecalhos = []
        for t in page.locator("table").all():
            ths = t.locator("th").all()
            cols = [th.inner_text().strip() for th in ths]
            if cols:
                cabecalhos.append(cols)
        (pasta / "cabecalhos_resultados.json").write_text(
            json.dumps(cabecalhos, ensure_ascii=False, indent=2),
            encoding="utf-8")

        # linhas da tabela de resultados
        linhas_visiveis = []
        try:
            linhas = container.locator(tecdoc.SELETORES["resultado"]["linha"])
            for i in range(min(linhas.count(), 10)):
                linhas_visiveis.append({
                    "texto": linhas.nth(i).inner_text(),
                    "html": linhas.nth(i).evaluate("el => el.outerHTML"),
                })
        except Exception:
            pass
        (pasta / "linhas_resultados.json").write_text(
            json.dumps(linhas_visiveis, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"DOM salvo ({len(html)} bytes), colunas: "
              f"{cabecalhos[0] if cabecalhos else 'sem <th>'}")
    except Exception as exc:
        print("Erro ao salvar DOM:", exc)


def _scan_disponibilidade(pasta) -> dict:
    """Conta chaves de disponibilidade/vendas presentes nas respostas /rest/*."""
    chaves = Counter()
    amostras: dict[str, str] = {}
    arquivos = sorted(pasta.glob("captura_api_*.jsonl")) + \
        sorted(config.data_dir().glob("captura/captura_*.jsonl"))
    chaves_quis = {
        "instock", "available", "availability", "availability_status",
        "stock", "state", "articlestate", "delivery", "leadtime",
        "lead_time", "deliverydate", "dataformats", "supplierdatasupplier",
    }
    for arq in arquivos:
        try:
            linhas = arq.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for linha in linhas:
            try:
                rec = json.loads(linha)
            except Exception:
                continue

            def anda(obj):
                if isinstance(obj, dict):
                    for k, v in obj.items():
                        if k.lower() in chaves_quis and not isinstance(v, (dict, list)):
                            chaves[k] += 1
                            if k not in amostras:
                                amostras[k] = str(v)
                        anda(v)
                elif isinstance(obj, list):
                    for it in obj:
                        anda(it)
            anda(rec)
    return {
        "chaves_vistas": dict(chaves),
        "amostras_de_valores": amostras,
        "arquivos": [str(a) for a in arquivos],
    }


def _arq_scan(pasta) -> str:
    return str(pasta / "scan_disponibilidade.json")


def _imprimir_scan(scan: dict) -> None:
    print("\n===== CAMPOS DE DISPONIBILIDADE VISTOS NA API =====")
    chaves = scan.get("chaves_vistas", {})
    if not chaves:
        print("Nenhuma chave de disponibilidade encontrada nos JSONs.")
        print("Conclusão provável: disponibilidade NÃO é exposta pela API.")
    else:
        for k, n in sorted(chaves.items(), key=lambda x: -x[1]):
            print(f"  {k}: {n}x   (ex.: {scan['amostras_de_valores'].get(k,'')!r})")
    print("====================================================")


if __name__ == "__main__":
    main()