"""Modelo de dados de um resultado de peça (sem dependência do Playwright).
"""
from __future__ import annotations

from dataclasses import dataclass, field

@dataclass
class PecaResultado:
    codigo: str
    numero_artigo: str = ""
    descricao: str = ""
    marca: str = ""
    gtin: str = ""
    aplicacoes: list[str] = field(default_factory=list)
    codigos_aplicacao: list[str] = field(default_factory=list)
    fornecedor: str = ""
    disponivel: bool = False
    url: str = ""
    observacao: str = ""
    cross_refs: list[tuple[str, str | None]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "codigo": self.codigo,
            "numero_artigo": self.numero_artigo,
            "descricao": self.descricao,
            "marca": self.marca,
            "gtin": self.gtin,
            "aplicacoes": self.aplicacoes,
            "codigos_aplicacao": self.codigos_aplicacao,
            "fornecedor": self.fornecedor,
            "disponivel": self.disponivel,
            "url": self.url,
            "observacao": self.observacao,
            "cross_refs": self.cross_refs,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "PecaResultado":
        """Reconstrói um resultado a partir de um dict salvo (ex.: cache)."""
        r = cls(codigo=str(d.get("codigo", "")))
        r.numero_artigo = str(d.get("numero_artigo", "") or "")
        r.descricao = str(d.get("descricao", "") or "")
        r.marca = str(d.get("marca", "") or "")
        r.gtin = str(d.get("gtin", "") or "")
        r.aplicacoes = list(d.get("aplicacoes", []) or [])
        r.codigos_aplicacao = list(d.get("codigos_aplicacao", []) or [])
        r.fornecedor = str(d.get("fornecedor", "") or "")
        r.disponivel = bool(d.get("disponivel", False))
        r.url = str(d.get("url", "") or "")
        r.observacao = str(d.get("observacao", "") or "")
        refs = []
        for ref in d.get("cross_refs", []) or []:
            if isinstance(ref, (list, tuple)) and len(ref) >= 1:
                marca = ref[1] if len(ref) > 1 else None
                refs.append((str(ref[0]), str(marca) if marca else None))
            elif isinstance(ref, dict):
                refs.append((str(ref.get("codigo_ref", "") or ""),
                             str(ref.get("marca_ref")) if ref.get("marca_ref") else None))
        r.cross_refs = refs
        return r


# ---------------------------------------------------------------------------
# SELETORES CENTRALIZADOS (agrupados por etapa)
# ---------------------------------------------------------------------------
# Como usar:
#   - Cada valor é uma lista de seletores, testados na ordem. O primeiro que
#     encontrar um elemento visível é usado.
#   - Para ajustar: rode `python diagnostico.py` logado, ou use o F12 no Chrome.
#
# CONFIRMADO (análise do bundle JS em 2026):
#   * Login Okta: input[name='identifier'], credenciais.passcode, submit.
#   * API do catálogo: POST {basePath}/rest/<Operacao>, body {"<Op>":{...}}.
#   * Campos dos artigos na resposta: articleNumber, dataSupplierId, brandName,
#     articleDescription, oemNumbers[].articleNumber, articleLinkId, dataFormats.
