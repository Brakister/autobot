"""Raspagem do RockAuto (https://www.rockauto.com) por número de peça.

Módulo "máquina" no mesmo formato do tecdoc.py: busca um número de peça,
parseia os resultados e devolve dicts no formato que a GUI (revisão/salvar)
entende. Também expõe `url_partsearch()` para o link "Ver em RockAuto" que
aparece no painel individual da revisão.

Uso na GUI (mesmo papel do tecdoc.executar_busca):
    resultados = rockauto.executar_busca(codigos)      # list[dict]
    link = rockauto.url_partsearch("095510-33040")     # link profundo

Uso direto (CLI):
    python rockauto.py          # roda build_retorno com tabelas.csv
"""
from __future__ import annotations

import csv
import re
import time
import urllib.parse
from pathlib import Path

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


class RockAutoAPI:
    """Automação da busca de peças no RockAuto."""

    base = "https://www.rockauto.com"

    def __init__(self, headless: bool = False, on_mensagem=None):
        self.headless = headless
        self._msg_cb = on_mensagem
        self.playwright = None
        self.browser = None
        self.context = None
        self.page = None

    def _msg(self, texto: str) -> None:
        if self._msg_cb:
            try:
                self._msg_cb(texto)
            except Exception:
                pass
        else:
            print(f"[rockauto] {texto}")

    def open_browser(self):
        if self.page:
            return self.page
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=self.headless)
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        return self.page

    # -----------------------------
    # 🔎 BUSCA PRINCIPAL
    # -----------------------------
    def search_part(self, part_number, timeout_s: int = 60):
        """Abre a busca do número no RockAuto e devolve o HTML dos resultados.

        A página `partsearch/?partnum=...` apenas pré-preenche o campo — é
        preciso clicar no botão "Search" para a página redirecionar para a
        listagem (https://www.rockauto.com/en/parts/...). Se não houver
        resultado, a página fica na partsearch e o HTML carrega o nó
        `"nodetype":"no_parts_found"`.

        Se o site pedir captcha, avisa (log/mensagem) e espera o usuário
        resolver no navegador — em vez de `input()`, que travava a GUI.
        """
        page = self.open_browser()
        search_url = url_partsearch(part_number)
        page.goto(search_url, wait_until="domcontentloaded")

        if "captcha" in page.url.lower():
            self._msg(f"Resolva o captcha no navegador para: {part_number}")
            inicio = time.time()
            while "captcha" in page.url.lower():
                if time.time() - inicio > timeout_s:
                    self._msg(f"Tempo esgotado esperando o captcha de {part_number}.")
                    return ""
                page.wait_for_timeout(1000)
            page.goto(search_url, wait_until="domcontentloaded")

        # Garante o número no campo e clica no Search da partsearch
        # (o form tem `dopartsearch=1`)
        try:
            num_input = page.query_selector(
                "input[name='partsearch[partnum][partsearch_007]']"
            )
            if num_input:
                num_input.fill(str(part_number))
            search_btn = page.query_selector(
                "input[name='partsearch[do][partsearch_007]']"
            )
            if search_btn and search_btn.is_visible():
                search_btn.click()
        except Exception as e:
            self._msg(f"Não consegui clicar em Search do RockAuto: {e}")

        # Espera o resultado: ou a listagem de peças carrega, ou o RockAuto
        # marca "no_parts_found".
        inicio = time.time()
        while time.time() - inicio < timeout_s:
            html = page.content()
            if "listing-final-partnumber" in html:
                break
            if '"nodetype":"no_parts_found"' in html:
                break
            page.wait_for_timeout(1000)

        return page.content()

    # -----------------------------
    # 🔬 EXTRAI RESULTADOS
    # -----------------------------
    def parse_search(self, data):
        results = []

        if not data:
            return results

        if '"nodetype":"no_parts_found"' in data:
            return results

        soup = BeautifulSoup(data, "html.parser")

        # Cada produto da listagem do RockAuto é um <tr> com
        # td.listing-border-top-line (marca, número, categoria, Info, preço)
        # e um span oculto com os números alternativos/OE.
        rows = soup.select("tr:has(td.listing-border-top-line)")

        for row in rows:
            td = row.select_one("td.listing-border-top-line")
            if not td:
                continue

            mfr_el = td.select_one("span.listing-final-manufacturer")
            num_el = td.select_one("span.listing-final-partnumber")
            info_a = td.select_one("a.ra-btn-moreinfo")
            cat_el = td.select_one("span.listing-footnote-text")
            xref_el = td.select_one(
                'span[title*="Alternate"], span[title*="Part Numbers"]'
            )

            name = num_el.get_text(" ", strip=True) if num_el else ""
            brand = mfr_el.get_text(" ", strip=True) if mfr_el else ""
            category = cat_el.get_text(" ", strip=True) if cat_el else ""
            category = re.sub(r"^Category:\s*", "", category).strip()

            info_target = ""
            if info_a:
                href = info_a.get("href", "")
                parsed = urllib.parse.urlparse(href)
                query = urllib.parse.parse_qs(parsed.query)
                info_target = query.get("pk", [href])[0]

            # preço — primeiro R$ ou $ da linha (dropdown "Choose")
            price_match = re.search(r"(?:R\$|\$)\s*[\d.,]+", td.get_text(" ", strip=True))
            price = price_match.group(0) if price_match else ""

            cross_refs: list[str] = []
            if xref_el:
                xrefs_text = xref_el.get_text(" ", strip=True)
                cross_refs = [
                    p.strip() for p in xrefs_text.split(",") if p.strip()
                ]

            if not name and not brand:
                continue

            results.append({
                "pk": info_target,
                "name": name,
                "brand": brand,
                "price": price,
                "category": category,
                "cross_refs": cross_refs,
                "raw": {
                    "info_href": info_a.get("href", "") if info_a else "",
                    "info_target": info_target,
                    "text": td.get_text(" ", strip=True)[:400],
                }
            })

        # o RockAuto às vezes duplica a mesma listagem no HTML (paginação/nav);
        # mantém só a primeira ocorrência de cada peça (pk igual)
        vistos: set = set()
        unicos = []
        for item in results:
            chave = item["pk"] or f"{item['brand']}|{item['name']}"
            if chave in vistos:
                continue
            vistos.add(chave)
            unicos.append(item)

        return unicos

    # -----------------------------
    # 📄 DETALHES (INFO MODAL) — opcional
    # -----------------------------
    def get_more_info(self, pk, cc="0", pt="0"):
        page = self.open_browser()
        if not pk:
            return ""

        if "moreinfo.php" in pk:
            url = urllib.parse.urljoin(self.base, pk)
        else:
            url = f"{self.base}/en/moreinfo.php?pk={pk}&cc={cc}&pt={pt}"

        page.goto(url, wait_until="domcontentloaded")
        return page.content()

    def parse_more_info(self, html):
        soup = BeautifulSoup(html, "html.parser")

        data = {
            "details": [],
            "applications": []
        }

        for row in soup.select("table tr"):
            cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]

            if len(cols) >= 3 and any(col.isdigit() for col in cols[-1].replace("-", " ").split()):
                app = {
                    "make": cols[0],
                    "model": cols[1] if len(cols) > 1 else "",
                    "years": cols[2] if len(cols) > 2 else "",
                }
                if len(cols) > 3:
                    app["notes"] = " | ".join(cols[3:])

                data["applications"].append(app)
                continue

            if len(cols) >= 2:
                data["details"].append({
                    "key": cols[0],
                    "value": cols[1]
                })

        if not data["applications"]:
            for li in soup.select("ul li"):
                txt = li.get_text(" ", strip=True)
                if txt:
                    data["applications"].append({"text": txt})

        return data

    # -----------------------------
    # 🔄 BUSCA COMPLETA
    # -----------------------------
    def full_lookup(self, part_number, with_details=False):
        raw = self.search_part(part_number)

        parsed = self.parse_search(raw)

        if not with_details:
            return parsed

        # enriquece com moreinfo
        for item in parsed:
            if item["pk"]:
                try:
                    html = self.get_more_info(item["pk"])
                    extra = self.parse_more_info(html)
                    item["extra"] = extra

                    time.sleep(0.5)  # evita bloqueio
                except Exception as e:
                    item["extra_error"] = str(e)

        return parsed

    def open_part_search(self, part_number):
        url = url_partsearch(part_number)
        page = self.open_browser()
        page.goto(url, wait_until="domcontentloaded")
        return url

    def close(self):
        try:
            if self.browser:
                self.browser.close()
        except Exception:
            pass
        try:
            if self.playwright:
                self.playwright.stop()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Formato de resultado usado pelo app (mesmo do PecaResultado do tecdoc)
