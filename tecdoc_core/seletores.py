"""Seletores do TecDoc, constantes de campos e utilitários de navegação.
Independem do TecDocAutomator (facilita ajustar o site sem mexer na automação).
"""
from __future__ import annotations

from playwright.sync_api import Page

# O filtro real do TecDoc está operacional: o multiselect abre um painel
# overlay, pesquisa pelo role=searchbox e atualiza a URL com ?brands=.
_APLICAR_FILTRO_MARCAS_SITE = True

SELETORES: dict[str, dict[str, str]] = {
    # ------------------------------------------------------------------ LOGIN
    "login": {
        "campo_usuario": (
            "input[name='identifier'], "
            "input[name='username'], "
            "input[type='text'], "
            "input[type='email']"
        ),
        "campo_senha": (
            "input[name='credentials.passcode'], "
            "input[name='password'], "
            "input[type='password']"
        ),
        "btn_primeiro": (          # OKTA: botão "Next" do passo usuário
            "input[type='submit'], button[type='submit'], "
            "button:has-text('Next'), button:has-text('Seguinte'), "
            "button:has-text('Continuar')"
        ),
        "btn_senha": (             # OKTA: botão "Sign In" do passo senha
            "input[type='submit'], button[type='submit'], "
            "button:has-text('Sign In'), button:has-text('Entrar')"
        ),
        "detector": (              # se algum aparecer, ainda estamos no login
            "input[name='identifier'], input[type='password']"
        ),
    },
    # ------------------------------------------------------------------ BUSCA
    "busca": {
        # campo onde digita o código (o real é input#part-search-input,
        # ta-name="search-input", no header — NÃO usar input[placeholder]
        # genérico, senão pode preencher outro campo da página)
        "campo_texto": (
            "input#part-search-input, "
            "input[ta-name='search-input'], "
            "input-search input, "
            "webcat-header input-search input, "
            "input[type='search']"
        ),
        # botão opcional (se Enter não disparar)
        "botao": (
            "button[type='submit'], "
            "button[aria-label*='usca'], "      # busca/pesquisa
            "button:has-text('Buscar')"
        ),
        # aba para forçar a exibição de "Artigos" após a busca
        "aba_artigos": (
            "ta-tab[data-testid*='article']:not([hidden]), "
            ".mat-tab-label:has-text('Artigos'), "
            ".nav-link:has-text('Artigos')"
        ),
    },
    # -------------------------------------------------------------- RESULTADO
    # A tabela de resultados do TecDoc é uma AG-Grid (divs, não <table>).
    # Colunas reais (col-id): articleComparison, articleNo, image,
    # description, stateText, quantity.
    "resultado": {
        "lista": (
            ".ag-root-wrapper, .ag-center-cols-container, "
            "table, .mat-mdc-table, .article-list, "
            ".direct-search-results"
        ),
        "linha": (
            ".ag-row[row-id], table tbody tr, tr, .article-row, .result-row"
        ),
        # marca = primeiro <span class="fw-bold"> dentro da célula description
        "cel_marca": (
            "[col-id='description'] span.fw-bold, .brand, "
            "[data-field='brand'], .brand-name, td:nth-child(1)"
        ),
        # designação = <span class="generic-article"> dentro da description
        "cel_descricao": (
            "[col-id='description'] .generic-article, .description, "
            "[data-field='description'], .article-name, td:nth-child(2)"
        ),
        # disponibilidade = coluna "Estado do artigo"
        "cel_disponivel": (
            "[col-id='stateText'], .availability, "
            "[data-field='availability'], .availability-badge, td:last-child"
        ),
    },
    # ------------------------------------------------------------ FILTROS
    # Painel lateral da busca: filtros de Marca / Grupo de produtos etc.
    # O seletor de marcas é um PrimeNG p-multiselect dentro de
    # [ta-name='brand-selector'] (trigger "Todas as marcas").
    "filtros": {
        "marca_selector": (
            "p-multiselect[ta-name='brand-selector'], "
            "[ta-name='brand-selector'] .p-multiselect, "
            ".filter-bar-item .p-multiselect"
        ),
        # campo onde se digita a marca (p-multiselect-filter). É o ÚLTIMO
        # visível na página: os outros multiselects fechados têm o campo
        # escondido — por isso usar :visible.
        "filtro_texto": (
            "input.p-multiselect-filter[role='searchbox']:visible, "
            "input.p-multiselect-filter:visible, "
            ".p-multiselect-filter-container input:visible"
        ),
        # opções: li[role='option'] com aria-label = nome da marca e
        # ta-value = id da marca (ex.: ta-value="7944")
        "opcao": (
            "li.p-multiselect-item[role='option'], "
            "li[role='option'].p-multiselect-item, "
            "li[role='option'], [role='option']"
        ),
        "check": ".p-checkbox-box",
    },
    # ------------------------------------------------- DATA DE REFERÊNCIA
    # Página de DETALHE do artigo (chega-se clicando num resultado da AG-Grid).
    # - resumo: part-detail-v2-summary-table (tr / th=rotulo / td=valor)
    # - estado: "<span class='text-center'><span>Estado:</span><span> Normal </span>"
    # - referências OE: tr[ta-name='oe-number'], código em ta-value ou td:first-child
    "detalhe": {
        "sumario": "part-detail-v2-summary-table table, part-detail-v2-summary-table",
        "linha_sumario": "tr",
        "cel_rotulo": "th",
        "cel_valor": "td",
        "estado": "span.text-center:has-text('Estado')",
        "lista_oe": "part-detail-v2-oe-table",
        "linha_oe": "tr[ta-name='oe-number']",
        "cel_oe_codigo": "td:first-child a strong, td:first-child",
        "cel_oe_info": "td:nth-child(2)",
    },
    # DATA DE REFERÊNCIA (manutenção)
    "xref": {
        "btn_detalhes": (
            "button:has-text('Detalhes'), button:has-text('Ver'), "
            "a:has-text('Detalhes'), tr"
        ),
        "aba_xref": (
            "ta-tab:has-text('Refer'), .mat-tab-label:has-text('Refer'), "
            "button:has-text('Cross-reference')"
        ),
        "linha_xref": "tbody tr, tr, .xref-row",
        "cel_codigo": "td:nth-child(1), .code",
        "cel_marca": "td:nth-child(2), .brand",
    },
}


