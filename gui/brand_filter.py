"""Tela de seleção de marcas para o filtro de resultados."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QListWidget,
    QListWidgetItem, QLineEdit, QGroupBox,
)
from PySide6.QtCore import Qt

import config


class BrandFilterScreen(QWidget):
    def __init__(self, marcas_conhecidas: list[str], on_continue):
        """marcas_conhecidas: lista de marcas a mostrar (ex.: pré-cadastradas)."""
        super().__init__()
        self.marcas_conhecidas = marcas_conhecidas or config.DEFAULT_BRANDS
        self.on_continue = on_continue
        self._build()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(52, 44, 52, 44)
        root.setSpacing(14)

        eyebrow = QLabel("ETAPA 2 DE 3 · REFINAR RESULTADOS")
        eyebrow.setObjectName("eyebrow")
        root.addWidget(eyebrow)

        titulo = QLabel("Filtrar por marcas")
        titulo.setObjectName("title")
        root.addWidget(titulo)

        sub = QLabel(
            "Selecione as marcas desejadas. Só as peças dessas marcas serão "
            "consideradas na hora de mostrar os resultados."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)

        box = QGroupBox("Marcas")
        v = QVBoxLayout()
        v.setSpacing(10)

        self.pesquisa = QLineEdit()
        self.pesquisa.setPlaceholderText("Buscar marca…")
        self.pesquisa.textChanged.connect(self._filtrar_lista)
        v.addWidget(self.pesquisa)

        self.lista = QListWidget()
        self.lista.setSelectionMode(QListWidget.MultiSelection)
        self.lista.itemSelectionChanged.connect(self._atualizar_count)
        self.lista.setMinimumHeight(270)
        for marca in self.marcas_conhecidas:
            item = QListWidgetItem(marca)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self.lista.addItem(item)

        v.addWidget(self.lista, stretch=1)

        h_btns = QHBoxLayout()
        btn_todos = QPushButton("Marcar todos")
        btn_todos.clicked.connect(lambda: self._set_todos(True))
        btn_nenhum = QPushButton("Desmarcar todos")
        btn_nenhum.clicked.connect(lambda: self._set_todos(False))
        h_btns.addWidget(btn_todos)
        h_btns.addWidget(btn_nenhum)
        h_btns.addStretch(1)
        v.addLayout(h_btns)

        self.lbl_count = QLabel("0 marcada(s)")
        self.lbl_count.setObjectName("subtitle")
        v.addWidget(self.lbl_count)

        box.setLayout(v)
        root.addWidget(box)

        btn_linha = QHBoxLayout()
        btn_linha.addStretch(1)
        btn_continuar = QPushButton("Continuar →")
        btn_continuar.setObjectName("primary")
        btn_continuar.clicked.connect(self._continuar)
        btn_linha.addWidget(btn_continuar)
        root.addLayout(btn_linha)

        root.addStretch(1)
        self.setLayout(root)

    def _set_todos(self, on: bool):
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            state = Qt.Checked if on else Qt.Unchecked
            item.setCheckState(state)
        self._atualizar_count()

    def _filtrar_lista(self, texto: str):
        texto = texto.lower()
        for i in range(self.lista.count()):
            item = self.lista.item(i)
            item.setHidden(texto not in item.text().lower())

    def _atualizar_count(self):
        sel = self._selecionadas()
        self.lbl_count.setText(f"{len(sel)} marca(s) selecionada(s)")

    def _selecionadas(self) -> list[str]:
        return [
            self.lista.item(i).text()
            for i in range(self.lista.count())
            if self.lista.item(i).checkState() == Qt.Checked
        ]

    def _continuar(self):
        self.on_continue(self._selecionadas())