# ---------------------------------------------------------------------------

def _resultado_vazio(part_number: str, observacao: str = "") -> dict:
    return {
        "codigo": part_number,
        "descricao": "",
        "marca": "",
        "gtin": "",
        "aplicacoes": [],
        "codigos_aplicacao": [],
        "fornecedor": "RockAuto",
        "disponivel": False,
        "url": url_partsearch(part_number),
        "observacao": observacao,
        "cross_refs": [],
    }


def url_partsearch(part_number) -> str:
    """Link profundo da busca do número de peça (usado no 'Ver em RockAuto')."""
    return f"{RockAutoAPI.base}/en/partsearch/?partnum=" \
           f"{urllib.parse.quote(str(part_number or '').strip())}"


def buscar_um(part_number: str, api: RockAutoAPI | None = None,
              on_mensagem=None) -> dict:
    """Busca UM código no RockAuto e devolve o melhor candidato (dict do app).

    Usa o primeiro resultado da busca (mesma regra do build_retorno). Se não
    houver resultado, devolve o dict vazio com observacao explicando.
    """
    fechar = api is None
    if api is None:
        api = RockAutoAPI(on_mensagem=on_mensagem)
    try:
        raw = api.search_part(part_number)
        candidatos = api.parse_search(raw)
        if not candidatos:
            return _resultado_vazio(
                part_number, observacao="Nenhum resultado no RockAuto")

        primeiro = candidatos[0]
        nome = str(primeiro.get("name", "") or "").strip()
        marca = str(primeiro.get("brand", "") or "").strip()
        if not marca and nome:
            marca = nome.split(" ", 1)[0] if " " in nome else nome
        cross_refs = primeiro.get("cross_refs") or []
        # o app espera refs como dicts {codigo_ref, marca_ref} ou tuplas
        # (codigo, marca) — normaliza as strings do RockAuto para esse formato
        refs_ok: list = []
        for ref in cross_refs:
            if isinstance(ref, dict):
                refs_ok.append(ref)
            elif isinstance(ref, (tuple, list)) and len(ref) >= 1:
                refs_ok.append(
                    (str(ref[0]), str(ref[1]) if len(ref) > 1 and ref[1] else None)
                )
            elif ref:
                refs_ok.append({"codigo_ref": str(ref), "marca_ref": None})

        return {
            "codigo": part_number,
            "descricao": nome,
            "marca": marca,
            "gtin": "",
            "aplicacoes": [],
            "codigos_aplicacao": [],
            "fornecedor": "RockAuto",
            "disponivel": True,
            "url": url_partsearch(part_number),
            "observacao": str(primeiro.get("category", "") or "").strip(),
            "cross_refs": refs_ok,
        }
    finally:
        if fechar:
            try:
                api.close()
            except Exception:
                pass


