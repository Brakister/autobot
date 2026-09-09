"""Configurações centrais do projeto cadastroauto."""
import os
import random
import sys
from pathlib import Path

# URL base do TecDoc
TECDOC_URL = "https://web.tecalliance.net/tecdoc/pt"
LOGIN_URL = "https://login.tecalliance.net/app/UserHome?session_hint=AUTHENTICATED"


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


def pausa_entre_codigos() -> None:
    """Pausa curta e variável entre buscas consecutivas."""
    import time
    time.sleep(random.uniform(*PAUSE_BETWEEN_CODES))

# Marcas padrão sugeridas na seleção (aparecem marcadas de início)
DEFAULT_BRANDS = [
    "Brembo", "Bosch", "Mahle", "Bilstein", "Febi", "SWAG", "ZE",
    "TRW", "Lemförder", "Sachs", "Textar", "Hengst", "Hella",
    "Delphi", "Pierburg", "UFI",
]

# Limite de códigos por corrida automática (evita timeout)
MAX_CODES_PER_RUN = 500
