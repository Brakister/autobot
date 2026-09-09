"""Exportação dos resultados para CSV e Excel (XLSX)."""
from pathlib import Path
import csv

import openpyxl
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter

import config


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
            ", ".join(r.get("cilindradas", [])),
            "\n".join(r.get("aplicacoes", [])),
            ", ".join(r.get("codigos_aplicacao", [])),
            r.get("fornecedor", ""),
            "Sim" if r.get("disponivel") else "Nao",
            r.get("observacao", ""),
            refs_texto,
        ])
    return linhas


_HEADERS = [
    "Codigo", "Descricao", "Marca", "GTIN", "Cilindradas", "Aplicacoes",
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
