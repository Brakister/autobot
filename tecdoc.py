"""Automação do TecDoc via Playwright.

Este módulo é 100% "máquina": faz login, busca os códigos, filtra por marcas
e extrai descrição/marca/cross-references, devolvendo resultados estruturados.

ESTRATÉGIA DE EXTRAÇÃO (duas camadas):
1. **API (principal)** — o site TecDoc é um SPA Angular que fala com uma API
   JSON-RPC: faz POST em `${basePath}/rest/<Operacao>` com body
   `{"<Operacao>": {parametros}}`. Em vez de raspar o HTML, interceptamos as
   respostas dessa API durante a navegação (mais robusto a mudanças de layout).
2. **DOM (fallback)** — se a interceptação falhar, tenta ler os dados do HTML.

Os seletores ficam todos centralizados no dicionário `SELETORES`, agrupados por
etapa, para fácil ajuste.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
import json
import random
import re
import time
import unicodedata
import urllib.parse
from pathlib import Path

from playwright.sync_api import sync_playwright, Page, BrowserContext, TimeoutError

import config


# ---------------------------------------------------------------------------
# Modelo de resultado
# ---------------------------------------------------------------------------

@dataclass
class PecaResultado:
    codigo: str
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

# O filtro real do TecDoc está operacional: o multiselect abre um painel
# overlay, pesquisa pelo role=searchbox e atualiza a URL com ?brands=.
_APLICAR_FILTRO_MARCAS_SITE = True

# IDs confirmados pelo próprio TecDoc nas rotas `brands=`. Para estas marcas,
# não há motivo para abrir o multiselect PrimeNG (a origem dos travamentos).
_BRAND_IDS_CONHECIDOS = {
    "hepu": "178",
    "textar": "39",
}

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
        # O quadrado visual do PrimeNG é um <div>; o input real fica dentro
        # de `.p-hidden-accessible`. É ele que mantém o estado confiável.
        "check_input": (
            "input[type='checkbox'], input[role='checkbox'], "
            ".p-hidden-accessible input"
        ),
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


class BuscaDestravada(RuntimeError):
    """O usuário pediu para pular a tentativa atual e retomá-la no fim."""


# ---------------------------------------------------------------------------
# AUTO-REPARO: heurísticas de erros transientes (rede/cache/servidor)
# ---------------------------------------------------------------------------

_PADRAO_TRANSIENTE = (
    # Playwright / chromium (net::ERR_*)
    "net::err_", "err_connection", "err_internet_disconnected",
    "err_name_not_resolved", "err_timed_out", "err_aborted",
    "err_connection_reset", "err_connection_refused",
    # mensagens comuns de rede
    "connection reset", "connection refused", "connection closed",
    "network is unreachable", "host unreachable", "socket",
    "timed out", "timeout exceeded", "target closed", "targetclosed",
    "has been closed", "was closed", "is closed",
    "page closed", "pageclosed", "browser closed", "browserclosed",
    "context closed", "contextclosed", "crash",
    "aborted", "load failed", "fetch failed", "reset by peer",
    # erros de servidor/gateway
    "502 bad gateway", "503 service unavailable", "504 gateway timeout",
    "500 internal server error", "http 500", "http 502", "http 503",
    "server error", "gateway", "upstream",
)


def _eh_erro_transiente(exc: BaseException) -> bool:
    """True se a mensagem da exceção parece queda de rede/erro de servidor."""
    if isinstance(exc, BuscaNaoIniciadaError):
        return True
    texto = f"{type(exc).__name__}: {exc}".lower()
    return any(p in texto for p in _PADRAO_TRANSIENTE)


def _resultado_tem_falha_transiente(res) -> bool:
    """True se o resultado (já retornado) indica falha recuperável.

    Como `buscar_codigo` catura algumas exceções e devolve PecaResultado com
    observacao, esta função olha para a observacao e para a URL atual:
    timeout, rede, servidor 5xx ou página de login/catalogo quebrada.
    """
    obs = f"{res.observacao or ''}".lower()
    if any(p in obs for p in _PADRAO_TRANSIENTE):
        return True
    if "nenhum resultado" in obs or "nada nas marcas" in obs:
        return False
    if "erro" in obs:
        return True
    return False


def _resultado_filtro_falhou(res) -> bool:
    """True se o resultado indica que o filtro de marcas não foi aplicado.

    O `buscar_codigo` devolve esta observacao quando `_extrair_dom` detecta
    que o filtro não refletiu na URL (?brands=) e, para não arriscar o 404,
    não abriu o detalhe. Vale repetir o MESMO código: o site às vezes engole
    o clique no checkbox do multiselect e a re-busca aplica o filtro normal.
    """
    obs = f"{res.observacao or ''}".lower()
    return "filtro" in obs and "refletiu" in obs


def _norm_texto(txt: str) -> str:
    """Normaliza texto p/ comparação: minúsculas, sem acentos/trema, espaços.

    Idêntico ao TecDocAutomator._norm, mas em nível de módulo para ser
    reutilizado também no _ParserApi (filtro de marcas da resposta JSON).
    Ex.: 'Lemförder' -> 'lemforder', 'HEPU GmbH' -> 'hepu GmbH'.
    """
    s = (txt or "").lower()
    s = "".join(
        c for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    )
    return " ".join(s.split())


def _limpar_codigo(txt) -> str:
    """Remove toda ocorrência de espaço/whitespace de um código lido do site.

    O TecDoc renderiza os números de artigo/OE agrupados por legibilidade
    (ex.: '038 121 011 B', 'J9C 19939', '13 51 7 584 461'); o código real do
    catálogo não tem espaços ('038121011B', 'J9C19939', '13517584461').
    Também remove quebras de linha/tabulação que eventualmente entram nos
    textos lidos do DOM.
    """
    if not txt:
        return ""
    return "".join(str(txt).split())


def _marca_casa(marca_lida: str, marcas: list[str]) -> bool:
    """Comparação tolerante marca lida x marcas selecionadas (não exata).

    Casa por nome exato, por prefixo de palavra, por palavra inteira e até
    por marca dentro do texto (ex.: 'febi' em 'FEBI BILSTEIN', 'hepu' em
    'HEPU GmbH'). Usada no DOM (grid) e na resposta da API, que podem trazer
    a marca com sufixo/acento/case diferentes do que o usuário digitou — o
    match exato fazia 'HEPU' ser rejeitado e virar 'produto não encontrado'.
    """
    if not marca_lida:
        return False
    m = _norm_texto(marca_lida)
    for b in marcas:
        b = _norm_texto(b)
        if not b:
            continue
        if m == b or m.startswith(b + " ") or b in m:
            return True
        # palavra-a-palavra (ex.: 'skf' em 'abc skf xyz')
        for palavra in m.split():
            if palavra == b or (len(b) >= 2 and palavra.startswith(b)):
                return True
    return False


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

class TecDocAutomator:
    def __init__(self, login: str, senha: str, headless: bool = False,
                 marcas: list[str] | None = None, capturar_api: bool = False,
                 on_mensagem: callable | None = None,
                 deve_desbloquear: callable | None = None):
        self.login = login
        self.senha = senha
        self.headless = headless
        self.marcas = marcas or []
        self.capturar_api = capturar_api  # salva request/response em data/captura/
        self._msg_cb = on_mensagem
        self._deve_desbloquear = deve_desbloquear
        self._pw = None
        self._context: BrowserContext | None = None
        self._page: Page | None = None
        self._ultima_resposta_direct_search = None
        self._ultimas_respostas_detalhe: list[dict] = []
        # pares (articleLinkId, linkingTargetId) do getArticleLinkedAllLinking
        # Target4 que o site dispara ao abrir o detalhe + origem (URL/headers)
        # pra resolver os nomes dos veículos via linkedTargetsByIds3.
        self._link4_pares: list[tuple[int, int]] = []
        self._link4_origem: dict = {}
        self._cap_file = None
        self._mensagens = []
        self._filtro_aplicado = False
        self._filtro_efetivado = False  # brands= apareceu na URL real do site
        # URL da busca cacheada enquanto ainda tem groups= (a SPA esvazia
        # esse parâmetro ao abrir o detalhe, quebrando a navegação direta).
        self._url_ultima_busca = ""

    def _msg(self, texto: str) -> None:
        self._mensagens.append(texto)
        self._rastro_abrir(texto)
        if self._msg_cb:
            try:
                self._msg_cb(texto)
            except Exception:
                pass
        else:
            print(f"[cadastroauto] {texto}")

    def _checar_desbloqueio(self) -> None:
        """Interrompe a tentativa em pontos seguros quando solicitado."""
        if self._deve_desbloquear and self._deve_desbloquear():
            raise BuscaDestravada("Solicitação de destravar recebida")

    # -- contexto ------------------------------------------------------------

    def iniciar(self) -> None:
        self._pw = sync_playwright().start()
        browser = self._pw.chromium.launch(headless=self.headless)
        self._context = browser.new_context(
            storage_state=str(config.SESSION_FILE) if config.SESSION_FILE.exists() else None,
        )
        # o Playwright não salva sessionStorage no storage_state; o Okta
        # guarda os tokens lá. Restauramos via init-script.
        if self._arquivo_sessionstorage().exists():
            self._restaurar_sessionstorage()
        self._page = self._context.new_page()
        self._page.set_default_timeout(config.PLAYWRIGHT_TIMEOUT)
        self._rastrear_navegacoes()
        if self.capturar_api:
            self._configurar_interceptacao()
        else:
            self._registrar_interceptacao()

    def encerrar(self) -> None:
        try:
            if self._context:
                self._context.storage_state(path=str(config.SESSION_FILE))
        except Exception:
            pass
        self._salvar_sessionstorage()
        if self._cap_file:
            try:
                self._cap_file.close()
            except Exception:
                pass
            self._cap_file = None
        try:
            if self._pw:
                self._pw.stop()
        except Exception:
            pass

    # -- auto-reparo ---------------------------------------------------------

    def _reconectar(self) -> None:
        """Reinicia o navegador (após queda de rede/erro de servidor).

        Encerra a instância atual com salvamento de sessão e sobe tudo de novo
        (browser, contexto com a sessão salva, página, interceptação de API e
        login garantido). Seguro para chamar mesmo se o Playwright já caiu:
        tudo dentro de try/except.
        """
        self._msg("Rede/servidor com problema — tentando religar o navegador...")
        # 1) salva o que der e derruba o Playwright antigo
        try:
            self.encerrar()
        except Exception:
            pass
        self._pw = None
        self._context = None
        self._page = None
        # 2) sobe tudo de novo (reusa a sessão salva)
        self._pw = sync_playwright().start()
        browser = self._pw.chromium.launch(headless=self.headless)
        self._context = browser.new_context(
            storage_state=str(config.SESSION_FILE)
            if config.SESSION_FILE.exists() else None,
        )
        if self._arquivo_sessionstorage().exists():
            self._restaurar_sessionstorage()
        self._page = self._context.new_page()
        self._page.set_default_timeout(config.PLAYWRIGHT_TIMEOUT)
        self._rastrear_navegacoes()
        if self.capturar_api:
            self._configurar_interceptacao()
        else:
            self._registrar_interceptacao()
        # 3) garante login; se MFA, espera o usuário terminar no navegador
        self.garantir_login()
        self._filtro_aplicado = False
        self._filtro_efetivado = False
        self._url_ultima_busca = ""
        self._msg("Navegador religado com sucesso.")

    def _buscar_com_reconexao(self, codigo: str) -> "PecaResultado":
        """buscar_codigo com auto-reparo: tenta de novo ante quedas de rede.

        Se o erro for transitório (queda de rede, timeout, 5xx), chama
        _reconectar() e refaz a busca, até config.TENTATIVAS_POR_CODIGO.
        Se o FILTRO de marcas não refletir na URL (?brands=), também refaz a
        busca do MESMO código após config.FILTRO_RETRY_ESPERA — sem reiniciar
        o navegador, apenas redigitando o código: o site às vezes engole o
        clique no checkbox do multiselect.
        Erros não transitórios estouram imediatamente.
        """
        filtro_tentativas = 0
        for tentativa in range(1, config.TENTATIVAS_POR_CODIGO + 1):
            try:
                res = self.buscar_codigo(codigo)
            except Exception as exc:
                if not _eh_erro_transiente(exc) or \
                        tentativa >= config.TENTATIVAS_POR_CODIGO:
                    raise
                self._msg(
                    f"[{codigo}] erro transitório (tentativa "
                    f"{tentativa}/{config.TENTATIVAS_POR_CODIGO}): {exc!r}")
                time.sleep(random.uniform(*config.PAUSA_ENTRE_TENTATIVAS))
                try:
                    self._reconectar()
                except Exception as exc2:
                    self._msg(f"[{codigo}] falha ao religar navegador: {exc2!r}")
                continue
            if _resultado_filtro_falhou(res):
                if (filtro_tentativas >= config.FILTRO_RETRY_TENTATIVAS or
                        tentativa >= config.TENTATIVAS_POR_CODIGO):
                    return res
                filtro_tentativas += 1
                self._msg(
                    f"[{codigo}] filtro de marcas não refletiu no site — "
                    f"recarregando o código "
                    f"({filtro_tentativas}/{config.FILTRO_RETRY_TENTATIVAS})…")
                time.sleep(random.uniform(*config.FILTRO_RETRY_ESPERA))
                # força a reaplicação do filtro na próxima busca
                self._filtro_aplicado = False
                self._filtro_efetivado = False
                continue
            if not _resultado_tem_falha_transiente(res):
                return res
            if tentativa >= config.TENTATIVAS_POR_CODIGO:
                return res
            self._msg(
                f"[{codigo}] resultado com falha transitória "
                f"({tentativa}/{config.TENTATIVAS_POR_CODIGO}), repetindo…")
            time.sleep(random.uniform(*config.PAUSA_ENTRE_TENTATIVAS))
            try:
                self._reconectar()
            except Exception as exc2:
                self._msg(f"[{codigo}] falha ao religar navegador: {exc2!r}")
        return res  # pragma: no cover (loop sempre retorna/levanta acima)

    # -- persistência de sessão (cookies + localStorage + sessionStorage) ---

    @staticmethod
    def _arquivo_sessionstorage() -> Path:
        return config.data_dir() / "_session_storage.json"

    @staticmethod
    def _origem_sources() -> tuple[str, ...]:
        return (
            "https://login.tecalliance.net",
            "https://web.tecalliance.net",
        )

    def _salvar_sessionstorage(self) -> None:
        """Grava o sessionStorage de cada origem relevante para restaurar depois.

        Não navega para outra origem durante o encerramento. Fazer isso
        disparava a rota raiz do catálogo e terminava em `catalog-not-found`,
        mascarando o resultado da busca.
        """
        if self._page is None:
            return
        arquivo = self._arquivo_sessionstorage()
        try:
            dump = json.loads(arquivo.read_text(encoding="utf-8")) \
                if arquivo.exists() else {}
        except Exception:
            dump = {}
        try:
            origem_atual = self._page.evaluate("() => location.origin")
            if origem_atual in self._origem_sources():
                dados = self._page.evaluate(
                    "() => { const o = {}; "
                    "for (let i=0;i<sessionStorage.length;i++){"
                    "const k=sessionStorage.key(i); o[k]=sessionStorage.getItem(k);}"
                    "return o; }"
                )
                if dados:
                    dump[origem_atual] = dados
        except Exception:
            pass
        try:
            arquivo.write_text(
                json.dumps(dump, ensure_ascii=False), encoding="utf-8",
            )
        except Exception:
            pass

    def _restaurar_sessionstorage(self) -> None:
        """Injeta init-scripts que preenchem o sessionStorage por origem."""
        try:
            dump = json.loads(
                self._arquivo_sessionstorage().read_text(encoding="utf-8")
            )
        except Exception:
            return
        if not dump:
            return
        for origem, dados in dump.items():
            if not dados:
                continue
            dados_js = json.dumps({str(k): str(v) for k, v in dados.items()})
            origem_js = json.dumps(origem)
            js = (
                "() => {"
                f" const dados = {dados_js};"
                f" const alvo = {origem_js};"
                " try {"
                "   if (location.origin === alvo) {"
                "     for (const k in dados) sessionStorage.setItem(k, dados[k]);"
                "   }"
                " } catch (e) {}"
                "}"
            )
            try:
                self._context.add_init_script(js)
            except Exception:
                continue

    # -- interceptação da API ------------------------------------------------

    def _configurar_interceptacao(self) -> None:
        from pathlib import Path
        import datetime
        pasta = config.data_dir() / "captura"
        pasta.mkdir(parents=True, exist_ok=True)
        self._cap_file = open(
            pasta / f"captura_{datetime.datetime.now():%Y%m%d_%H%M%S}.jsonl",
            "w", encoding="utf-8",
        )
        self._registrar_interceptacao()

    def _registrar_interceptacao(self) -> None:
        """Escuta XHR/fetch do site (rest e jsonEndpoint).

        Registra sempre: além de alimentar o parser de busca, captura os
        pares de ligação (getArticleLinkedAllLinkingTarget4) usados para
        resolver as aplicações (veículos) do artigo.
        """
        self._page.on("response", self._ao_responder_rest)
        self._page.on("request", self._ao_pedir_link4)
        self._page.on("response", self._ao_responder_link4)

    def _ao_responder_rest(self, resp):
        url = resp.url
        if "/rest/" not in url:
            return
        try:
            corpo = resp.json()
        except Exception:
            return
        if self._cap_file:
            rec = {"url": url, "method": resp.request.method, "body": corpo}
            self._cap_file.write(json.dumps(rec, ensure_ascii=False) + "\n")
            self._cap_file.flush()
        # classifica a resposta
        nome_op = url.rsplit("/", 1)[-1]
        if any(op.lower() in nome_op.lower() for op in OPERACAO_BUSCA):
            self._ultima_resposta_direct_search = corpo
        elif any(op.lower() in nome_op.lower() for op in
                 (OPERACAO_DETALHE + OPERACAO_XREF)):
            self._ultimas_respostas_detalhe.append(corpo)

    def _ao_pedir_link4(self, req):
        """Guarda URL/headers/pedido de uma chamada getArticleLinkedAll
        LinkingTarget4 (referência pros lotes de resolução de veículos)."""
        if req.resource_type not in ("xhr", "fetch"):
            return
        if "jsonEndpoint" not in req.url:
            return
        try:
            obj = json.loads(req.post_data or "{}")
        except Exception:
            return
        if "getArticleLinkedAllLinkingTarget4" in obj:
            obj = obj["getArticleLinkedAllLinkingTarget4"]
            if not self._link4_origem:
                self._link4_origem = {
                    "url": req.url,
                    "headers": dict(req.headers),
                    "pedido": obj,
                }

    def _ao_responder_link4(self, resp):
        """Coleciona os pares articleLinkId+linkingTargetId das respostas
        do getArticleLinkedAllLinkingTarget4 (pontos de ligação)."""
        if "jsonEndpoint" not in resp.url:
            return
        try:
            corpo = resp.json()
            req_data = resp.request.post_data or ""
        except Exception:
            return
        if "getArticleLinkedAllLinkingTarget4" not in req_data:
            return
        for it in corpo.get("data", {}).get("array", []) or []:
            for lk in (it.get("articleLinkages", {}).get("array", []) or []):
                al = lk.get("articleLinkId")
                lt = lk.get("linkingTargetId")
                if al is not None and lt is not None:
                    par = (int(al), int(lt))
                    if par not in self._link4_pares:
                        self._link4_pares.append(par)

    # -- login ---------------------------------------------------------------

    def _esta_no_login(self) -> bool:
        """True se a página atual ainda está na tela de login (Okta ou do app).

        Inclui o post-logout do TecDoc (…/pt/post-logout): a sessão caiu e o
        catálogo não está carregado, então vale religar o login antes de
        procurar o campo de busca.
        """
        try:
            if self._page.locator(SELETORES["login"]["detector"]).count() > 0:
                return True
            url = self._page.url
            return ("/login" in url or "login.tecalliance" in url
                    or "oauth2" in url
                    or "post-logout" in url or "logout" in url
                    or "logoff" in url)
        except Exception:
            return True

    def _aguardar_fora_do_login(self, timeout_s: float = 120.0,
                                on_mensagem=None) -> bool:
        """Espera até a tela de login sumir.

        Se o login automático falhou (ex.: MFA/aprovação no celular), o
        usuário completa o login manualmente no navegador que está aberto.
        Retorna True se saiu do login a tempo.
        """
        if on_mensagem:
            on_mensagem(
                "Se aparecer verificação (MFA/aprovação), complete o login "
                "manualmente no navegador que se abriu."
            )
        inicio = time.time()
        while time.time() - inicio < timeout_s:
            try:
                if not self._esta_no_login():
                    try:
                        self._page.wait_for_load_state("networkidle", timeout=8_000)
                    except TimeoutError:
                        pass
                    return True
            except Exception:
                pass
            time.sleep(2)
        return False

    def garantir_login(self) -> None:
        """Garante que estamos logados e na tela do catálogo.

        Ordem:
          1. Navega até o TecDoc (reutilizando a sessão salva).
          2. Se cair na tela de login, tenta o login automático.
          3. Se ainda estiver no login (MFA etc.), aguarda o usuário concluir
             manualmente no navegador aberto.
        """
        page = self._page
        page.goto(config.TECDOC_URL)
        try:
            page.wait_for_load_state("networkidle", timeout=20_000)
        except TimeoutError:
            pass

        if not self._esta_no_login():
            return  # sessão salva ainda válida

        # Tenta o login automático; se não completou, dá uma segunda chance
        # (a página Okta pode ter demorado a assentar o formulário).
        self._fazer_login()
        if self._esta_no_login():
            self._page.wait_for_timeout(2500)
            self._fazer_login()
        if self._esta_no_login():
            self._aguardar_fora_do_login(on_mensagem=self._msg)

    def _fazer_login(self) -> None:
        """Preenche a tela de login do TecAlliance (Okta).

        Tela atual (2026): URL `login.tecalliance.net`, página "Sign In".
        Username: input[name='identifier']
        Botão inicial: input[type='submit'] (Okta "Next")
        Depois do primeiro passo, aparece o campo de senha:
        input[name='credentials.passcode'] (Okta) e botão submit novamente.
        """
        page = self._page

        # O Okta primeiro resolve o device fingerprint e só então renderiza o
        # formulário. Espera a página assentar antes de procurar os campos;
        # preencher no meio do carregamento falhava o login automático.
        try:
            page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass
        page.wait_for_timeout(1200)

        # Passo 1: usuário (com pequeno retry — o campo pode aparecer logo
        # depois do fingerprint).
        for _tent in range(2):
            campo_user = page.locator(SELETORES["login"]["campo_usuario"])
            try:
                if campo_user.count() > 0 and campo_user.first.is_visible():
                    campo_user.first.fill(self.login)
                    localizar(page, "login", "btn_primeiro").first.click()
                    try:
                        page.wait_for_load_state("networkidle", timeout=20_000)
                    except TimeoutError:
                        pass
                    page.wait_for_timeout(800)
                    break
            except Exception:
                pass
            page.wait_for_timeout(1500)

        # Passo 2: senha (se aparecer)
        campo_senha = page.locator(SELETORES["login"]["campo_senha"]).first
        if campo_senha.count() > 0:
            for _tent in range(2):
                try:
                    if campo_senha.is_visible():
                        campo_senha.fill(self.senha)
                        localizar(page, "login", "btn_senha").first.click()
                        break
                except Exception:
                    page.wait_for_timeout(1200)
            try:
                page.wait_for_load_state("networkidle", timeout=20_000)
            except TimeoutError:
                pass
            page.wait_for_timeout(800)

        # Passo 3: pode haver um botão final "Entrar/Continuar" pós-Okta
        for _ in range(3):
            if not self._esta_no_login():
                return
            btns = page.locator(
                "input[type='submit'], button[type='submit'], "
                "button:has-text('Entrar'), button:has-text('Login'), "
                "button:has-text('Seguinte')"
            )
            if btns.count() > 0:
                try:
                    btns.first.click()
                except Exception:
                    pass
                try:
                    page.wait_for_load_state("networkidle", timeout=15_000)
                except TimeoutError:
                    pass
                page.wait_for_timeout(500)
            else:
                break

    # -- busca ---------------------------------------------------------------

    def _aguardar_grid_estavel(self, tempo_max_s: float = 30.0) -> bool:
        """Espera a AG-Grid terminar de renderizar (contagem e 1ª linha estáveis).

        Depois de buscar ou de aplicar filtro de marcas, a grid recarrega e as
        linhas mudam; clicar durante esse re-render pega linha errada (404).

        Após alguns segundos, aceita "contagem estável" (mesma quantidade de
        linhas em 2 amostras seguidas): a AG-Grid costuma ficar re-renderizando
        o conteúdo/ordem sem mudar o número de linhas, e a leitura real (por
        row-id + goto direto) não depende do texto da 1ª linha ficar parado.
        Isso impede a espera de dar o timeout inteiro (ex.: 45s) à toa.
        """
        page = self._page
        inicio = time.time()
        amostras: list[tuple[int, str]] = []
        contagens: list[int] = []
        while time.time() - inicio < tempo_max_s:
            self._checar_desbloqueio()
            try:
                linha = page.locator(SELETORES["resultado"]["linha"])
                n = linha.count()
            except Exception:
                n = 0
            primeiro = ""
            if n:
                try:
                    primeiro = linha.first.inner_text(timeout=800)[:60]
                except Exception:
                    pass
            if n == 0:
                amostras.clear()
                contagens.clear()
            else:
                amostras.append((n, primeiro))
                contagens.append(n)
                if len(amostras) > config.GRID_STABLE_SAMPLES:
                    amostras.pop(0)
                    contagens.pop(0)
                if (len(amostras) >= config.GRID_STABLE_SAMPLES
                        and len(set(amostras)) == 1):
                    return True
                if (time.time() - inicio >= 6.0
                        and len(contagens) >= config.GRID_STABLE_SAMPLES
                        and len(set(contagens)) == 1):
                    return True
            time.sleep(0.35)
        return False

    def _aguardar_grid_filtrada(self, tempo_max_s: float = 8.0) -> None:
        """Espera a grid mostrar as linhas da marca do filtro (sinal dinâmico).

        Em vez de networkidle + timeout cego depois de filtrar, observa a
        própria grid: assim que a PRIMEIRA linha visível exibir a marca
        selecionada (a AG-Grid ordena por marca após o filtro), o re-render
        terminou e dá pra ler e correr pro detalhe. Retorna quase de
        imediato no caso normal; se a marca não aparecer, deixa o
        `_extrair_dom` decidir como sempre fez.
        """
        page = self._page
        inicio = time.time()
        linhas = page.locator(
            ".ag-row[row-id], table tbody tr, .article-row, .result-row"
        )
        # respiro mínimo pro servidor/AG-Grid trocar os dados; sem isso a
        # primeira amostra ainda vê a grid SEM filtro (linhas antigas) e a
        # 1ª linha pode não ser da marca (aí a gente espera — sem risco).
        page.wait_for_timeout(800)
        while time.time() - inicio < tempo_max_s:
            try:
                n = linhas.count()
            except Exception:
                n = 0
            if n:
                for i in range(min(n, 3)):
                    try:
                        texto = linhas.nth(i).inner_text(timeout=800)
                        marca = self._cel_texto(
                            linhas.nth(i), "resultado", "cel_marca", texto)
                    except Exception:
                        marca = ""
                    if self._marca_bate(marca):
                        return
            page.wait_for_timeout(300)

    def _grid_ja_tem_marcas(self, max_linhas: int = 60) -> bool:
        """True se TODAS as linhas visíveis da grid já são das marcas alvo.

        Atalho ANTES de aplicar o filtro no site: quando o código tem só 1
        resultado (ou todos os resultados já são da marca desejada), abrir o
        multiselect e clicar checkbox é desnecessário — e era justamente onde
        o fluxo ficava preso com 'as vezes o click não vai'. Se ninguém além
        das marcas alvo aparece na grid, o resultado pode ser usado direto
        (equivale a um filtro já efetivado).
        """
        page = self._page
        try:
            linhas = page.locator(
                ".ag-row[row-id], table tbody tr, .article-row, .result-row")
            n = linhas.count()
        except Exception:
            return False
        if n == 0:
            return False
        for i in range(min(n, max_linhas)):
            try:
                texto = linhas.nth(i).inner_text(timeout=1_000)
                marca = self._cel_texto(
                    linhas.nth(i), "resultado", "cel_marca", texto)
            except Exception:
                texto = ""
                marca = ""
            if not self._marca_bate(marca):
                # O seletor às vezes lê a célula errada (articleNo no lugar do
                # nome) — confere pelo texto completo da linha antes de
                # considerar "precisa aplicar filtro".
                if texto and self._marca_no_texto(texto):
                    continue
                return False
        return True

    def _aplicar_filtros_marca(self) -> None:
        """Seleciona as marcas no filtro nativo do site (só 1x por execução).

        Fluxo igual ao manual: abre o multiselect 'Todas as marcas', DIGITA
        o nome da marca no campo de busca dele e ESPERA a opção aparecer na
        lista (as opções são filtradas/renderizadas sob demanda) antes de
        clicar. O usuário clica no CHECKBOX da opção (div.p-checkbox-box dentro
        do li#pn_id_XX_N) — clicar no checkbox é o que aplica a seleção.
        Só depois disso o grid tem os artigos certos da marca — clicar artigo
        errado é o que causava o 404.
        """
        if not self.marcas or self._filtro_aplicado:
            return
        self._filtro_aplicado = True
        # Orçamento global: o site nem sempre confirma o filtro rápido, mas a
        # aplicação NUNCA pode ficar presa aqui (caso real de 89s+ travado).
        deadline = time.time() + 45.0
        page = self._page
        try:
            self._checar_desbloqueio()
            # Caminho sem dropdown para as marcas mais usadas neste fluxo.
            # A rota é idêntica à que o TecDoc cria depois do checkbox.
            ids_conhecidos = [
                _BRAND_IDS_CONHECIDOS.get(self._norm(marca))
                for marca in self.marcas
            ]
            if self.marcas and all(ids_conhecidos):
                for marca, brand_id in zip(self.marcas, ids_conhecidos):
                    self._checar_desbloqueio()
                    if not self._aplicar_marca_id_pela_url(brand_id, marca):
                        break
                else:
                    self._filtro_efetivado = "brands=" in page.url
                    self._msg("Filtro de marcas aplicado diretamente pela URL "
                              f"({', '.join(self.marcas)}).")
                    return
            try:
                page.bring_to_front()
            except Exception:
                pass
            sel = page.locator(SELETORES["filtros"]["marca_selector"])
            if sel.count() == 0:
                return
            self._msg("Filtro: abrindo seletor de marcas…")
            sel.first.click(timeout=3_000)
            campo = page.locator(SELETORES["filtros"]["filtro_texto"])
            try:
                campo.first.wait_for(state="visible", timeout=3_000)
            except TimeoutError:
                page.wait_for_timeout(300)

            escolhidas: list[str] = []
            # SÓ o campo VISÍVEL é o do filtro de marcas (os outros
            # multiselects — "Todos os artigos", "Grupo de produtos" — têm o
            # input escondido; preencher eles = "não digita a marca")
            if campo.count() > 0:
                for marca in self.marcas:
                    self._checar_desbloqueio()
                    if time.time() > deadline:
                        self._msg("Filtro: tempo limite atingido durante a "
                                  "seleção das marcas.")
                        break
                    # Garante que o painel e o campo estão abertos. Se o painel
                    # fechou (ex.: marca anterior não encontrada), reabre.
                    try:
                        campo_vis = (campo.count() > 0 and
                                     campo.first.is_visible())
                    except Exception:
                        campo_vis = False
                    if not campo_vis:
                        try:
                            sel.first.click(timeout=3_000)
                            campo.first.wait_for(state="visible",
                                                 timeout=3_000)
                        except Exception:
                            self._msg(f"Filtro: painel não reabriu; "
                                      f"parando em '{marca}'.")
                            break
                    # Digitação confiável no PrimeNG: foca, limpa com Ctrl+A,
                    # preenche com fill (que substitui tudo) e, se o evento de
                    # filtragem não disparar, digita char a char.
                    try:
                        campo.first.click(timeout=2_000)
                        campo.first.press("Control+A")
                        campo.first.fill(marca)
                    except Exception:
                        try:
                            campo.first.type(marca)
                        except Exception:
                            continue
                    # Se o fill não disparou o filtro, as opções continuam
                    # mostrando a marca anterior — força redigitação.
                    opcao = self._achar_opcao_marca(marca)
                    if opcao is None and marca.strip():
                        try:
                            campo.first.fill("")
                            campo.first.press_sequential(
                                marca, delay=20)
                            opcao = self._achar_opcao_marca(marca)
                        except Exception:
                            pass
                    if opcao is None:
                        self._msg(f"Filtro: '{marca}' não apareceu nas opções.")
                        page.keyboard.press("Escape")
                        page.wait_for_timeout(200)
                        continue
                    if self._marcar_opcao(opcao, marca):
                        escolhidas.append(marca)
                    elif self._aplicar_marca_pela_url(opcao, marca):
                        # Plano B para o PrimeNG: ele já nos deu o ID da
                        # marca em `ta-value`; aplicar esse ID na rota é o
                        # mesmo estado que o checkbox produz, sem depender
                        # de foco/click no elemento visual.
                        escolhidas.append(marca)
            else:
                # sem campo: procura por aria-label nas opções já renderizadas
                alvo_map = {self._norm(m): m for m in self.marcas}
                opcoes = page.locator(SELETORES["filtros"]["opcao"])
                for i in range(opcoes.count()):
                    try:
                        a = self._norm(
                            opcoes.nth(i).get_attribute(
                                "aria-label", timeout=800) or "")
                    except Exception:
                        continue
                    if a in alvo_map:
                        if self._marcar_opcao(opcoes.nth(i), alvo_map[a]):
                            escolhidas.append(alvo_map[a])

            # O TecDoc atualiza a URL de forma assíncrona depois do checkbox.
            # Aguarda essa confirmação antes de fechar o overlay e ler a grid.
            if escolhidas:
                # O site atualiza a URL de forma assíncrona (às vezes leva
                # mais de 6s) — espera até ~16s, respeitando o orçamento.
                for _ in range(80):
                    if time.time() > deadline:
                        break
                    if "brands=" in page.url:
                        break
                    page.wait_for_timeout(200)
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            if escolhidas:
                self._msg(f"Filtro de marcas aplicado no site "
                          f"({', '.join(escolhidas)}).")
            else:
                self._msg("Filtro: nenhuma das marcas selecionadas existia "
                          "neste resultado.")
            # confirmação: o site expõe o filtro aplicado na URL (?brands=...)
            try:
                self._filtro_efetivado = "brands=" in page.url
            except Exception:
                self._filtro_efetivado = False
            # Retry: o checkbox às vezes não "pega" no clique do Playwright.
            # Se selecionou marcas mas a URL não mudou, reabre o overlay e
            # confere estado de cada opção; re-clica só nas desmarcadas.
            if escolhidas and not self._filtro_efetivado:
                self._msg("Filtro não refletiu na URL — tentando retry...")
                self._filtro_aplicado = False
                reiniciado = False
                try:
                    sel.first.click(timeout=3_000)
                    for marca in list(escolhidas):
                        # O overlay pode ser recriado ao voltar de segundo
                        # plano. Refiltra para não tentar clicar na opção da
                        # marca anterior (ou em uma lista vazia/desatualizada).
                        campo_retry = page.locator(
                            SELETORES["filtros"]["filtro_texto"]).first
                        try:
                            campo_retry.wait_for(state="visible", timeout=3_000)
                            campo_retry.focus()
                            campo_retry.fill(marca)
                            if campo_retry.input_value(timeout=1_000).strip() != marca:
                                campo_retry.press("Control+A")
                                campo_retry.press_sequential(marca, delay=20)
                        except Exception:
                            pass
                        opcao = self._achar_opcao_marca(marca)
                        if opcao is None:
                            continue
                        try:
                            marcado = self._check_marcado(opcao)
                        except Exception:
                            marcado = False
                        if not marcado:
                            if self._marcar_opcao(opcao, marca):
                                reiniciado = True
                            else:
                                self._msg(f"Filtro (retry): '{marca}' continuou "
                                          f"desmarcada após tentativas.")
                    if reiniciado:
                        for _ in range(50):
                            if time.time() > deadline:
                                break
                            if "brands=" in page.url:
                                break
                            page.wait_for_timeout(200)
                except Exception:
                    pass
                try:
                    self._filtro_efetivado = "brands=" in page.url
                except Exception:
                    self._filtro_efetivado = False
                page.keyboard.press("Escape")
                page.wait_for_timeout(250)
            if escolhidas and not self._filtro_efetivado:
                self._msg("ATENÇÃO: o filtro não refletiu na URL (?brands=). "
                          "Não vou clicar nos resultados para evitar 404.")
        except BuscaDestravada:
            # Não transforme o pedido do botão "Destravar" em uma falha de
            # filtro; ele precisa subir até a fila para reagendar o código.
            raise
        except Exception as exc:
            self._msg(f"Filtro de marcas falhou: {exc}")

    @staticmethod
    def _check_marcado(opcao) -> bool:
        """Descobre se a opção da marca está marcada no multiselect.

        O p-checkbox do PrimeNG pinta o .p-checkbox-box com a classe
        `p-highlight` (ou `.p-checkbox-checked` no layout antigo) quando
        selecionado. Alguns layouts marcam a PRÓPRIA linha (li) com
        `p-highlight` ou o atributo `aria-checked`. Verifica as três fontes.
        """
        # PrimeNG atual (como o da tela do usuário) expõe o estado no input
        # escondido. Ler este estado antes das classes visuais é importante:
        # a classe pode demorar um frame para ser atualizada ao voltar de
# segundo plano.
        try:
            inp = opcao.locator(SELETORES["filtros"]["check_input"]).first
            if inp.count() > 0:
                if inp.is_checked(timeout=800):
                    return True
                aria_input = (inp.get_attribute(
                    "aria-checked", timeout=800) or "").lower()
                if aria_input in ("true", "1", "selected"):
                    return True
        except Exception:
            pass
        try:
            box = opcao.locator(SELETORES["filtros"]["check"]).first
            if box.count() > 0:
                cls = box.get_attribute("class", timeout=800) or ""
                if "p-highlight" in cls or "p-checkbox-checked" in cls:
                    return True
        except Exception:
            pass
        try:
            if "p-highlight" in (opcao.get_attribute(
                    "class", timeout=800) or ""):
                return True
        except Exception:
            pass
        try:
            aria = (opcao.get_attribute(
                "aria-checked", timeout=800) or "").lower()
            return aria in ("true", "1", "selected")
        except Exception:
            return False

    def _marcar_opcao(self, opcao, marca: str) -> bool:
        """Marca a opção da marca no multiselect, tentando em ordem.

        Retorna True se a opção FICOU marcada (confirmado pelo estado real
        no DOM, não só pelo clique). Logga cada estratégia usada — assim o
        rastro mostra se o "click foi dado" ou se o "Enter" resolveu. É o
        feedback que faltava quando o filtro 'às vezes não vai'.
        """
        page = self._page
        tentativas = 0

        def confirmou() -> bool:
            # O site atualiza o modelo Angular assíncronamente. Em vez de
            # decidir 200 ms depois do click (o que falhava na imagem), dá
            # tempo e lê o input real + atributos do componente.
            for _ in range(8):
                if self._check_marcado(opcao):
                    return True
                page.wait_for_timeout(150)
            return False

        # Se a opção já ficou marcada em uma tentativa anterior/retry, não
        # clique outra vez: multiselect é toggle e um novo click a desmarca.
        if confirmou():
            self._msg(f"Filtro: '{marca}' já estava selecionada.")
            return True

        # 1) Marca o INPUT de verdade. `check` é mais confiável que clicar no
        # quadrado decorativo e o `force` é necessário porque o input é
        # propositalmente escondido pelo PrimeNG.
        try:
            inp = opcao.locator(SELETORES["filtros"]["check_input"]).first
            if inp.count() > 0:
                tentativas += 1
                inp.check(force=True, timeout=4_000)
                if confirmou():
                    self._msg(f"Filtro: '{marca}' selecionada (input real)")
                    return True
        except Exception:
            pass

        # 2) clique no checkbox visual (forma normal)
        try:
            box = opcao.locator(SELETORES["filtros"]["check"]).first
            if box.count() > 0:
                tentativas += 1
                # Nunca deixa um click normal consumir o timeout padrão de
                # 30 s. Se houver overlay/interceptação, cai rapidamente no
                # click forçado e nas demais alternativas abaixo.
                box.click(timeout=2_000)
                if confirmou():
                    self._msg(f"Filtro: '{marca}' selecionada (click checkbox)")
                    return True
        except Exception:
            pass
        # 3) clique no checkbox com force (ignore o intercept)
        try:
            box = opcao.locator(SELETORES["filtros"]["check"]).first
            if box.count() > 0:
                tentativas += 1
                box.click(force=True, timeout=2_000)
                if confirmou():
                    self._msg(f"Filtro: '{marca}' selecionada (force checkbox)")
                    return True
        except Exception:
            pass
        # 4) clique na própria linha da opção
        try:
            tentativas += 1
            opcao.click(force=True, timeout=2_000)
            if confirmou():
                self._msg(f"Filtro: '{marca}' selecionada (click na linha)")
                return True
        except Exception:
            pass
        # 5) Enter na opção focada
        try:
            tentativas += 1
            opcao.focus(timeout=2_000)
            page.keyboard.press("Enter")
            if confirmou():
                self._msg(f"Filtro: '{marca}' selecionada (Enter)")
                return True
        except Exception:
            pass
        # 6) Espaço na opção focada
        try:
            tentativas += 1
            opcao.focus(timeout=2_000)
            page.keyboard.press("Space")
            if confirmou():
                self._msg(f"Filtro: '{marca}' selecionada (Space)")
                return True
        except Exception:
            pass

        self._msg(f"Filtro: '{marca}' NÃO marcou após "
                  f"{tentativas} tentativa(s) — estado não confirmou.")
        return False

    def _aplicar_marca_pela_url(self, opcao, marca: str) -> bool:
        """Fallback sem UI para checkbox PrimeNG que não responde.

        Cada opção possui `ta-value` com o ID do fornecedor (HEPU, por
        exemplo, é 178). O TecDoc grava o mesmo ID em `brands=` na query e em
        `brands:` no fragmento do router Angular. Atualizar ambos evita que
        um clique perdido deixe a execução parada no overlay.
        """
        try:
            brand_id = (opcao.get_attribute("ta-value", timeout=800) or "").strip()
            if not brand_id or not brand_id.isdigit():
                return False
            return self._aplicar_marca_id_pela_url(brand_id, marca)
        except BuscaDestravada:
            raise
        except Exception as exc:
            self._msg(f"Filtro: fallback por URL falhou para '{marca}': {exc}")
            return False

    def _aplicar_marca_id_pela_url(self, brand_id: str, marca: str) -> bool:
        """Aplica um ID de fornecedor direto na rota do TecDoc."""
        try:
            page = self._page
            atual = urllib.parse.urlsplit(page.url)
            pares = urllib.parse.parse_qsl(atual.query, keep_blank_values=True)
            brands = []
            for chave, valor in pares:
                if chave == "brands":
                    brands.extend(v for v in valor.split(",") if v)
            if brand_id not in brands:
                brands.append(brand_id)
            pares = [(k, v) for k, v in pares if k != "brands"]
            pares.append(("brands", ",".join(brands)))

            fragmentos = atual.fragment.split(";") if atual.fragment else []
            valor_fragmento = "brands:" + ",".join(brands)
            for i, trecho in enumerate(fragmentos):
                if trecho.startswith("brands:"):
                    fragmentos[i] = valor_fragmento
                    break
            else:
                fragmentos.append(valor_fragmento)
            destino = urllib.parse.urlunsplit((
                atual.scheme, atual.netloc, atual.path,
                urllib.parse.urlencode(pares), ";".join(fragmentos),
            ))
            page.goto(destino, wait_until="domcontentloaded", timeout=12_000)
            self._msg(f"Filtro: '{marca}' aplicado pela URL (fallback).")
            return True
        except BuscaDestravada:
            raise
        except Exception as exc:
            self._msg(f"Filtro: fallback por URL falhou para '{marca}': {exc}")
            return False

    @staticmethod
    def _norm(txt: str) -> str:
        """Normaliza para comparação: minúsculas, sem acentos/trema, espaços.

        Ex.: 'Lemförder' -> 'lemforder', 'SWAG' -> 'swag'. Assim uma marca
        digitada sem o umlaut (ex.: 'lemforder') casa com a opção do site
        ('LEMFÖRDER'), evitando o 'às vezes vai, às vezes não'.
        """
        return _norm_texto(txt)

    def _achar_opcao_marca(self, marca: str):
        """Espera a opção com a marca aparecer no painel (via aria-label).

        Casa por nome exato, por prefixo de palavra e por palavra inteira no
        rótulo (ex.: 'trw' em 'zf trw', 'swag' em 'swag teile'), tudo
        normalizado (sem acentos/trema). Devolve a opção (locator) pronta
        para clicar no checkbox.
        """
        page = self._page
        alvo = self._norm(marca)
        palavras_alvo = alvo.split()
        for _ in range(30):  # até ~4,5s, com polling menor
            self._checar_desbloqueio()
            opcoes = page.locator(SELETORES["filtros"]["opcao"])
            for i in range(opcoes.count()):
                try:
                    rotulo = self._norm(
                        opcoes.nth(i).get_attribute(
                            "aria-label", timeout=800) or "")
                except Exception:
                    continue
                if rotulo == alvo or rotulo.startswith(alvo + " "):
                    return opcoes.nth(i)
                # palavra inteira dentro do rótulo (evita 'mahle' vs 'mahle x')
                if len(palavras_alvo) == 1 and \
                        alvo in rotulo.split() and len(alvo) >= 2:
                    return opcoes.nth(i)
            page.wait_for_timeout(150)
        return None

    def _garantir_catalogo(self) -> None:
        """Anti-bug: nunca digita código na tela de login.

        Antes de qualquer busca, garante que NÃO estamos na tela de login.
        Se estivermos (login Okta, post-logout, sessão expirada), volta pra raiz
        do catálogo e religa a sessão via garantir_login(); se não sair, aborta
        com erro claro em vez de digitar o código no campo de usuário/senha
        (bug antigo kkk).
        """
        if not self._esta_no_login():
            return
        self._msg("Sessão fora do catálogo — tentando recuperar o login...")
        # Navega de novo pra raiz do catálogo: do post-logout a SPA
        # redireciona pro Okta e o login automático roda; do Okta ainda em
        # sessão, cai direto no catálogo. (garantir_login também aguarda o
        # usuário concluir MFA manual se o login automático falhar.)
        self.garantir_login()
        if self._esta_no_login():
            ok = self._aguardar_fora_do_login(
                timeout_s=120.0, on_mensagem=self._msg)
            if not ok:
                raise RuntimeError(
                    "Não foi possível sair da tela de login. "
                    "Complete o login no navegador ou verifique as credenciais."
                )

    def _preencher_busca(self, codigo: str) -> None:
        page = self._page
        self._checar_desbloqueio()
        # Quando a janela fica em segundo plano o Chromium pode adiar a
        # atualização da SPA. Trazer a aba para frente não depende de foco do
        # teclado do usuário, mas evita reutilizar um input desmontado durante
        # esse intervalo.
        try:
            page.bring_to_front()
        except Exception:
            pass

        def localizar_campo():
            """Devolve um locator novo; Angular pode recriar o header."""
            return page.locator(SELETORES["busca"]["campo_texto"]).first

        # espera o campo da busca aparecer (header), não digita às cegas
        campo = localizar_campo()
        recarregado = False
        for _ in range(60):  # até 30s para o campo ficar visível
            self._checar_desbloqueio()
            try:
                if campo.is_visible():
                    break
            except Exception:
                pass
            # Atalho de velocidade: em vez de encarar 30s esperando o campo,
            # se ele não aparece em ~6s recarrega a raiz uma vez (recupera a
            # SPA de qualquer estado estranho) e continua verificando.
            if _ > 12 and not recarregado:
                recarregado = True
                self._msg("Campo de busca não visível — recarregando o catálogo")
                try:
                    page.goto(config.TECDOC_URL, wait_until="domcontentloaded")
                    page.wait_for_timeout(800)
                    campo = localizar_campo()
                except Exception:
                    pass
            time.sleep(0.5)
        else:
            raise BuscaNaoIniciadaError(
                f"Campo de busca não ficou visível. URL: {page.url}")

        def preencher_e_confirmar() -> bool:
            """Preenche e confirma o valor no input que está vivo agora.

            `fill` normalmente é suficiente, mas ocasionalmente o componente
            do TecDoc ignora seu evento após voltar de segundo plano. Nesse
            caso, Ctrl+A + digitação sequencial gera a mesma sequência de
            eventos de uma digitação manual. A leitura de volta impede seguir
            com o código anterior que ficou preso no campo.
            """
            nonlocal campo
            campo = localizar_campo()
            try:
                campo.wait_for(state="visible", timeout=4_000)
                campo.focus()
                campo.click(timeout=4_000)
                campo.fill(codigo)
                page.wait_for_timeout(150)
                if (campo.input_value(timeout=1_500).strip() == codigo):
                    return True
            except Exception:
                pass
            try:
                # Reobtém o locator: o primeiro fill pode ter feito Angular
                # trocar o nó do input.
                campo = localizar_campo()
                campo.focus()
                campo.press("Control+A")
                campo.press("Backspace")
                campo.press_sequential(codigo, delay=25)
                page.wait_for_timeout(250)
                return campo.input_value(timeout=1_500).strip() == codigo
            except Exception:
                return False

        if not preencher_e_confirmar():
            raise BuscaNaoIniciadaError(
                f"Campo de busca não aceitou o código '{codigo}'.")

        def ja_pesquisou():
            try:
                return ("query=" in page.url
                        and codigo.lower() in page.url.lower())
            except Exception:
                return False

        # dispara de várias formas até a busca realmente rodar
        for disparo in ("Enter", "sugestao", "botao"):
            if ja_pesquisou():
                break
            for _ in range(20):  # até ~10s de espera por forma
                self._checar_desbloqueio()
                if ja_pesquisou():
                    break
                if disparo == "Enter" and _ == 0:
                    try:
                        # Reconfirma antes do Enter: se houve troca de foco ou
                        # re-render, nunca envia Enter para outro controle.
                        if campo.input_value(timeout=1_000).strip() != codigo:
                            if not preencher_e_confirmar():
                                continue
                        campo.focus()
                        campo.press("Enter")
                    except Exception:
                        # Um novo input pode ter substituído o anterior entre
                        # focus e press; uma repetição controlada é segura.
                        try:
                            if preencher_e_confirmar():
                                campo.press("Enter")
                        except Exception:
                            pass
                elif disparo == "sugestao" and _ == 0:
                    try:
                        sugestao = page.locator(
                            "input-search-options-picker li[role='option'], "
                            "input-search-options-picker .dropdown-item, "
                            "[role='option']:has-text('Pesquisar'), "
                            "li:has-text('qualquer')"
                        ).filter(has_text=codigo).first
                        sugestao.click(timeout=4_000)
                    except Exception:
                        pass
                elif disparo == "botao" and _ == 0:
                    try:
                        page.locator(SELETORES["busca"]["botao"]).first \
                           .click(timeout=4_000)
                    except Exception:
                        pass
                time.sleep(0.5)
        if not ja_pesquisou():
            raise BuscaNaoIniciadaError(
                f"Busca do '{codigo}' não disparou. URL: {page.url}")
        page.wait_for_timeout(500)

    def buscar_codigo(self, codigo: str) -> PecaResultado:
        """Busca um código e devolve o resultado (API interceptada + fallback DOM)."""
        self._checar_desbloqueio()
        self._garantir_catalogo()  # anti-bug: nunca digita em tela de login
        page = self._page
        resultado = PecaResultado(codigo=codigo)

        self._ultima_resposta_direct_search = None
        self._ultimas_respostas_detalhe.clear()
        self._link4_pares.clear()
        self._link4_origem.clear()

        try:
            self._preencher_busca(codigo)
            page.wait_for_load_state("networkidle", timeout=1_200)
        except TimeoutError:
            pass
        except BuscaNaoIniciadaError as exc:
            self._msg(str(exc))
            resultado.observacao = str(exc)
            return resultado

        # espera a grid terminar de carregar a primeira busca
        self._aguardar_grid_estavel()
        self._rastro_abrir(f"[{codigo}] grid carregou")

        # Re-checa se o filtro de marcas está ativo na URL real do site.
        # IMPORTANTE: o site perde o brands= a cada nova busca, então o
        # filtro precisa ser REAPLICADO (e _filtro_efetivado recalibrado),
        # senão a validação de marca fica bypassada e abre artigo errado
        # ("artigo não encontrado" a partir do 2º código).
        if _APLICAR_FILTRO_MARCAS_SITE and self.marcas:
            try:
                url_atual = page.url.lower()
            except Exception:
                url_atual = ""
            tem_brands = "brands=" in url_atual
            self._filtro_efetivado = tem_brands
            if not tem_brands:
                if not self._grid_ja_tem_marcas():
                    # Filtro não está ativo na URL e a grid mostra outras
                    # marcas: precisa aplicar de verdade.
                    self._filtro_aplicado = False  # permite reaplicar no site
                    self._aplicar_filtros_marca()
                    # Espera dinâmica: para quando a grid mostrar a(s) marca(s)
                    # selecionada(s) — nada de networkidle cego + timeout de 45s.
                    self._aguardar_grid_filtrada(tempo_max_s=8.0)
                else:
                    # Atalho: resultado único / todos da marca alvo. Aplicar o
                    # filtro do site não muda nada e é aí que o fluxo travava.
                    self._filtro_efetivado = True
                    self._filtro_aplicado = True
                    self._rastro_abrir(
                        f"[{codigo}] grid já contém apenas a(s) marca(s) "
                        f"alvo — filtro do site pulado.")
            else:
                self._rastro_abrir(
                    f"[{codigo}] filtro de marcas já ativo na URL")

        # Cachea a URL da busca AGORA, enquanto ainda tem groups= e brands=.
        # Ao abrir o detalhe a SPA reescreve a URL (o groups= some) e a
        # navegação direta montaria a URL do artigo com groups=1 (default),
        # que o site às vezes trata como "artigo não encontrado".
        try:
            self._url_ultima_busca = page.url
        except Exception:
            self._url_ultima_busca = ""

        # ---- 1) API + detalhe DOM ------------------------------------------
        parser = _ParserApi(resultado, self.marcas)
        ok = parser.extrair(self._ultima_resposta_direct_search)
        if (ok and resultado.observacao.startswith(("Nenhum resultado",))):
            self._msg(f"[{codigo}] sem resultado; seguindo para o próximo.")
            return resultado
        if ok and not resultado.observacao.startswith(("Nada nas marcas",)):
            if not parser.tenha_dados_faltando:
                # A API identifica os candidatos, mas os dados que a extensão
                # antiga extraía (GTIN, OE e aplicações) só existem no detalhe.
                # Portanto, não encerra aqui: abre a linha correta enquanto a
                # página ainda está viva.
                self._rastro_abrir(f"[{codigo}] API encontrou candidatos; abrindo detalhe")
                linhas = page.locator(".ag-row[row-id], table tbody tr, "
                                      ".article-row, .result-row")
                if linhas.count() > 0:
                    self._extrair_dom(resultado)
                    return resultado
                self._enriquecer_xref(resultado)
                return resultado

        # ---- 2) fallback DOM ------------------------------------------------
        self._rastro_abrir(f"[{codigo}] vai pro caminho DOM")
        self._extrair_dom(resultado)
        return resultado

    def _enriquecer_xref(self, resultado: PecaResultado) -> None:
        """Usa as respostas de detalhes/xref já capturadas (se houver)."""
        xrefs: list[tuple[str, str | None]] = []
        for corpo in self._ultimas_respostas_detalhe:
            for item in _todos_caminhos(corpo, ("articleNumber", "articleNo")):
                item = _limpar_codigo(item)
                if item and item.upper() != resultado.codigo.upper():
                    marca = _caminho(corpo, CAMPO_MARCA)
                    xrefs.append((item, marca if isinstance(marca, str) else None))
        resultado.cross_refs = xrefs or resultado.cross_refs

    def _extrair_dom(self, resultado: PecaResultado) -> None:
        page = self._page
        try:
            if page.locator(SELETORES["resultado"]["lista"]).count() == 0:
                resultado.observacao = "Nenhum resultado encontrado"
                return
            # Em AG-Grid, localizar os rows diretamente evita incluir o
            # wrapper/container como uma linha e sobreviver ao re-render.
            linhas = page.locator(
                ".ag-row[row-id], table tbody tr, .article-row, .result-row"
            )
        except Exception:
            resultado.observacao = "Erro ao ler resultados (seletores DOM)"
            return

        total = linhas.count()
        if total == 0:
            resultado.observacao = "Nenhum resultado encontrado"
            return

        # Espera a coluna de marca renderizar conteúdo: a AG-Grid às vezes
        # mostra as linhas vazias (skeleton) e a marca vem depois. Sem isso
        # a leitura marca "0 na marca(s)" mesmo com resultado na tela.
        for _ in range(20):
            algum = any(
                (linhas.nth(i).locator(
                    "[col-id='description'], .brand, .brand-name").count()
                 > 0 and (linhas.nth(i).inner_text(timeout=800).strip()))
                for i in range(min(total, 5))
            )
            if algum:
                break
            page.wait_for_timeout(500)
        else:
            self._rastro_abrir(
                f"[{resultado.codigo}] grid visível mas coluna de marca "
                f"vazia após 10s")

        candidatas: list[tuple[int, PecaResultado]] = []
        ilegiveis = 0
        for i in range(total):
            linha = linhas.nth(i)
            try:
                texto_linha = linha.inner_text(timeout=2_000)
                marca = self._cel_texto(
                    linha, "resultado", "cel_marca", texto_linha
                )
            except Exception:
                texto_linha = ""
                marca = ""
            if not marca and texto_linha:
                partes = [p.strip() for p in texto_linha.splitlines() if p.strip()]
                marca = partes[1] if len(partes) > 1 else ""
            if not marca:
                if not self._filtro_efetivado:
                    ilegiveis += 1
                    continue
            if self.marcas and not self._marca_bate(marca):
                if self._filtro_efetivado:
                    pass
                else:
                    # Seletor de marca falhou/leu célula errada (rastro mostra
                    # 'marca=1-GNC'). A marca escolhida costuma aparecer no
                    # texto inteiro da linha — procura palavra normalizada.
                    texto_explorado = " ".join(
                        p.strip() for p in texto_linha.splitlines() if p.strip()
                    )
                    if texto_explorado and self._marca_no_texto(texto_explorado):
                        marca = self._marca_candidata_no_texto(texto_explorado)
                    else:
                        continue
            peca = PecaResultado(codigo=resultado.codigo, marca=marca)
            peca.descricao = self._cel_texto(linha, "resultado",
                                             "cel_descricao", texto_linha)
            peca.disponivel = self._cel_booleano(linha, "resultado",
                                                 "cel_disponivel", "")
            candidatas.append((i, peca))
        self._rastro_abrir(
            f"[{resultado.codigo}] grid lida: {total} linhas, "
            f"{len(candidatas)} na marca(s), {ilegiveis} ilegíveis")

        if not candidatas:
            resultado.observacao = (
                f"Nada nas marcas: {', '.join(self.marcas)}"
                if self.marcas else "Nada encontrado"
            )
            self._msg(resultado.observacao)
            return
        # A grade já vem ordenada pelo TecDoc após o filtro. Preserve essa
        # ordem: o primeiro candidato é exatamente o primeiro resultado
        # visível que o usuário espera abrir.
        idx_linha, melhor = candidatas[0]
        if self._descricao_valida(melhor.descricao):
            resultado.descricao = melhor.descricao
        # else: a leitura da grid pegou cabeçalho/célula errada (ex.: 'N° OE'),
        # mantém a descrição que a API e o detalhe já preencheram
        # O seletor de marca às vezes lê a célula errada (articleNo no lugar
        # do nome da marca — ex. 'P569' em vez de 'HEPU'). Com o filtro
        # efetivo, a grid só contém a(s) marca(s) escolhida(s), então o valor
        # da célula pode ser ignorado: usa self.marcas[0].
        if (self._filtro_efetivado and self.marcas
                and not self._marca_bate(melhor.marca)):
            resultado.marca = self.marcas[0]
        else:
            resultado.marca = melhor.marca
        resultado.disponivel = melhor.disponivel
        marca_confirmada = (
            not self.marcas or self._marca_bate(resultado.marca)
        )
        if (self._filtro_aplicado and not self._filtro_efetivado
                and not marca_confirmada and not resultado.observacao):
            resultado.observacao = (
                "Filtro de marcas não refletiu no site — detalhe não aberto "
                "(resultado sem confirmação de marca; evitando 404)."
            )
            self._msg(resultado.observacao)
            return
        try:
            linhas.nth(idx_linha).scroll_into_view_if_needed(timeout=3_000)
        except Exception:
            pass
        try:
            row_id = linhas.nth(idx_linha).get_attribute(
                "row-id", timeout=800) or ""
        except Exception:
            row_id = ""
        self._rastro_abrir(
            f"[{resultado.codigo}] abrindo primeiro resultado: "
            f"marca={resultado.marca} row={row_id}"
        )
        self._abrir_detalhe(linhas.nth(idx_linha), resultado)

    def _marca_bate(self, marca: str) -> bool:
        """Marca do resultado x marcas selecionadas (tolerante a prefixo).

        A grid mostra 'FEBI BILSTEIN' mas o usuário escolhe 'Febi'; então
        'febi' casa com 'febi bilstein' (startswith por palavra). A confirmação
        final é o sumário da página do artigo.
        """
        return _marca_casa(marca, self.marcas)

    def _marca_no_texto(self, texto: str) -> bool:
        """True se alguma marca selecionada aparece como palavra no texto.

        Fallback quando a coluna de marca da AG-Grid é lida com o seletor
        errado (rastro: 'marca=1-GNC'). Normaliza o texto e procura a marca
        por palavra inteira ou prefixo de palavra (mesma semântica do
        _marca_bate, agora contra o texto completo da linha).
        """
        if not texto or not self.marcas:
            return False
        norm = _norm_texto(texto)
        palavras = [p for p in norm.split() if p]
        for b in self.marcas:
            b = _norm_texto(b)
            if not b:
                continue
            for palavra in palavras:
                if b in palavra or (len(b) >= 2 and palavra.startswith(b)):
                    return True
        return False

    def _marca_candidata_no_texto(self, texto: str) -> str:
        """Devolve a marca selecionada que confirma no texto da linha."""
        norm = _norm_texto(texto)
        palavras = [p for p in norm.split() if p]
        for b in self.marcas:
            b_norm = _norm_texto(b)
            if not b_norm:
                continue
            if any(b_norm in p or (len(b_norm) >= 2 and p.startswith(b_norm))
                   for p in palavras):
                return b
        return ""

    @staticmethod
    def _descricao_valida(texto: str) -> bool:
        """True se o texto é uma descrição de artigo de verdade.

        A leitura de célula da grid às vezes cai em cabeçalhos ('N° OE',
        'Marca', 'Estado') ou no número do artigo ('P569', 'TM7134') quando o
        layout renderiza só a 1ª linha. Uma descrição real tem palavras em
        caixa mista (ex.: 'Filtro de óleo'); código/cabeçalho é CAIXA ALTA ou
        token único sem vogal.
        """
        t = (texto or "").strip().rstrip(".:-")
        if not t or len(t) < 3:
            return False
        cab = {
            "n° oe", "nº oe", "numero oe", "número oe", "no oe",
            "descricao", "descrição", "codigo", "código", "marca",
            "artigo", "estado", "disponibilidade", "quantidade", "qtd",
        }
        if t.lower().strip() in cab:
            return False
        # token único sem nenhuma vogal = código (P569, TM7134), não descrição
        if len(t.split()) == 1:
            if not any(ch.lower() in "aeiouáéíóúãõâêîôûàèìòù" for ch in t):
                return False
        # cabeçalho/nome de coluna em caixa alta vazou como fallback
        if t.isupper():
            return False
        return True

    @staticmethod
    def _cel_texto(linha, etapa, campo, fallback_texto: str) -> str:
        try:
            cel = linha.locator(SELETORES[etapa][campo]).first
            if cel.count() > 0:
                t = cel.inner_text(timeout=1_500).strip()
                if t:
                    return t[:200]
        except Exception:
            pass
        if fallback_texto:
            return fallback_texto.splitlines()[0].strip()[:80]
        return ""

    @staticmethod
    def _cel_booleano_prov_negativo(val: str) -> bool:
        """True se o texto da coluna 'Estado do artigo' indica DISPONÍVEL.

        Baseia-se na coluna real do TecDoc (stateText -> 'Normal', etc.).
        Nunca marca 'indisponível' por falta de informação.
        """
        val = (val or "").strip().lower()
        if not val:
            return True
        neg = ("descontinuad", "discontinued", "anulad", "cancelled",
               "stopped", "auslauff", "schluss", "fora de linha", "ng")
        for n in neg:
            if n in val:
                return False
        return True

    @staticmethod
    def _cel_booleano(linha, etapa, campo, texto: str) -> bool:
        try:
            cel = linha.locator(SELETORES[etapa][campo]).first
            if cel.count() > 0:
                return TecDocAutomator._cel_booleano_prov_negativo(
                    cel.inner_text(timeout=1_500))
        except Exception:
            pass
        # fallback: sem informação, assume disponível (não gera falso "Não")
        return True

    def _rastro_abrir(self, texto: str) -> None:
        try:
            saida = config.data_dir() / "erros"
            saida.mkdir(parents=True, exist_ok=True)
            url = self._page.url if self._page else ""
            with open(saida / "rastro.txt", "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%H:%M:%S')} {texto}\n  url: {url}\n")
        except Exception:
            pass

    def _rastrear_navegacoes(self) -> None:
        """Grava toda mudança de URL principal em data/erros/rastro.txt.

        Quando o site "redirecionar pra outro link", o log mostra para qual
        URL e em que momento — e o dump imediato captura o motivo. """
        try:
            self._page.on("framenavigated", self._ao_navegar)
        except Exception:
            pass
        try:
            self._page.on("console", self._ao_console)
        except Exception:
            pass
        try:
            self._page.on("request", self._ao_request)
        except Exception:
            pass

    def _ao_console(self, msg) -> None:
        try:
            tipo = msg.type
            if tipo in ("error", "warning"):
                self._rastro_abrir(f"console[{tipo}]: {msg.text[:180]}")
        except Exception:
            pass

    def _ao_request(self, request) -> None:
        try:
            if request.resource_type == "document":
                self._rastro_abrir(
                    f"REQ documento: {request.method} {request.url[:200]}")
        except Exception:
            pass

    def _ao_navegar(self, frame) -> None:
        try:
            if isinstance(self._page, Page) and frame == self._page.main_frame:
                url = ""
                try:
                    url = frame.url
                except Exception:
                    url = ""
                try:
                    self._rastro_abrir(f"NAVEGOU -> {url[:220]}")
                except Exception:
                    pass
                # O callback roda dentro do evento de navegação. Não chame
                # screenshot/content aqui: isso reentra no Sync API e pode
                # cancelar a navegação no Playwright.
                if ("catalog-not-found" in url
                        or url.rstrip("/") == "https://web.tecalliance.net"):
                    self._rastro_abrir("redirect suspeito detectado")
        except Exception:
            pass

    def _abrir_detalhe(self, linha, resultado: PecaResultado) -> None:
        """Abre a página do artigo SEM clicar na grid.

        O clique na célula de descrição disparava uma navegação para a RAIZ
        do site (https://web.tecalliance.net/) em vez do artigo — caindo em
        `catalog-not-found` e redirecionando pro Okta. Então agora a gente
        monta a URL do artigo direto (brandId do filtro + articleNo da linha)
        e navega; se falhar, guarda a evidência.
        """
        self._rastro_abrir(
            f"[{resultado.codigo}] abrir detalhe (navegação direta)")
        if not self._abrir_detalhe_direto(linha, resultado):
            # falhou: registra evidência do que aconteceu (404/redirect)
            self._dump_erro_detalhe(resultado)

    def _aguardar_detalhe(self, tentativas: int) -> bool:
        """Aguarda a página do artigo renderizar (sumario ou tabela OE).

        Dá um respiro inicial porque o shell do SPA (i18n, config, auth)
        costuma demorar mais que a checagem imediata.
        """
        page = self._page
        page.wait_for_timeout(700)
        for _ in range(tentativas):
            try:
                if (page.locator(SELETORES["detalhe"]["sumario"]).count() > 0
                        or page.locator(SELETORES["detalhe"]["lista_oe"]).count() > 0):
                    return True
            except Exception:
                pass
            time.sleep(0.5)
        return False

    def _abrir_detalhe_direto(self, linha, resultado: PecaResultado) -> bool:
        """Navega direto para a página do artigo, montando a URL do site.

        Em vez de depender do clique na grid (que está caindo no lugar errado),
        monta `parts/{brandId}/{articleNo}/detail` usando a identidade da
        própria linha. O `row-id` é a fonte correta porque a URL pode ainda
        conter um `brands=` de uma seleção anterior.
        """
        page = self._page
        article_no = ""
        href_artigo = ""
        row_brand_id = ""
        try:
            row_id = linha.get_attribute("row-id", timeout=800) or ""
            match = re.search(r"\[(\d+)\]-\[(.+)\]", row_id)
            if match:
                row_brand_id, article_no = match.groups()
            cel = linha.locator("[col-id='articleNo']").first
            if cel.count() > 0:
                article_no = article_no or cel.inner_text(timeout=800).strip()
                # o próprio site renderiza o artigo como link — o href dele é
                # a URL CERTA (sem adivinhar nada)
                anc = cel.locator("a").first
                if anc.count() > 0:
                    href_artigo = (anc.get_attribute(
                        "href", timeout=800) or "").strip()
            article_no = _limpar_codigo(article_no)
        except Exception:
            pass
        if not article_no and not href_artigo:
            self._msg("Detalhe direto: não achei o número do artigo na linha.")
            return False

        try:
            # SPA às vezes esvazia/reescreve a URL (groups= some) entre a busca e
            # abertura do detalhe. Usa a URL capturada no fim da busca; se
            # estiver vazia (ex.: retry pós-reconexão), cai pra page.url.
            url_atual = self._url_ultima_busca or page.url
            p = urllib.parse.urlsplit(url_atual)
            params = urllib.parse.parse_qs(p.query)
            # O row-id identifica o artigo exibido: [brandId]-[articleNo].
            # Só usa a URL quando uma versão antiga do DOM não o informa.
            brand_id = row_brand_id
            if not brand_id:
                raw = params.get("brands", [""])
                for value in raw:
                    for part in value.split(","):
                        if part.strip().isdigit():
                            brand_id = part.strip()
                            break
                    if brand_id:
                        break
            if not brand_id:
                match = re.search(r"brands:(\d+)", url_atual)
                brand_id = match.group(1) if match else ""
            if not brand_id:
                try:
                    match = re.search(r"\[(\d+)\]",
                                      linha.get_attribute(
                                          "row-id", timeout=800) or "")
                    brand_id = match.group(1) if match else ""
                except Exception:
                    brand_id = ""
            query = params.get("query", [resultado.codigo])[0]
            groups = params.get("groups", [""])[0]
            # Na busca com vários resultados o site NÃO informa groups na
            # URL. O valor default "1" causa o detalhe a abrir vazio/errado.
            # Sem groups real, monta URL sem o parâmetro — o site resolve
            # o artigo por brandId + articleNo direto.
            tem_groups = bool(groups) and groups != "1"
            if not brand_id:
                self._msg("Detalhe direto: sem brandId na URL (filtro não "
                          "refletiu).")
                return False

            novo_caminho = f"/tecdoc/pt/parts/{brand_id}/{article_no}/detail"
            nova_url = (f"{p.scheme}://{p.netloc}{novo_caminho}"
                        f"?query={urllib.parse.quote(query)}&numberType=1")
            if tem_groups:
                nova_url += f"&groups={urllib.parse.quote(groups)}"
            nova_url += self._fragmento_detalhe(
                url_atual, brand_id, article_no, query,
                groups if tem_groups else "")
            # se a própria célula expõe o href do artigo, usa ELE (fonte da
            # verdade do site); o montado acima é o fallback
            if href_artigo:
                if href_artigo.startswith("/"):
                    href_artigo = f"{p.scheme}://{p.netloc}{href_artigo}"
                self._rastro_abrir(f"goto pelo href da célula: "
                                   f"{href_artigo[:200]}")
                page.goto(href_artigo, wait_until="domcontentloaded")
            else:
                self._rastro_abrir(f"goto direto: {nova_url[:200]}")
                page.goto(nova_url, wait_until="domcontentloaded")
            page.wait_for_timeout(400)
            # se o site derrubou na raiz/catálogo inexistente, não insiste
            if ("catalog-not-found" in page.url
                    or page.url.rstrip("/") == "https://web.tecalliance.net"):
                self._rastro_abrir(
                    f"[{resultado.codigo}] goto direto caiu fora do catálogo "
                    f"({page.url[:180]}).")
                return False
            ok = self._aguardar_detalhe(40)
            if not ok:
                # SPA às vezes ignora o primeiro goto (cache/timing); recarrega
                # a mesma URL uma única vez antes de desistir
                self._rastro_abrir(
                    f"[{resultado.codigo}] goto direto não renderizou; "
                    f"recarregando: {page.url[:180]}")
                try:
                    page.reload(wait_until="domcontentloaded")
                except Exception:
                    pass
                page.wait_for_timeout(500)
                ok = self._aguardar_detalhe(50)
                self._rastro_abrir(f"[{resultado.codigo}] retry "
                                   f"{'ok' if ok else 'continua sem renderizar'}.")
            if not ok:
                self._rastro_abrir(
                    f"[{resultado.codigo}] goto direto não abriu o artigo.")
                return False
            page.wait_for_timeout(300)
            self._extrair_detalhe(resultado)
            return True
        except Exception as exc:
            self._msg(f"Detalhe direto falhou: {exc}")
            return False

    def _fragmento_detalhe(self, url_atual: str, brand_id: str,
                           article: str, query: str, groups: str) -> str:
        """Reconstrói o fragmento de rota que o site usa (#@brc/... /detail:...).

        Copia a parte de busca do fragmento atual (mantém a codificação do
        título) e acrescenta o segmento /detail:... com os parâmetros.
        `groups` vazio significa que a busca não tinha grupo definido (caso
        dos múltiplos resultados) — omite o ;groups: também no fragmento.
        """
        try:
            fr = urllib.parse.urlsplit(url_atual).fragment
            if not fr:
                return ""
            if not fr.startswith("@"):
                fr = "@" + fr.lstrip("#")
            # raiz = "@brc/search:...;query:..."
            idx = fr.find(";query:")
            raiz = fr[:idx] if idx != -1 else fr
            saida = ("#" + raiz
                     + ";query:" + urllib.parse.quote(str(query))
                     + ";brands:" + str(brand_id))
            if groups:
                saida += ";groups:" + urllib.parse.quote(str(groups))
            saida += ("/detail:" + str(article)
                      + ";brandId:" + str(brand_id)
                      + ";articleNo:" + str(article)
                      + ";query:" + urllib.parse.quote(str(query))
                      + ";numberType:1")
            if groups:
                saida += ";groups:" + urllib.parse.quote(str(groups))
            return saida
        except Exception:
            return ""

    def _dump_erro_detalhe(self, resultado: PecaResultado) -> None:
        try:
            saida = config.data_dir() / "erros"
            saida.mkdir(parents=True, exist_ok=True)
            carimbo = time.strftime("%Y%m%d_%H%M%S")
            url = self._page.url if self._page else ""
            (saida / f"erro_{carimbo}.txt").write_text(
                f"codigo: {resultado.codigo}\n"
                f"marca: {resultado.marca}\n"
                f"url: {url}\n"
                f"marcas app: {', '.join(self.marcas)}\n"
                f"filtro_aplicado: {self._filtro_aplicado} | "
                f"filtro_efetivado: {self._filtro_efetivado}\n",
                encoding="utf-8",
            )
            (saida / f"erro_{carimbo}.html").write_text(
                self._page.content(), encoding="utf-8")
        except Exception:
            pass
        self._msg(f"Detalhe não abriu (possível 404). Evidência em "
                  f"data/erros/erro_{carimbo}.*")

    def _extrair_detalhe(self, resultado: PecaResultado) -> None:
        """Lê o sumário do artigo e a tabela 'Número OE' (cross-references)."""
        page = self._page
        # ---- resumo (Marca / Número do artigo / Grupo de produtos) ----
        try:
            sumario: dict[str, str] = {}
            cont = page.locator(SELETORES["detalhe"]["sumario"]).first
            rows = cont.locator(SELETORES["detalhe"]["linha_sumario"])
            for i in range(rows.count()):
                r = rows.nth(i)
                rot = r.locator(SELETORES["detalhe"]["cel_rotulo"]).first
                val = r.locator(SELETORES["detalhe"]["cel_valor"]).first
                try:
                    if rot.count() > 0 and val.count() > 0:
                        sumario[rot.inner_text(timeout=800).strip()] = \
                            val.inner_text(timeout=800).strip()
                except Exception:
                    pass
            # O componente pode mudar de wrapper, mas o HTML da extensão
            # antiga permanece estável: th[scope=row] seguido por td.
            for i in range(page.locator("th[scope='row']").count()):
                th = page.locator("th[scope='row']").nth(i)
                rotulo = th.inner_text(timeout=800).strip()
                td = th.locator("xpath=following-sibling::td[1]")
                if td.count() > 0:
                    sumario[rotulo] = td.inner_text(timeout=800).strip()
            marca = next((v for k, v in sumario.items()
                          if self._norm(k) == "marca"), "")
            desc = next((v for k, v in sumario.items()
                         if self._norm(k) == "grupo de produtos"), "").strip()
            if marca:
                resultado.marca = marca
            if len(desc) >= 3:
                resultado.descricao = desc
        except Exception:
            pass

        self._extrair_gtin(resultado)

        self._extrair_aplicacoes(resultado)
        self._extrair_veiculos(resultado)

        # ---- validação: abriu o artigo certo? ----
        # Se o sumário diz uma marca que NÃO está entre as selecionadas,
        # o clique pegou a linha errada (causa típica do 404/nada).
        if (resultado.marca
                and self.marcas
                and not self._marca_bate(resultado.marca)):
            self._rastro_abrir(
                f"[{resultado.codigo}] ABRIU ARTIGO FORA DAS MARCAS: "
                f"'{resultado.marca}' (marcas do app: {self.marcas})")
            self._msg(f"ATENÇÃO: abriu artigo de '{resultado.marca}' — fora "
                      f"das marcas selecionadas.")
        if any(s in page.url.lower() for s in ("404", "not-found", "nao-existe")):
            self._dump_erro_detalhe(resultado)

        # ---- estado do artigo (disponibilidade) ----
        try:
            est = page.locator(SELETORES["detalhe"]["estado"]).first
            if est.count() > 0:
                t = est.inner_text(timeout=800)
                m = re.search(r":\s*([^\n]+)", t)
                val = (m.group(1).strip() if m else t.strip())
                if val:
                    resultado.disponivel = \
                        TecDocAutomator._cel_booleano_prov_negativo(val)
        except Exception:
            pass

        # ---- referências OE (cross-references) ----
        xrefs: list[tuple[str, str | None]] = []
        try:
            rows = page.locator(
                "part-detail-v2-oe-table tr[ta-name='oe-number'], "
                "tr[ta-name='oe-number']"
            )
            for i in range(rows.count()):
                r = rows.nth(i)
                try:
                    cod = (r.get_attribute("ta-value", timeout=800) or "").strip()
                except Exception:
                    cod = ""
                if not cod:
                    try:
                        cod = r.locator(SELETORES["detalhe"]["cel_oe_codigo"]) \
                              .first.inner_text(timeout=800).strip()
                    except Exception:
                        cod = ""
                info = ""
                try:
                    info = r.locator(SELETORES["detalhe"]["cel_oe_info"]) \
                           .first.inner_text(timeout=800).strip()
                except Exception:
                    pass
                if cod:
                    cod = _limpar_codigo(cod)
                    info = info or None
                    if not any(ex_cod == cod for ex_cod, _ in xrefs):
                        xrefs.append((cod, info))
        except Exception:
            pass
        resultado.cross_refs = xrefs or resultado.cross_refs

    def _extrair_gtin(self, resultado: PecaResultado) -> None:
        """Extrai o GTIN/EAN do artigo por várias estratégias (reforçado).

        O GTIN é carregado de forma assíncrona e nem sempre está renderizado
        na primeira leitura — então faz POLLING: tenta achar, espera um pouco
        e repete até encontrar (ou estourar o timeout). Evita o caso de pegar
        no 1º artigo e não no 2º por causa de timing.
        """
        page = self._page

        def _texto(el, *args) -> str:
            try:
                # timeout padrão curto: sem isso cada leitura espera 30s se
                # o nó destaca durante o polling do GTIN
                return (el.inner_text(*args, timeout=800) or "").strip()
            except Exception:
                return ""

        def _todos(loc) -> list:
            """Converte locator em lista de elementos (Playwright não itera locator)."""
            try:
                return loc.all()
            except Exception:
                out: list = []
                n = loc.count()
                for i in range(n):
                    out.append(loc.nth(i))
                return out

        def _coletar() -> list[str]:
            """Roda as 4 estratégias de uma vez e devolve os textos candidatos."""
            cand: list[str] = []

            # 1) th[scope='row'] / th com rótulo GTIN/EAN e td irmão
            for th in _todos(page.locator(
                "th[scope='row'], part-detail-v2-summary-table th"
            )):
                rotulo = self._norm(_texto(th))
                if any(rotulo.startswith(r) for r in
                       ("gtin", "ean", "código de barra", "codigo de barra")):
                    td = th.locator("xpath=following-sibling::td[1]")
                    v = _texto(td.first) if td.count() else ""
                    if v:
                        cand.append(v)

            # 2) elemento de rótulo com "GTIN"/"EAN" e o próximo irmão
            if not cand:
                for sel in ("dt", "label", ".label", "th"):
                    for el in _todos(page.locator(sel)):
                        rotulo = self._norm(_texto(el))
                        if rotulo and any(rotulo.startswith(r) for r in
                                          ("gtin", "ean")):
                            irmao = el.locator(
                                "xpath=following-sibling::*[1]").first
                            v = _texto(irmao) if irmao.count() else ""
                            if v:
                                cand.append(v)
                            pai = el.locator("xpath=..").first
                            if pai.count():
                                try:
                                    for t in pai.locator(
                                            "td, .p-component, div"):
                                        t2 = _texto(t)
                                        if t2:
                                            cand.append(t2)
                                except Exception:
                                    pass
                            break
                    if cand:
                        break

            # 3) atributos / itemprop
            if not cand:
                for atr in ("itemprop", "data-gtin", "data-ean"):
                    for el in _todos(page.locator(f"[{atr}]")):
                        try:
                            v_attr = el.get_attribute(atr, timeout=800) or ""
                        except Exception:
                            continue
                        rotulo = self._norm(v_attr)
                        if rotulo.startswith("gtin") or rotulo in (
                                "ean", "gtin13"):
                            pai = el.locator("xpath=..").first
                            v = _texto(pai) if pai.count() else ""
                            if v:
                                cand.append(v)
                            v2 = _texto(pai.locator(
                                "td, .p-component, div").first) \
                                if pai.count() else ""
                            if v2:
                                cand.append(v2)
                    if cand:
                        break

            # 4) fallback: número "parecido com GTIN" no texto do corpo
            if not cand:
                todos = _texto(page.locator("body"))
                match = re.search(
                    r"GTIN[:\s]*([0-9]{8,14})", todos, re.IGNORECASE)
                if match:
                    cand.append(match.group(1))
            return cand

        def _valor_valido(cand: list[str]) -> str:
            melhor = ""
            for raw in cand:
                digitos = re.sub(r"[^0-9]", "", (raw or "").strip())
                # GTIN usual: 8, 12, 13 ou 14 dígitos
                if len(digitos) in (8, 12, 13, 14) and digitos != melhor:
                    melhor = digitos
                    break
            return melhor

        melhor = ""
        # polling: até ~4s (8 tentativas a cada 500ms) enquanto a página
        # carrega o resumo do artigo. Para antes se já achou.
        for _ in range(8):
            melhor = _valor_valido(_coletar())
            if melhor:
                break
            page.wait_for_timeout(500)

        if melhor:
            resultado.gtin = melhor
            self._msg(f"[{resultado.codigo}] GTIN: {melhor}")
        else:
            self._msg(f"[{resultado.codigo}] GTIN: não encontrado")

    def _extrair_aplicacoes(self, resultado: PecaResultado) -> None:
        """Percorre todas as marcas do seletor "Número OE" e mescla os códigos.

        O autocomplete (``p-autocomplete``) do cabeçalho da tabela "Número OE"
        abre pelo botão de dropdown (``button.p-autocomplete-dropdown``) e lista
        cada marca como um ``li[role=option]`` (ex.: JAGUAR, LAND ROVER).
        Para cada marca disponível, clicamos nela e lemos os códigos OE (primeira
        célula de cada linha da tabela "Número OE" que contém o autocomplete).
        O carregamento é assíncrono, então faz POLLING até as células
        renderizarem — sem isso "alguns códigos de aplicação não vinham".
        Códigos repetidos são mesclados (deduplicados) com os já existentes.
        """
        page = self._page
        try:
            # ancora na tabela "Número OE" pra não pegar outro p-autocomplete
            # da página por engano; se ela não tiver autocomplete, cai pro
            # primeiro visível (comportamento antigo).
            tabela = page.locator(SELETORES["detalhe"]["lista_oe"]).first
            # a referência ("Número OE") às vezes monta DEPOIS do sumário do
            # artigo: espera até ~3s antes de desistir (evita ler vazio e
            # depois travar em outra etapa sem referência).
            for _ in range(10):
                if (tabela.count() > 0
                        and tabela.locator("p-autocomplete").count() > 0):
                    break
                page.wait_for_timeout(300)
            if tabela.count() == 0 or \
                    tabela.locator("p-autocomplete").count() == 0:
                tabela = page.locator("p-autocomplete").first \
                    .locator("xpath=ancestor::table").first
            if tabela.count() == 0:
                self._rastro_abrir(
                    f"[{resultado.codigo}] referência (Número OE) não "
                    f"disponível na página.")
                return
            ac = tabela.locator("p-autocomplete").first
            if ac.count() == 0:
                return
            botao = ac.locator("button.p-autocomplete-dropdown").first
            if botao.count() == 0:
                return

            def _abrir() -> None:
                try:
                    botao.click(timeout=2_500)
                except Exception:
                    try:
                        botao.click(force=True, timeout=1_500)
                    except Exception:
                        inp = ac.locator("input").first
                        if inp.count() and inp.first.is_enabled():
                            inp.click(timeout=2_500)
                page.wait_for_timeout(150)

            opcoes = page.locator(
                "li.p-autocomplete-item[role='option']:visible, "
                "li[role='option'][aria-label]:visible"
            )
            _abrir()
            marcas_set: dict[str, str] = {}
            panel = ac.locator("div.p-autocomplete-panel").first
            # coleta opções scrollando o painel até o fim: garante que marcas
            # com dropdown virtualizado (lista longa) fiquem todas capturadas
            for _round in range(15):
                n_opcoes = opcoes.count()
                for i in range(n_opcoes):
                    try:
                        rotulo = opcoes.nth(i).get_attribute(
                            "aria-label", timeout=800) or ""
                    except Exception:
                        rotulo = ""
                    if not rotulo:
                        try:
                            rotulo = opcoes.nth(i).inner_text(timeout=800)
                        except Exception:
                            rotulo = ""
                    nome = (rotulo or "").strip()
                    if nome:
                        chave = self._norm(nome)
                        if chave not in marcas_set:
                            marcas_set[chave] = nome
                if panel.count():
                    try:
                        antes = panel.evaluate(
                            "el => el.scrollTop + el.clientHeight")
                        panel.evaluate(
                            "el => el.scrollTop = el.scrollHeight")
                        page.wait_for_timeout(200)
                        depois = panel.evaluate(
                            "el => el.scrollTop + el.clientHeight")
                        if abs(depois - antes) < 2:
                            break
                    except Exception:
                        break
                else:
                    break
            marcas = list(marcas_set.values())
            page.keyboard.press("Escape")
            page.wait_for_timeout(150)

            juntar = {self._norm(c) for c in resultado.codigos_aplicacao}

            def _ler_novos() -> list[str]:
                cels = tabela.locator("tbody tr td:first-child")
                novos: list[str] = []
                for j in range(cels.count()):
                    try:
                        cod = _limpar_codigo(
                            cels.nth(j).inner_text(timeout=800))
                    except Exception:
                        continue
                    if cod and self._norm(cod) not in juntar:
                        novos.append(cod)
                return novos

            # teto de tempo pra troca de abinha das marcas: mesmo que um clique
            # não "pegue" ou a tabela demore a re-renderizar, o código não pode
            # travar aqui (reads sem timeout usariam 30s cada).
            deadline = time.time() + 45.0
            for marca in marcas:
                if time.time() > deadline:
                    self._msg("Aplicações: tempo limite atingido na troca "
                              "das marcas.")
                    break
                _abrir()
                if opcoes.count() == 0:
                    page.keyboard.press("Escape")
                    continue
                try:
                    opcao = page.locator(
                        "li.p-autocomplete-item, li[role='option']").filter(
                        has_text=marca).first
                    if opcao.count() == 0:
                        page.keyboard.press("Escape")
                        continue
                    opcao.click(timeout=2_500)
                except Exception:
                    page.keyboard.press("Escape")
                    page.wait_for_timeout(150)
                    continue
                # códigos da marca carregam async: espera a tabela renderizar
                # (em vez de ler às cegas 250ms depois do clique).
                novos: list[str] = []
                for _ in range(12):  # até ~2,4s de polling
                    if time.time() > deadline:
                        break
                    novos = _ler_novos()
                    if novos:
                        break
                    page.wait_for_timeout(200)
                for cod in novos:
                    if self._norm(cod) not in juntar:
                        juntar.add(self._norm(cod))
                        resultado.codigos_aplicacao.append(cod)
                page.keyboard.press("Escape")
                page.wait_for_timeout(150)
            # fallback: se o dropdown de marcas não abriu/rendeu nada, ainda
            # lê os códigos que já estão visíveis na tabela "Número OE".
            if not resultado.codigos_aplicacao:
                for _ in range(12):
                    if time.time() > deadline:
                        break
                    novos = _ler_novos()
                    if novos:
                        for cod in novos:
                            juntar.add(self._norm(cod))
                            resultado.codigos_aplicacao.append(cod)
                        break
                    page.wait_for_timeout(200)
            self._msg(
                f"[{resultado.codigo}] códigos OE mesclados: "
                f"{len(resultado.codigos_aplicacao)} em {len(marcas)} marca(s)"
            )
        except Exception as exc:
            self._rastro_abrir(
                f"[{resultado.codigo}] aplicações não disponíveis: {exc!r}"
            )

    def _extrair_veiculos(self, resultado: PecaResultado) -> None:
        """Resolve as aplicações (veículos) do artigo via API JSON-RPC e DOM.

        Tenta primeiro via API (getArticleLinkedAllLinkingTargetsByIds3).
        Se não tiver dados da API, tenta extrair de modais/tabelas no DOM
        (estilo da extensão Chrome).
        """
        page = self._page

        # 1) Tenta via API JSON-RPC
        if self._link4_pares and self._link4_origem:
            veiculos_api = self._extrair_veiculos_api(resultado)
            if veiculos_api:
                resultado.aplicacoes = veiculos_api
                self._msg(f"[{resultado.codigo}] veículos (API): "
                          f"{len(veiculos_api)} aplicação(ões)")
                return

        # 1-bis) link4 não veio: tenta forçar a aba de aplicações no
        #        detalhe pra que o SPA dispare a chamada JSON-RPC
        if not self._link4_pares:
            try:
                aba = page.locator(
                    "ta-tab:has-text('Aplica'), "
                    "button:has-text('Aplica'), "
                    "a:has-text('Aplica'), "
                    "[role='tab']:has-text('Aplica'), "
                    "ta-tab:has-text('vehicle'), "
                    "button:has-text('vehicle'), "
                    "a:has-text('vehicle'), "
                    "[role='tab']:has-text('vehicle')").first
                if aba.count() > 0:
                    aba.click(timeout=2_000)
                    page.wait_for_timeout(1_500)
            except Exception:
                pass
            if self._link4_pares and self._link4_origem:
                veiculos_api = self._extrair_veiculos_api(resultado)
                if veiculos_api:
                    resultado.aplicacoes = veiculos_api
                    self._msg(
                        f"[{resultado.codigo}] veículos (API pós-aba): "
                        f"{len(veiculos_api)} aplicação(ões)")
                    return

        # 2) Fallback: extrai de modais/tabelas no DOM (estilo extensão)
        veiculos_dom = self._extrair_veiculos_dom()
        if veiculos_dom:
            resultado.aplicacoes = veiculos_dom
            self._msg(f"[{resultado.codigo}] veículos (DOM): "
                      f"{len(veiculos_dom)} aplicação(ões)")

    def _extrair_veiculos_api(self, resultado: PecaResultado) -> list[str]:
        """Extrai veículos via API JSON-RPC."""
        if not self._link4_pares or not self._link4_origem:
            return []
        page = self._page
        origem = self._link4_origem
        pedido = origem.get("pedido", {}) or {}
        artigo_id = pedido.get("articleId")
        if not artigo_id:
            return []
        par_base = {
            "provider": pedido.get("provider", 23365),
            "lang": pedido.get("lang", "pt"),
            "articleCountry": pedido.get("articleCountry", "DE"),
        }
        url = origem["url"]
        headers = {
            k: v for k, v in origem["headers"].items()
            if k.lower() not in ("content-length", "accept-encoding", "host")
        }
        pares = list(self._link4_pares)
        veiculos: list[str] = []
        try:
            for i in range(0, len(pares), 25):
                lote = pares[i:i + 25]
                corpo = {
                    "getArticleLinkedAllLinkingTargetsByIds3": {
                        **par_base,
                        "articleId": artigo_id,
                        "immediateAttributs": True,
                        "linkingTargetType": "VOLB",
                        "linkedArticlePairs": {
                            "array": [
                                {"articleLinkId": al, "linkingTargetId": lt}
                                for al, lt in lote
                            ]
                        },
                    }
                }
                r = page.evaluate(
                    """async ({url, headers, body, timeoutMs}) => {
                        try {
                            // AbortController limita o tempo do fetch: sem isso
                            // o evaluate fica preso no timeout default de 30s
                            // quando a API de veículos não responde.
                            const ctrl = new AbortController();
                            const timer = setTimeout(() => ctrl.abort(), timeoutMs);
                            const resp = await fetch(url, {
                                method: 'POST',
                                headers: headers,
                                body: body,
                                signal: ctrl.signal,
                            });
                            clearTimeout(timer);
                            const j = await resp.json();
                            return {status: resp.status, data: j};
                        } catch (e) {
                            return {status: 0, erro: String(e)};
                        }
                    }""",
                    {"url": url, "headers": headers,
                     "body": json.dumps(corpo), "timeoutMs": 12_000},
                )
                if not isinstance(r, dict) or "erro" in r:
                    self._rastro_abrir(
                        f"[{resultado.codigo}] link4 resp inválida: "
                        f"{r!r:.200}")
                    continue
                j = r.get("data")
                d = j.get("data") if isinstance(j, dict) else None
                arr = (d.get("array", []) if isinstance(d, dict) else []) or []
                nao_dicts = [x for x in arr if not isinstance(x, dict)]
                if nao_dicts:
                    self._rastro_abrir(
                        f"[{resultado.codigo}] link4 array com itens não-dict "
                        f"({len(nao_dicts)}/{len(arr)}): {nao_dicts[:3]!r}")
                for it in arr:
                    if not isinstance(it, dict):
                        continue
                    lv = it.get("linkedVehicles")
                    if not isinstance(lv, dict):
                        continue
                    for v in (lv.get("array", []) or []):
                        if not isinstance(v, dict):
                            continue
                        nome = " ".join(
                            str(v.get(k, "") or "").strip()
                            for k in ("manuDesc", "modelDesc", "carDesc")
                        ).strip()
                        if not nome:
                            continue
                        if nome not in veiculos:
                            veiculos.append(nome)
            return veiculos
        except Exception as exc:
            self._rastro_abrir(
                f"[{resultado.codigo}] veículos API não disponíveis: {exc!r}"
            )
            return []

    def _extrair_veiculos_dom(self) -> list[str]:
        """Extrai aplicações de modais/tabelas no DOM (estilo extensão Chrome).
        
        Procura por:
        1. Modal/dialog com tabela de aplicações
        2. Tabelas com colunas de veículo/ano
        3. Lista de aplicações em qualquer lugar da página
        """
        page = self._page
        veiculos: list[str] = []
        
        try:
            # Procura modal/dialog
            modal = page.locator('[role="dialog"], .modal, [class*="modal"]').first
            if modal.count() == 0:
                # Se não tem modal, tenta extrair de tabelas na página
                modal = page.locator('body')
            
            # Extrai linhas da tabela (cap pra não varrer a página toda quando a
            # referência não monta e o fallback cai no body inteiro)
            rows = modal.locator('table tbody tr')
            seen = set()
            total_rows = min(rows.count(), 1000)
            
            for i in range(total_rows):
                row = rows.nth(i)
                try:
                    # Procura link (nome do veículo)
                    link = row.locator('a').first
                    if link.count() == 0:
                        continue
                    
                    model_raw = link.inner_text(timeout=1000).strip()
                    if not model_raw or 'mais informações' in model_raw.lower():
                        continue
                    
                    # Extrai ano
                    cells = row.locator('td, th')
                    year_range = ''
                    for j in range(cells.count()):
                        cell_text = cells.nth(j).inner_text(timeout=500).strip()
                        year_match = re.search(r'(\d{2}\.\d{4})(?:\s*[—-]\s*(\d{2}\.\d{4}))?', cell_text)
                        if year_match:
                            start_year = year_match.group(1).split('.')[1]
                            end_year = year_match.group(2).split('.')[1] if year_match.group(2) else ''
                            year_range = f"{start_year}-{end_year}" if end_year else f"{start_year}-"
                            break
                    
                    if not year_range:
                        continue
                    
                    # Formata aplicação
                    app_line = f"{model_raw} {year_range}"
                    if app_line not in seen:
                        seen.add(app_line)
                        veiculos.append(app_line)
                        
                except Exception:
                    continue
            
            return veiculos
            
        except Exception as exc:
            self._rastro_abrir(f"veículos DOM não disponíveis: {exc!r}")
            return []

    def __del__(self):
        try:
            self.encerrar()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# PARSER da API (JSON)
# ---------------------------------------------------------------------------

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
                "codigo_ref": _limpar_codigo(_caminho(a, ("articleNumber", "articleNo")) or ""),
                "disponivel": _eh_disponivel(a),
            })

        if not artigos:
            self.resultado.observacao = "Nenhum resultado encontrado"
            self.tenha_dados_faltando = True
            return True

        # filtra por marcas (comparação tolerante, ex.: 'hepu' casa com a
        # API que pode vir como 'HEPU GmbH' / case diferente)
        if self.marcas:
            filtrados = [a for a in artigos
                         if _marca_casa(a["marca"], self.marcas)]
            if not filtrados:
                self.resultado.observacao = (
                    f"Nada nas marcas: {', '.join(self.marcas)}"
                )
                self.tenha_dados_faltando = True
                return True
            artigos = filtrados
            # prioriza a ordem das marcas configuradas
            artigos.sort(key=lambda a: min(
                (i for i, m in enumerate(self.marcas)
                 if _marca_casa(a["marca"], [m])), default=99))

        melhor = artigos[0]
        self.resultado.marca = melhor["marca"]
        self.resultado.descricao = melhor["descricao"]
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

def executar_busca(
    login: str,
    senha: str,
    codigos: list[str | dict[str, str]],
    marcas: list[str] | None = None,
    headless: bool = False,
    on_progress: callable | None = None,
    on_mensagem: callable | None = None,
    capturar_api: bool = False,
    on_pausa: callable | None = None,
    on_resultado: callable | None = None,
    deve_desbloquear: callable | None = None,
) -> list[PecaResultado]:
    automator = TecDocAutomator(login, senha, headless=headless, marcas=marcas,
                                capturar_api=capturar_api, on_mensagem=on_mensagem,
                                deve_desbloquear=deve_desbloquear)
    resultados: list[PecaResultado] = []
    try:
        automator.iniciar()
        automator.garantir_login()
        total = len(codigos)
        marca_anterior: str | None = None
        # A fila cresce no máximo uma vez por código: "Destravar" agenda o
        # item atual no final, sem abandonar o restante do lote.
        fila = list(codigos)
        reagendados: set[tuple[str, str]] = set()
        for i, item in enumerate(fila, start=1):
            if isinstance(item, dict):
                codigo = str(item.get("codigo", "")).strip()
                marca_item = str(item.get("marca", "")).strip()
            else:
                codigo = str(item).strip()
                marca_item = ""
            if on_progress:
                sufixo = " (nova tentativa)" if i > total else ""
                on_progress(min(i, total), total, codigo + sufixo)
            if not codigo:
                continue
            # Aguarda se estiver pausado
            if on_pausa:
                on_pausa()
            if i > 1:
                config.pausa_entre_codigos()
            # A marca informada na própria linha tem prioridade. O filtro é
            # resetado para permitir marcas diferentes na mesma lista; se a
            # marca for a MESMA do código anterior, mantém o filtro do site
            # (o SPA preserva brands= entre buscas) e pula o reload do shell
            # — economia de ~1min por código em lote.
            marca_item_norm = marca_item.strip().lower()
            if i == 1 or marca_item_norm != marca_anterior:
                marca_anterior = marca_item_norm
                automator._filtro_aplicado = False
                automator._filtro_efetivado = False
                automator.marcas = [marca_item] if marca_item else (marcas or [])
                if i > 1:
                    # Volta à raiz do site pra limpar o estado da SPA
                    # (brands=, groups=, fragmento de busca antigo).
                    # Não usamos goto pra uma URL de busca porque a SPA
                    # às vezes ignora a navegação e a grid não carrega.
                    automator._page.goto(
                        config.TECDOC_URL, wait_until="domcontentloaded"
                    )
                    try:
                        automator._page.wait_for_load_state(
                            "networkidle", timeout=10_000)
                    except TimeoutError:
                        pass
                    automator._page.wait_for_timeout(500)
            else:
                # mesma marca: filtro já aplicado no site; pula o reload do
                # shell e digita direto no campo do cabeçalho da SPA.
                automator._filtro_aplicado = True
                automator._filtro_efetivado = True
            try:
                res = automator._buscar_com_reconexao(codigo)
            except BuscaDestravada:
                chave = (codigo.upper(), marca_item.lower())
                if chave not in reagendados:
                    reagendados.add(chave)
                    fila.append(item)
                    automator._msg(
                        f"[{codigo}] destravado — será tentado novamente ao fim.")
                else:
                    automator._msg(
                        f"[{codigo}] destravado novamente; pulado para não travar o lote.")
                continue
            except Exception as exc:
                automator._rastro_abrir(
                    f"[{codigo}] EXCEÇÃO em buscar_codigo: {exc!r}")
                res = PecaResultado(codigo=codigo, observacao=f"Erro: {exc}")
            resultados.append(res)
            # Emite parcial para preview em tempo real
            if on_resultado:
                try:
                    on_resultado(res)
                except Exception:
                    pass
    finally:
        automator.encerrar()
    return resultados
