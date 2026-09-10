"""Extrai os dados do JSON da API TecDoc (sem Playwright).
Usa apenas _caminho/_todos_caminhos de tecdoc_core.seletores.
"""
from __future__ import annotations

from .modelo import PecaResultado
from .seletores import _caminho, CAMPO_MARCA, CAMPO_DESCRICAO

class _ParserApi:
    """Lê o JSON de uma resposta `/rest/DirectSearch*` e preenche PecaResultado.

    Conservador: preenche o que conseguir; não quebra se a estrutura mudar.
    """

    def __init__(self, resultado: PecaResultado, marcas: list[str]):
        self.resultado = resultado
        self.marcas = marcas
        self.tenha_dados_faltando = False

    def extrair(self, corpo) -> bool:
        if corpo is None:
            self.tenha_dados_faltando = True
            return False

        # tenta achar um "array" de artigos no JSON (recursivo)
        artigos_candidatos: list[dict] = []
        self._coletar_artigos(corpo, artigos_candidatos)
        if not artigos_candidatos:
            # nenhuma lista de artigos: sinal de "sem resultado"
            self.resultado.observacao = "Nenhum resultado encontrado"
            self.tenha_dados_faltando = True
            return True

        # cada artigo: monta dict chave->valor
        artigos: list[dict] = []
        for a in artigos_candidatos:
            if not isinstance(a, dict):
                continue
            artigos.append({
                "marca": _caminho(a, CAMPO_MARCA) or "",
                "descricao": _caminho(a, CAMPO_DESCRICAO) or "",
                "codigo_ref": _caminho(a, ("articleNumber", "articleNo")) or "",
                "disponivel": _eh_disponivel(a),
            })

        if not artigos:
            self.resultado.observacao = "Nenhum resultado encontrado"
            self.tenha_dados_faltando = True
            return True

        # filtra por marcas
        if self.marcas:
            filtrados = [a for a in artigos
                         if a["marca"] in self.marcas]
            if not filtrados:
                self.resultado.observacao = (
                    f"Nada nas marcas: {', '.join(self.marcas)}"
                )
                self.tenha_dados_faltando = True
                return True
            artigos = filtrados
            # prioriza a ordem das marcas configuradas
            artigos.sort(key=lambda a: self.marcas.index(a["marca"])
                         if a["marca"] in self.marcas else 99)

        melhor = artigos[0]
        self.resultado.marca = melhor["marca"]
        self.resultado.descricao = melhor["descricao"]
        self.resultado.numero_artigo = melhor["codigo_ref"]
        self.resultado.disponivel = melhor["disponivel"]
        # guarda também as demais marcas como candidatas p/ cross? Não, deixo vazio.
        return True

    def _coletar_artigos(self, obj, out: list) -> None:
        """Coleta dicionários que parecem artigos (têm articleNumber e marca)."""
        if isinstance(obj, dict):
            tem_numero = any(
                k.lower() in ("articlenumber", "articleno") and v
                for k, v in obj.items()
            )
            tem_marca = any(k.lower() in CAMPO_MARCA for k in obj)
            if tem_numero or tem_marca:
                out.append(obj)
                return
            for v in obj.values():
                self._coletar_artigos(v, out)
        elif isinstance(obj, list):
            for item in obj:
                self._coletar_artigos(item, out)


def _eh_disponivel(artigo: dict) -> bool:
    """Heurística: artigo 'disponível' se tem campo de disponibilidade verdadeiro
    OU se possui dataFormats (artigo ativo no catálogo)."""
    for k, v in artigo.items():
        kl = k.lower()
        if kl in ("instock", "available", "availability", "stock",
                  "availability_status") and isinstance(v, bool):
            return v
        if kl == "state" and isinstance(v, (int, str)):
            return str(v) not in ("0", "3", "7", "deleted", "del")
    if "dataformats" in artigo:
        return True
    return True


# ---------------------------------------------------------------------------
# Função de alto nível usada pela GUI
# ---------------------------------------------------------------------------
