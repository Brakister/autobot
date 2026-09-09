"""Tela de progresso mostrada enquanto a automação Playwright roda."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QProgressBar, QPlainTextEdit,
)
from PySide6.QtCore import Qt


class ProgressScreen(QWidget):
    def __init__(self):
        super().__init__()
        self._build()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(16)

        titulo = QLabel("Buscando no TecDoc…")
        titulo.setObjectName("title")
        root.addWidget(titulo)

        sub = QLabel(
            "A automação está aberta no navegador. NÃO feche a janela do "
            "navegador nem mexa nos campos enquanto busca."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)

        self.lbl_atual = QLabel("Aguardando…")
        self.lbl_atual.setObjectName("subtitle")
        root.addWidget(self.lbl_atual)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Log da execução…")
        root.addWidget(self.log, stretch=1)

        self.setLayout(root)

    def iniciar(self, total: int):
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.log.clear()

    def atualizar(self, index: int, total: int, codigo: str):
        self.progress.setValue(index)
        self.lbl_atual.setText(
            f"({index}/{total}) Buscando código: {codigo}"
        )
        self.log.appendPlainText(f"[{index}/{total}] {codigo} …")

    def log_erro(self, msg: str):
        self.log.appendPlainText(f"      ! {msg}")