# ---------------------------------------------------------------------------
# API DO CATÁLOGO (nomes de operação para interceptação)
# ---------------------------------------------------------------------------
# O SPA chama:  POST  {basePath}/rest/<Operacao>  body {"<Operacao>": {...}}
# As respostas JSON contêm os artigos. Listamos as operações prováveis por etapa.

OPERACAO_BUSCA = (  # quando digitamos o código e pressionamos Enter
    "DirectSearch",
    "getArticleDirectSearchAllNumbersWithState",
    "SearchArticles",
)
OPERACAO_DETALHE = (  # quando abrimos os detalhes de um artigo
    "getDirectArticlesByIds7",
    "getArticles",
    "getArticleLinkedAllLinkingTarget",
)
OPERACAO_XREF = (  # referências cruzadas / números alternativos
    "getArticleLinkedAllLinkingTargetManufacturer",
    "getArticleLinkedAll",
    "CrossReference",
)
# nomes de campos reconhecidos nos JSON da API (ordem de preferência)
# IMPORTANTE: tudo em minúsculas (o comparador usa k.lower()).
CAMPO_MARCA = ("brandname", "brand", "manufacturer", "datasuppliername")
CAMPO_DESCRICAO = ("articledescription", "description", "name", "articlename")
CAMPO_DISPONIVEL = ("instock", "available", "availability", "stock", "state")
CAMPO_URL = ("url", "href")


# ---------------------------------------------------------------------------
# UTILITÁRIOS de navegação genérica
# ---------------------------------------------------------------------------

def primeiro_visivel(page: Page, seletores: str):
    """Testa uma lista de seletores separados por vírgula e devolve o primeiro
    elemento localizável. Se nenhum casar, devolve o primeiro mesmo assim
    (para dar erro claro de seletor)."""
    loc = page.locator(seletores)
    if loc.count() > 0:
        return loc
    raise RuntimeError(
        f"Nenhum seletor encontrado na página.\nSeletores testados: {seletores}"
    )


def localizar(page: Page, chave_etapa: str, chave_campo: str):
    """Localiza um elemento usando o dicionário SELETORES."""
    return primeiro_visivel(page, SELETORES[chave_etapa][chave_campo])


class BuscaNaoIniciadaError(RuntimeError):
    """A busca pelo código não chegou a ser disparada no site."""


# ---------------------------------------------------------------------------
# AUXILIARES de extração de JSON (recursivo, tolerante a estrutura)
# ---------------------------------------------------------------------------

def _caminho(obj, chaves: tuple[str, ...]):
    """Encontra o primeiro valor no dicionário cuja chave está em `chaves`
    (sem diferenciar maiúsculas). Percorre listas e dicts recursivamente."""
    chaves_low = {c.lower() for c in chaves}

    def anda(o):
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in chaves_low and v not in (None, "", [], {}):
                    return v
                r = anda(v)
                if r is not None:
                    return r
        elif isinstance(o, list):
            for item in o:
                r = anda(item)
                if r is not None:
                    return r
        return None

    return anda(obj)


def _todos_caminhos(obj, chaves: tuple[str, ...], limite: int = 500):
    """Como _caminho, mas coleta TODOS os valores (para listas de artigos)."""
    chaves_low = {c.lower() for c in chaves}
    out = []

    def anda(o):
        if len(out) >= limite:
            return
        if isinstance(o, dict):
            for k, v in o.items():
                if k.lower() in chaves_low and v not in (None, "", [], {}):
                    out.append(v)
                anda(v)
        elif isinstance(o, list):
            for item in o:
                anda(item)

    anda(obj)
    return out


# ---------------------------------------------------------------------------
# AUTOMAÇÃO
# ---------------------------------------------------------------------------
