"""Exportação dos resultados para CSV, Excel (XLSX/XLS) e TXT."""
from pathlib import Path
import csv

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import config

try:
    import xlwt
    _TEM_XLWT = True
except ImportError:
    _TEM_XLWT = False


def _linhas_planilha(resultados: list[dict]) -> list[list]:
    """Transforma resultados (dict com cross_refs) em linhas de dados."""
    linhas: list[list] = []
    for r in resultados:
        refs_texto = "; ".join(
            (f"{ref.get('marca_ref', '') or ''}/{ref.get('codigo_ref', '')}"
             if isinstance(ref, dict)
             else f"{ref[1] if len(ref) > 1 and ref[1] else ''}/"
                  f"{ref[0] if len(ref) > 0 else ''}")
            for ref in r.get("cross_refs", [])
        )
        linhas.append([
            r.get("codigo", ""),
            r.get("descricao", ""),
            r.get("marca", ""),
            r.get("gtin", ""),
            "\n".join(r.get("aplicacoes", [])),
            ", ".join(r.get("codigos_aplicacao", [])),
            r.get("fornecedor", ""),
            "Sim" if r.get("disponivel") else "Nao",
            r.get("observacao", ""),
            refs_texto,
        ])
    return linhas


_HEADERS = [
    "Codigo", "Descricao", "Marca", "GTIN", "Aplicacoes",
    "CodigosAplicacao", "Fornecedor",
    "Disponivel", "Observacao", "CrossRefs",
]


def exportar_csv(resultados: list[dict], caminho: str | Path | None = None) -> str:
    """Exporta para CSV. Retorna o caminho gerado."""
    caminho = caminho or config.EXPORT_DIR / "resultados.csv"
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    with open(caminho, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f, delimiter=";")
        writer.writerow(_HEADERS)
        writer.writerows(_linhas_planilha(resultados))
    return str(caminho)


def exportar_xlsx(resultados: list[dict], caminho: str | Path | None = None) -> str:
    """Exporta para XLSX com formatação básica. Retorna o caminho gerado."""
    caminho = caminho or config.EXPORT_DIR / "resultados.xlsx"
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Resultados"

    header_font = Font(bold=True, color="FFFFFF")
    header_fill = PatternFill("solid", fgColor="1F4E78")
    for c, nome in enumerate(_HEADERS, start=1):
        cell = ws.cell(row=1, column=c, value=nome)
        cell.font = header_font
        cell.fill = header_fill

    for i, linha in enumerate(_linhas_planilha(resultados), start=2):
        for c, valor in enumerate(linha, start=1):
            ws.cell(row=i, column=c, value=valor)

    # largura aproximada das colunas
    for c in range(1, len(_HEADERS) + 1):
        ws.column_dimensions[get_column_letter(c)].width = 28

    wb.save(caminho)
    return str(caminho)


def exportar_xls(resultados: list[dict], caminho: str | Path | None = None) -> str:
    """Exporta para XLS (Excel 97-2003). Retorna o caminho gerado."""
    if not _TEM_XLWT:
        raise RuntimeError(
            "xlwt não instalado. Rode: pip install xlwt"
        )
    caminho = caminho or config.EXPORT_DIR / "resultados.xls"
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)

    wb = xlwt.Workbook(encoding="utf-8")
    ws = wb.add_sheet("Resultados")

    fonte = xlwt.Font()
    fonte.bold = True
    fonte.colour_index = 9  # branco
    padrao = xlwt.Pattern()
    padrao.pattern = xlwt.Pattern.SOLID_PATTERN
    padrao.pattern_fore_colour = 0x17  # azul escuro aprox.
    estilo_cab = xlwt.easyxf("font: bold on", ) 
    estilo_cab.font = fonte
    estilo_cab.pattern = padrao

    for c, nome in enumerate(_HEADERS):
        ws.write(0, c, nome, estilo_cab)
    for i, linha in enumerate(_linhas_planilha(resultados), start=1):
        for c, valor in enumerate(linha):
            ws.write(i, c, str(valor))

    # largura aproximada das colunas
    for c in range(1, len(_HEADERS) + 1):
        ws.col(c).width = 256 * 28

    wb.save(str(caminho))
    return str(caminho)


def texto_ficha(r: dict) -> str:
    """Gera o texto de UMA peça no formato .txt (modelo do coisas.md)."""
    linhas = []
    codigo = str(r.get("codigo", "")).upper()
    marca = str(r.get("marca", "")).upper()
    gtin = str(r.get("gtin", "")).upper()
    descricao = str(r.get("descricao", "")).upper()

    cross_refs = r.get("cross_refs", [])
    codigos_extra = []
    for ref in cross_refs:
        if isinstance(ref, dict):
            codigos_extra.append(ref.get("codigo_ref", ""))
        elif ref:
            codigos_extra.append(ref[0] if len(ref) > 0 else "")
    vistos = set()
    codigos_unicos = []
    for c in codigos_extra:
        c_upper = c.upper()
        if c_upper and c_upper not in vistos:
            vistos.add(c_upper)
            codigos_unicos.append(c_upper)
    codigos_str = ",".join(codigos_unicos)
    if codigos_str:
        codigos_str += ";"

    aplicacoes = r.get("aplicacoes", [])
    aplicacoes_texto = (
        "\n".join(str(a).upper() for a in aplicacoes) if aplicacoes else "-"
    )

    linhas.append(f"{codigo}   {marca}")
    linhas.append("")
    if gtin:
        linhas.append(f"GTIN: {gtin}")
    linhas.append("")
    linhas.append("PRODUTO:")
    linhas.append(descricao)
    linhas.append("")
    linhas.append("INFORMAÇÕES TÉCNICAS:")
    linhas.append(f"CÓDIGOS: {codigos_str}")
    linhas.append(f"MARCA: {marca}")
    linhas.append("")
    linhas.append("APLICAÇÕES:")
    linhas.append(aplicacoes_texto)
    linhas.append("")
    linhas.append("")
    return "\n".join(linhas)


def exportar_txt_fichas(resultados: list[dict],
                        caminho: str | Path | None = None) -> str:
    """Exporta as fichas em texto (.txt), uma peça por bloco."""
    caminho = caminho or config.EXPORT_DIR / "fichas.txt"
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    texto = "\n".join(texto_ficha(r) for r in resultados)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)
    return str(caminho)
