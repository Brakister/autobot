"""Verificação e instalação de novas versões (auto-update) para o Cadastro Auto.

- Checa a API pública do GitHub (`/repos/{repo}/releases/latest`) para a versão
  mais recente.
- Se houver versão nova, o app avisa ao abrir (background thread).
- Se o usuário aceitar, baixa o instalador .exe para a pasta temporária e o
  executa (processo Detached), depois encerra o app.
"""

import json
import urllib.request
import urllib.error
import tempfile
import os
import subprocess
import sys
from packaging.version import parse as _parse_ver

import config


API_URL = f"https://api.github.com/repos/{config.GITHUB_REPO}/releases/latest"
TIMEOUT = 10  # segundos


def _versao_para_tupla(versao: str):
    """Converte uma string de versão (ex: '1.1.0') em tuple de ints."""
    try:
        v = _parse_ver(versao)
        # packaging.version.Version .release é (major, minor, patch, ...)
        return v.release[:3]
    except Exception:
        return (0, 0, 0)


def versao_mais_nova(versao_atual: str, timeout: int = TIMEOUT):
    """Retorna dict com info da versão mais nova ou None se não houver atualização.

    Chaves esperadas: "versao", "url" (download .exe), "notas" (body opcional).
    """
    req = urllib.request.Request(
        API_URL,
        headers={
            "User-Agent": "cadastroauto-updater",
            "Accept": "application/vnd.github+json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.load(resp)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError):
        return None

    tag = data.get("tag_name", "").lstrip("vV").strip()
    if not tag:
        return None

    versao_nova = tag
    comparar = _parse_ver(versao_nova)
    atual = _parse_ver(versao_atual)
    if comparar <= atual:
        return None  # já está na versão mais recente (ou igual)

    # Encontrar URL do instalador .exe entre os assets
    url_download = None
    for asset in data.get("assets", []):
        nome = asset.get("name", "").lower()
        if nome.endswith(".exe"):
            url_download = asset.get("browser_download_url")
            break

    if not url_download:
        return None

    # Pegar body/notes resumido (primeiras 3 linhas)
    notas = data.get("body", "")
    resumo = " ".join(notas.splitlines()[:3]) if notas else ""

    return {
        "versao": versao_nova,
        "url": url_download,
        "notas": resumo,
    }


def baixar_instalador(url: str, destino: str, progresso_cb=None):
    """Baixa o instalador de `url` para `destino`, chamando `progresso_cb(pct)` se fornecido."""
    req = urllib.request.Request(url, headers={"User-Agent": "cadastroauto-downloader"})
    with urllib.request.urlopen(req, timeout=30) as resp, open(destino, "wb") as f:
        total = int(resp.headers.get("Content-Length", "0") or 0)
        baixado = 0
        while True:
            bloco = resp.read(65536)
            if not bloco:
                break
            f.write(bloco)
            baixado += len(bloco)
            if progresso_cb and total:
                pct = int(baixado * 100 / total)
                progresso_cb(pct)
    return destino