def executar_busca(
    codigos: list[str | dict[str, str]],
    headless: bool = False,
    on_progress: callable | None = None,
    on_mensagem: callable | None = None,
    on_pausa: callable | None = None,
    on_resultado: callable | None = None,
) -> list[dict]:
    """Busca vários códigos no RockAuto (mesmo papel do tecdoc.executar_busca).

    `codigos` pode ser uma lista de strings ou de dicts {"codigo": ...,
    "marca": ...}. Devolve list[dict] no formato do app (revisão/salvar).
    """
    api = RockAutoAPI(headless=headless, on_mensagem=on_mensagem)
    total = len(codigos)
    resultados: list[dict] = []
    try:
        for i, item in enumerate(codigos, start=1):
            if on_pausa:
                on_pausa()
            if isinstance(item, dict):
                codigo = str(item.get("codigo", "")).strip()
                marca_item = str(item.get("marca", "")).strip()
            else:
                codigo = str(item).strip()
                marca_item = ""
            if on_progress:
                on_progress(i, total, codigo)
            if not codigo:
                continue
            res = buscar_um(codigo, api=api, on_mensagem=on_mensagem)
            if marca_item and not res["marca"]:
                res["marca"] = marca_item
            resultados.append(res)
            if on_resultado:
                try:
                    on_resultado(res)
                except Exception:
                    pass
            if i < total:
                time.sleep(1.0)  # ritmo humano, evita bloqueio
    finally:
        api.close()
    return resultados


# ---------------------------------------------------------------------------
# Pipeline antigo (CSV → CSV) mantido por compatibilidade
# ---------------------------------------------------------------------------

def load_partnumbers_without_col2(csv_path, limit=10):
    rows = []

    with open(csv_path, newline="", encoding="utf-8-sig") as csv_file:
        reader = csv.reader(csv_file, delimiter=";")

        for index, row in enumerate(reader):
            if index == 0:
                continue

            if len(row) < 3:
                continue

            chassis = row[0].strip()
            vehicle = row[1].strip()
            partnumber = row[2].strip()

            if not partnumber or vehicle:
                continue

            normalized_row = [chassis, vehicle, partnumber]
            while len(normalized_row) < 7:
                normalized_row.append("")

            rows.append(normalized_row)

            if len(rows) >= limit:
                break

    return rows


def write_results_csv(output_path, rows):
    header = ["Chassi:", "Veiculo:", "Partnumber dos itens:", "", "", "", ""]

    with open(output_path, "w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.writer(csv_file, delimiter=";")
        writer.writerow(header)
        writer.writerows(rows)


def build_retorno(input_csv="tabelas.csv", output_csv="retorno.csv", limit=10):
    rows = load_partnumbers_without_col2(input_csv, limit=limit)

    api = RockAutoAPI()

    output_rows = []

    for row in rows:
        chassi, vehicle, partnumber = row[:3]

        print(f"🔎 Buscando: {partnumber}")

        try:
            results = api.full_lookup(partnumber, with_details=False)

            if results:
                # pega o primeiro resultado (ou pode iterar todos)
                first = results[0]

                vehicle_info = first.get("name", "")
                brand = first.get("brand", "")
                category = first.get("category", "")

                output_rows.append([
                    chassi,
                    f"{brand} {vehicle_info} ({category})",
                    partnumber,
                    "",
                    "",
                    "",
                    ""
                ])
            else:
                output_rows.append(row)

        except Exception as e:
            print(f"Erro em {partnumber}: {e}")
            output_rows.append(row)

    api.close()

    write_results_csv(output_csv, output_rows)


if __name__ == "__main__":
    base_dir = Path(__file__).resolve().parent
    build_retorno(
        input_csv=base_dir / "tabelas.csv",
        output_csv=base_dir / "retorno.csv",
        limit=100,
    )