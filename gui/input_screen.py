"""Tela de entrada de códigos: colar em texto ou carregar arquivo .txt/.csv."""
import re
from pathlib import Path

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPlainTextEdit, QPushButton, QLabel,
    QFileDialog, QGroupBox,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFontDatabase, QFont

import config


def extrair_codigos(texto: str) -> list[dict[str, str]]:
    """Extrai códigos de um texto (arquivo ou colado).

    Considera cada linha um código. Ignora linhas em branco, cabeçalhos e
    linhas com apenas separadores. Quando a linha contém múltiplos campos
    (CSV separado por ; , ou TAB), pega o primeiro campo.
    """
    codigos = []
    for linha in texto.splitlines():
        linha = linha.strip()
        if not linha:
            continue
        # remove linhas que parecem cabeçalho
        if linha.lower().startswith(("código", "codigo", "part", "sku",
                                     "manufacturer", "marca", "item")):
            continue
        campos = [campo.strip() for campo in re.split(r"[;,\t]", linha)]
        codigo = campos[0] if campos else ""
        marca = campos[1] if len(campos) > 1 else ""
        if not marca:
            partes = codigo.split(maxsplit=1)
            codigo = partes[0]
            marca = partes[1].strip() if len(partes) > 1 else ""
        if codigo:
            codigos.append({"codigo": codigo, "marca": marca})
    # remove duplicados preservando ordem
    vistos = set()
    unicos = []
    for item in codigos:
        chave = (item["codigo"].upper(), item["marca"].lower())
        if chave not in vistos:
            vistos.add(chave)
            unicos.append(item)
    return unicos


class InputScreen(QWidget):
    def __init__(self, on_continue):
        super().__init__()
        self.on_continue = on_continue
        self._build()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(16)

        titulo = QLabel("Códigos de peça")
        titulo.setObjectName("title")
        root.addWidget(titulo)

        sub = QLabel(
            "Cole os códigos (um por linha) ou carregue um arquivo "
            ".txt / .csv. Opcionalmente informe a marca após o código: "
            "12345 Bosch ou 12345; Bosch."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)

        box = QGroupBox("Lista de códigos")
        v = QVBoxLayout()
        v.setSpacing(10)

        self.editor = QPlainTextEdit()
        monofont = QFontDatabase.systemFont(QFontDatabase.FixedFont)
        self.editor.setFont(monofont)
        self.editor.setPlaceholderText(
            "Ex.:\n095510-33040 Bosch\n54-1011; Textar\n0281301040"
        )
        v.addWidget(self.editor)

        h = QHBoxLayout()
        btn_carregar = QPushButton("Carregar arquivo…")
        btn_carregar.clicked.connect(self._carregar_arquivo)
        self.lbl_arquivo = QLabel("Nenhum arquivo")
        self.lbl_arquivo.setObjectName("subtitle")
        h.addWidget(btn_carregar)
        h.addWidget(self.lbl_arquivo)
        h.addStretch(1)
        v.addLayout(h)

        self.lbl_count = QLabel("0 código(s) detectado(s)")
        self.lbl_count.setObjectName("subtitle")
        v.addWidget(self.lbl_count)

        box.setLayout(v)
        root.addWidget(box)

        self.erro = QLabel("")
        self.erro.setObjectName("error")
        root.addWidget(self.erro)

        btn_linha = QHBoxLayout()
        btn_linha.addStretch(1)
        btn_continuar = QPushButton("Continuar →")
        btn_continuar.setObjectName("primary")
        btn_continuar.clicked.connect(self._continuar)
        btn_linha.addWidget(btn_continuar)
        root.addLayout(btn_linha)

        root.addStretch(1)
        self.setLayout(root)

        self.editor.textChanged.connect(self._atualizar_count)

    def _atualizar_count(self):
        codigos = extrair_codigos(self.editor.toPlainText())
        n = len(codigos)
        self.lbl_count.setText(f"{n} código(s) detectado(s)")

    def _carregar_arquivo(self):
        caminho, _ = QFileDialog.getOpenFileName(
            self, "Selecionar arquivo de códigos", "",
            "Arquivos (*.txt *.csv);;Todos (*)",
        )
        if not caminho:
            return
        try:
            texto = Path(caminho).read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            self.erro.setText(f"Falha ao ler arquivo: {exc}")
            return
        self.editor.setPlainText(texto)
        self.lbl_arquivo.setText(Path(caminho).name)
        self.erro.setText("")

    def _get_codigos(self) -> list[str]:
        codigos = extrair_codigos(self.editor.toPlainText())
        # se vier de um arquivo com nome, usa esse nome como código de busca da sessão
        return codigos

    def limpar(self):
        """Prepara a tela para um novo lote sem fechar o aplicativo."""
        self.editor.clear()
        self.lbl_arquivo.setText("Nenhum arquivo")
        self.erro.clear()

    def _continuar(self):
        codigos = self._get_codigos()
        if not codigos:
            self.erro.setText("Nenhum código detectado.")
            return
        if len(codigos) > config.MAX_CODES_PER_RUN:
            self.erro.setText(
                f"Limite de {config.MAX_CODES_PER_RUN} códigos por execução.\n"
                f"Você tem {len(codigos)}. Divida em lotes."
            )
            return
        self.erro.setText("")
        self.on_continue(codigos)
