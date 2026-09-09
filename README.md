# Cadastro Auto · TecDoc

Sistema de automação para buscar códigos de peça no TecDoc (TecAlliance),
filtrar por marcas e revisar/confirmar antes de salvar.

## Stack

- **Python** (3.14)
- **PySide6** — interface gráfica
- **Playwright** — automação do navegador (login + busca + extração)
- **SQLite** — persistência (peças, cross-references, sessões)
- **PyInstaller** — empacotamento em `.exe`

## Estrutura

```
main.py                 # entry point
config.py               # configurações (URLs, caminhos, limites)
database.py             # camada SQLite
tecdoc.py               # automação Playwright (100% máquina)
export.py               # exportar CSV/XLSX
gui/
  login_screen.py       # credenciais
  input_screen.py       # colar códigos / carregar arquivo
  brand_filter.py       # selecionar marcas
  progress_screen.py    # progresso da automação
  review_screen.py      # "Está tudo certo?" (editar + confirmar)
  main_window.py        # orquestração do fluxo
```

## Fluxo

1. **Login** — usuário/senha do TecAlliance
2. **Códigos** — colar (um por linha) ou carregar `.txt`/`.csv`
3. **Marcas** — selecionar marcas a filtrar
4. **Automação (100% máquina)** — Playwright loga, busca cada código e extrai
   descrição, marca e cross-references
5. **Revisão** — tabela editável "Está tudo certo?" (editar/remover linhas)
6. **Confirmar** — salva no SQLite e exporta CSV + XLSX

## IMPORTANTE — seletores

Os seletores ficam centralizados no dicionário `SELETORES` no `tecdoc.py`,
agrupados por etapa (`login`, `busca`, `resultado`, `xref`).

O que **já está confirmado** (análise do bundle JS em 2026):
- Login Okta: `input[name='identifier']` → senha `credentials.passcode` → submit.
- API do catálogo: POST `{basePath}/rest/<Operacao>` com body `{"<Operacao>": {...}}`.
- Campos dos artigos: `articleNumber`, `dataSupplierName`, `articleDescription`,
  `oemNumbers[].articleNumber`, `dataFormats`, `articleState`.

O sistema tenta extrair os dados **interceptando a API JSON-RPC** (robusto) e
cai para DOM se necessário. Os seletores de DOM (`busca`, `resultado`, `xref`)
ainda são candidatos prováveis — confirme-os rodando o diagnóstico:

```bash
python diagnostico.py                 # pergunta login/senha e o código
python diagnostico.py 0460907501      # já passa o código de teste
```

Esse script reutiliza a sessão salva (login automático; se aparecer MFA,
complete manualmente no navegador que abre) e faz **1 busca real**. Ele salva
em `data/diagnostico/`:
- `captura/` — todas as trocas com a API `/rest/*` (JSON-L)
- `dom_resultados.html` e `linhas_resultados.json` — tabela de resultados real
- `pagina_busca.html` — página inteira (filtros de marca ficam fora da grid)
- `cabecalhos_resultados.json` — colunas da tabela (para localizar disponibilidade)
- `filtros_marca.json` — descrição do filtro de marcas do site
- `erro_404.html/.txt` — captura da página de erro quando o clique falha
- `scan_disponibilidade.json` — quais campos de disponibilidade a API expõe

De posse disso, ajuste o `SELETORES` no `tecdoc.py` se algum campo divergir.

### Gravar o fluxo manual (para ver como você faz)

Quando o app automatizar algo que só funciona na mão, rode o gravador —
ele abre o TecDoc já logado e registra **tudo o que você fizer**:

```bash
python gravar_sessao.py
```

Faça o fluxo normal no navegador (buscar código, abrir o filtro de marcas,
digitar a marca, esperar e clicar no resultado) e pressione ENTER no terminal
quando terminar. Gera em `data/grava_sessao/`:
- `video/*.webm` — gravação da tela
- `cliques.jsonl` — cada clique (elemento, classe, `ta-name`, texto, caminho)
- `urls.txt` — todas as mudanças de URL
- `requests.jsonl` — chamadas `/rest/*` (API) com corpo
- `dom_fim.html` + `fim.png` — estado final da página
- `url_final.txt` — URL onde você parou

## Instalação (dev)

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
python main.py
```

## Gerar .exe

```bash
pip install pyinstaller
pyinstaller cadastroauto.spec
```

O executável sai em `dist\cadastroauto.exe`.

O Playwright precisa do navegador Chromium acessível. Defina
`PLAYWRIGHT_BROWSERS_PATH` para uma pasta que viaje junto com o `.exe` se
quiser distribuir (ver docs do Playwright/PyInstaller).
