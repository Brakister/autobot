"""Configurações centrais do projeto cadastroauto."""
import os
import random
import sys
from pathlib import Path

# URL base do TecDoc
TECDOC_URL = "https://web.tecalliance.net/tecdoc/pt"
LOGIN_URL = "https://login.tecalliance.net/app/UserHome?session_hint=AUTHENTICATED"

# Versão do aplicativo (usada no auto-update) e repositório das releases.
APP_VERSION = "1.1.0"
GITHUB_REPO = "Brakister/autobot"


def base_path() -> Path:
    """Retorna o diretório base do app (funciona dentro do PyInstaller)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def data_dir() -> Path:
    """Diretório onde ficam o banco de dados e sessão do navegador."""
    d = base_path() / "data"
    d.mkdir(parents=True, exist_ok=True)
    return d


def configurar_playwright() -> None:
    """Faz o Playwright achar o navegador embutido junto do exe.

    O build copia as pastas chromium-<rev> e chromium_headless_shell-<rev>
    para a mesma pasta do executável. Sem isso, o Playwright procura em
    %LOCALAPPDATA%\\ms-playwright (o PC de destino não tem navegador).
    Em desenvolvimento (.py) respeita o comportamento padrão.
    """
    if getattr(sys, "frozen", False):
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(base_path()))


# Caminhos
DATABASE_PATH = data_dir() / "cadastroauto.db"
# arquivo de estado do navegador (cookies + localStorage) — usado pelo
# storage_state do Playwright (precisa ser um ARQUIVO, não um diretório)
SESSION_FILE = data_dir() / "browser_session.json"
SESSION_DIR = data_dir() / "browser_session"  # pasta extra de suporte (sessionStorage)
EXPORT_DIR = data_dir() / "exports"

# Tempo máximo (segundos) de espera por elemento no Playwright
PLAYWRIGHT_TIMEOUT = 30_000

# Ritmo da automação: reduz esperas redundantes, mas mantém uma pausa humana
# entre códigos para não gerar uma sequência artificial de requisições.
GRID_STABLE_SAMPLES = 2
PAUSE_BETWEEN_CODES = (0.8, 1.6)

# A extração usa API/DOM textual; imagens, fontes e vídeos só aumentam o
# trabalho do Chromium e o consumo de memória em máquinas mais fracas.
BLOQUEAR_RECURSOS_PESADOS = True


def pausa_entre_codigos() -> None:
    """Pausa curta e variável entre buscas consecutivas."""
    import time
    time.sleep(random.uniform(*PAUSE_BETWEEN_CODES))

# Marcas padrão sugeridas na seleção (aparecem marcadas de início)
DEFAULT_BRANDS = [
    "Brembo", "Bosch", "Mahle", "Bilstein", "Febi", "SWAG", "ZE",
    "TRW", "Lemförder", "Sachs", "Textar", "Hengst", "Hella",
    "Delphi", "Pierburg", "UFI", "HEPU", "Forschen",
]

# Limite de códigos por corrida automática (evita timeout)
MAX_CODES_PER_RUN = 500

# Auto-reparo: quantas tentativas por código ante queda de rede / erro de
# servidor, e a pausa (aleatória) entre tentativas, em segundos.
TENTATIVAS_POR_CODIGO = 3
PAUSA_ENTRE_TENTATIVAS = (5.0, 12.0)

# Auto-reparo do FILTRO de marcas: se o site não confirmar o filtro na URL
# (?brands=), a validação de marca fica sem efeito e o detalhe não abre (pra
# evitar 404). Nessas horas o multiselect às vezes "engole" o clique no
# checkbox; então a busca espera uma pausa e RECARREGA o mesmo código — a
# re-busca reaplica o filtro e a segunda passada costuma pegar.
FILTRO_RETRY_TENTATIVAS = 2
FILTRO_RETRY_ESPERA = (3.0, 7.0)
