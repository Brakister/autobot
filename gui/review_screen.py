"""Tela de revisão 'Está tudo certo?' com tabela editável.

Permite ao usuário revisar, editar inline, remover linhas e, ao confirmar,
salvar no SQLite e exportar CSV/XLSX.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog, QMessageBox,
    QGroupBox, QComboBox, QCheckBox,
)
from PySide6.QtCore import Qt

import database as db
import export as exp


class ReviewScreen(QWidget):
    def __init__(self, resultados: list[dict], on_confirmar,
                 on_adicionar=None):
        """resultados: lista de dicts (cada um com codigo, descricao, marca,
        fornecedor, disponivel, observacao, cross_refs).
        on_confirmar: callback(lista_final) chamado ao confirmar."""
        super().__init__()
        self.resultados = resultados
        self.on_confirmar = on_confirmar
        self.on_adicionar = on_adicionar
        self._build()
        self._popular()

    # colunas: handle | codigo | descricao | marca | disponivel | obs
    COL_CODIGO = 0
    COL_DESCRICAO = 1
    COL_MARCA = 2
    COL_DISPONIVEL = 3
    COL_OBS = 4

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(12)

        titulo = QLabel("Está tudo certo?")
        titulo.setObjectName("title")
        root.addWidget(titulo)

        sub = QLabel(
            "Revise os resultados abaixo. Você pode editar descrição/marca, "
            "marcar/desmarcar disponível e remover linhas antes de confirmar."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)

        self.tabela = QTableWidget(0, 5)
        self.tabela.setHorizontalHeaderLabels(
            ["Código", "Descrição", "Marca", "Disponível", "Observação"]
        )
        self.tabela.setEditTriggers(
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
        )
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(self.COL_DESCRICAO, QHeaderView.Stretch)
        self.tabela.verticalHeader().setVisible(False)
        root.addWidget(self.tabela, stretch=1)

        self.tabela.itemChanged.connect(self._item_editado)

        # Resumo cross-references (mostrado ao selecionar uma linha)
        box_xref = QGroupBox("Cross-references da peça selecionada")
        vx = QVBoxLayout()
        self.lbl_xref = QLabel("Selecione uma linha para ver as referências cruzadas.")
        self.lbl_xref.setObjectName("subtitle")
        self.lbl_xref.setWordWrap(True)
        vx.addWidget(self.lbl_xref)
        box_xref.setLayout(vx)
        root.addWidget(box_xref)
        self.tabela.itemSelectionChanged.connect(self._mostrar_xref)

        # Ações de linha
        acoes = QHBoxLayout()
        btn_remover = QPushButton("Remover selecionada")
        btn_remover.setObjectName("danger")
        btn_remover.clicked.connect(self._remover_selecionada)
        btn_marcar_disp = QPushButton("Marcar 'Disponível'")
        btn_marcar_disp.clicked.connect(lambda: self._set_disponivel(True))
        btn_desmarcar_disp = QPushButton("Desmarcar 'Disponível'")
        btn_desmarcar_disp.clicked.connect(lambda: self._set_disponivel(False))
        acoes.addWidget(btn_remover)
        acoes.addWidget(btn_marcar_disp)
        acoes.addWidget(btn_desmarcar_disp)
        acoes.addStretch(1)
        root.addLayout(acoes)

        # Exportação rápida
        ex = QHBoxLayout()
        btn_csv = QPushButton("Exportar CSV…")
        btn_csv.clicked.connect(self._exportar_csv)
        btn_xlsx = QPushButton("Exportar Excel…")
        btn_xlsx.clicked.connect(self._exportar_xlsx)
        ex.addWidget(btn_csv)
        ex.addWidget(btn_xlsx)
        ex.addStretch(1)
        root.addLayout(ex)

        self.lbl_resumo = QLabel("")
        self.lbl_resumo.setObjectName("ok")
        root.addWidget(self.lbl_resumo)

        btn_linha = QHBoxLayout()
        btn_adicionar = QPushButton("+ Adicionar códigos")
        btn_adicionar.clicked.connect(self._adicionar)
        btn_linha.addWidget(btn_adicionar)
        btn_linha.addStretch(1)
        self.btn_confirmar = QPushButton("Confirmar e salvar ✓")
        self.btn_confirmar.setObjectName("primary")
        self.btn_confirmar.clicked.connect(self._confirmar)
        btn_linha.addWidget(self.btn_confirmar)
        root.addLayout(btn_linha)

        self.setLayout(root)

    def _adicionar(self):
        if self.on_adicionar:
            self.on_adicionar()

    # -- população ----------------------------------------------------------

    def _popular(self):
        self.tabela.blockSignals(True)
        self.tabela.setRowCount(0)
        for r in self.resultados:
            self._inserir_linha(r)
        self.tabela.blockSignals(False)
        self._atualizar_resumo()

    def _inserir_linha(self, r: dict):
        row = self.tabela.rowCount()
        self.tabela.insertRow(row)

        item_cod = QTableWidgetItem(str(r.get("codigo", "")))
        item_cod.setFlags(item_cod.flags() & ~Qt.ItemIsEditable)  # código não editável
        self.tabela.setItem(row, self.COL_CODIGO, item_cod)

        item_desc = QTableWidgetItem(str(r.get("descricao", "")))
        self.tabela.setItem(row, self.COL_DESCRICAO, item_desc)

        item_marca = QTableWidgetItem(str(r.get("marca", "")))
        self.tabela.setItem(row, self.COL_MARCA, item_marca)

        item_disp = QTableWidgetItem()
        item_disp.setText("Sim" if r.get("disponivel") else "Não")
        item_disp.setFlags(
            item_disp.flags() | Qt.ItemIsUserCheckable
        )
        item_disp.setCheckState(
            Qt.Checked if r.get("disponivel") else Qt.Unchecked
        )
        self.tabela.setItem(row, self.COL_DISPONIVEL, item_disp)

        item_obs = QTableWidgetItem(str(r.get("observacao", "")))
        self.tabela.setItem(row, self.COL_OBS, item_obs)

        self.tabela.item(row, self.COL_CODIGO).setData(
            Qt.UserRole, r.get("cross_refs", [])
        )
        self.tabela.item(row, self.COL_CODIGO).setData(
            Qt.UserRole + 1,
            {
                "gtin": r.get("gtin", ""),
                "cilindradas": r.get("cilindradas", []),
                "aplicacoes": r.get("aplicacoes", []),
                "codigos_aplicacao": r.get("codigos_aplicacao", []),
            },
        )

    def _item_editado(self, item):
        # se o usuário clicar no checkbox de disponível
        if item.column() == self.COL_DISPONIVEL:
            item.setText("Sim" if item.checkState() == Qt.Checked else "Não")

    # -- leitura ------------------------------------------------------------

    def _x(self):
        return self.resultados

    def _linhas_finais(self) -> list[dict]:
        finais = []
        for row in range(self.tabela.rowCount()):
            codigo = self.tabela.item(row, self.COL_CODIGO).text()
            descricao = self.tabela.item(row, self.COL_DESCRICAO).text()
            marca = self.tabela.item(row, self.COL_MARCA).text()
            disp_item = self.tabela.item(row, self.COL_DISPONIVEL)
            disponivel = disp_item.checkState() == Qt.Checked
            obs = self.tabela.item(row, self.COL_OBS).text()
            cross_refs = self.tabela.item(row, self.COL_CODIGO).data(Qt.UserRole)
            extras = self.tabela.item(row, self.COL_CODIGO).data(Qt.UserRole + 1) or {}
            finais.append({
                "codigo": codigo,
                "descricao": descricao,
                "marca": marca,
                "disponivel": disponivel,
                "observacao": obs,
                "cross_refs": cross_refs or [],
                "gtin": extras.get("gtin", ""),
                "cilindradas": extras.get("cilindradas", []),
                "aplicacoes": extras.get("aplicacoes", []),
                "codigos_aplicacao": extras.get("codigos_aplicacao", []),
            })
        return finais

    def _atualizar_resumo(self):
        n = self.tabela.rowCount()
        disp = sum(
            1 for row in range(self.tabela.rowCount())
            if self.tabela.item(row, self.COL_DISPONIVEL).checkState() == Qt.Checked
        )
        self.lbl_resumo.setText(f"{n} peça(s) · {disp} disponível(is)")

    def _mostrar_xref(self):
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            return
        row = rows[0].row()
        refs = self.tabela.item(row, self.COL_CODIGO).data(Qt.UserRole) or []
        if refs:
            linhas = []
            for ref in refs:
                if isinstance(ref, dict):
                    marca = ref.get("marca_ref", "-")
                    codigo = ref.get("codigo_ref", "")
                else:
                    codigo = ref[0] if len(ref) > 0 else ""
                    marca = ref[1] if len(ref) > 1 and ref[1] else "-"
                linhas.append(f"   {marca}: {codigo}")
            texto = "\n".join(linhas)
            self.lbl_xref.setText(texto)
        else:
            self.lbl_xref.setText("Sem cross-references registradas.")

    # -- ações --------------------------------------------------------------

    def _remover_selecionada(self):
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            return
        rows.sort(key=lambda idx: idx.row(), reverse=True)
        for idx in rows:
            self.tabela.removeRow(idx.row())
        self._atualizar_resumo()

    def _set_disponivel(self, valor: bool):
        for idx in self.tabela.selectionModel().selectedRows():
            item = self.tabela.item(idx.row(), self.COL_DISPONIVEL)
            item.setCheckState(Qt.Checked if valor else Qt.Unchecked)
            item.setText("Sim" if valor else "Não")
        self._atualizar_resumo()

    def _exportar_csv(self):
        finais = self._linhas_finais()
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar CSV", "resultados.csv", "CSV (*.csv)"
        )
        if caminho:
            try:
                p = exp.exportar_csv(finais, caminho)
                QMessageBox.information(self, "Exportado", f"Salvo em:\n{p}")
            except Exception as exc:
                QMessageBox.critical(self, "Erro", str(exc))

    def _exportar_xlsx(self):
        finais = self._linhas_finais()
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar Excel", "resultados.xlsx", "Excel (*.xlsx)"
        )
        if caminho:
            try:
                p = exp.exportar_xlsx(finais, caminho)
                QMessageBox.information(self, "Exportado", f"Salvo em:\n{p}")
            except Exception as exc:
                QMessageBox.critical(self, "Erro", str(exc))

    def _confirmar(self):
        finais = self._linhas_finais()
        if not finais:
            QMessageBox.warning(self, "Nada a salvar", "Não há linhas para salvar.")
            return
        self.on_confirmar(finais)
