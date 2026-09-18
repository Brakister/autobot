"""Tela de revisão 'Está tudo certo?' com tabela editável.

Permite revisar e editar as linhas, remover peças e, ao confirmar, salvar no
SQLite e exportar CSV/XLSX/XLS/TXT. Ao clicar numa peça, a ficha .txt dela é
mostrada no painel lateral, editável e com botão de copiar.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog, QMessageBox,
    QGroupBox, QScrollArea, QFrame, QSplitter, QTextEdit, QApplication,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

import html

from gui.ui_utils import flash_sucesso

import database as db
import export as exp


class ReviewScreen(QWidget):
    def __init__(self, resultados: list[dict], on_confirmar,
                 on_adicionar=None, on_salvar_e_voltar=None,
                 modo="final", on_encerrar=None):
        """resultados: lista de dicts (cada um com codigo, descricao, marca,
        fornecedor, disponivel, observacao, cross_refs).
        on_confirmar: callback(lista_final) chamado ao confirmar.
        on_salvar_e_voltar: callback(resultados) chamado ao salvar parcial e voltar.
        modo='parcial': tela chamada no MEIO de uma busca pausada.
            - botão principal vira "Salvar e continuar busca"
            - "Salvar parcial e voltar" vira "Encerrar automação e salvar agora"
            - botão "+ Adicionar códigos" é ocultado.
        on_encerrar: callback(resultados) quando modo='parcial' e o usuário
            clica em "Encerrar automação e salvar agora"."""
        super().__init__()
        self.resultados = resultados
        self.on_confirmar = on_confirmar
        self.on_adicionar = on_adicionar
        self.on_salvar_e_voltar = on_salvar_e_voltar
        self.on_encerrar = on_encerrar
        self.modo = modo
        self._fichas: dict[str, str] = {}
        self._sel_codigo: str | None = None
        self._build()
        self._popular()

    # colunas: codigo | descricao | marca | gtin | disponivel | obs
    COL_CODIGO = 0
    COL_DESCRICAO = 1
    COL_MARCA = 2
    COL_GTIN = 3
    COL_DISPONIVEL = 4
    COL_OBS = 5

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(40, 34, 40, 34)
        root.setSpacing(12)

        if self.modo == "parcial":
            titulo = QLabel("Revisando o que já foi coletado")
            sub = QLabel(
                "A busca está pausada. Revise/edite os resultados já "
                "coletados. Use 'Salvar e continuar' para retomar a busca "
                "com o que salvou, ou 'Encerrar' para parar e salvar agora."
            )
        else:
            titulo = QLabel("Está tudo certo?")
            sub = QLabel(
                "Revise os resultados abaixo. Clique numa peça para ver e "
                "editar a ficha .txt dela (e copiar). Você também pode editar "
                "qualquer campo, marcar/desmarcar disponível e remover linhas."
            )
        eyebrow = QLabel("REVISÃO E EXPORTAÇÃO")
        eyebrow.setObjectName("eyebrow")
        titulo.setObjectName("title")
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(eyebrow)
        root.addWidget(titulo)
        root.addWidget(sub)

        # área central: tabela de resultados à esquerda + detalhes do item à direita
        # (metade/metade, com divisor arrastável pelo usuário)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setChildrenCollapsible(False)

        esquerda_widget = QWidget()
        esquerda = QVBoxLayout()
        esquerda.setContentsMargins(0, 0, 8, 0)
        esquerda.setSpacing(12)

        self.tabela = QTableWidget(0, 6)
        self.tabela.setHorizontalHeaderLabels(
            ["Código", "Descrição", "Marca", "GTIN", "Disponível", "Observação"]
        )
        self.tabela.setEditTriggers(
            QAbstractItemView.EditKeyPressed
        )
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setAlternatingRowColors(True)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(self.COL_DESCRICAO, QHeaderView.Stretch)
        header.setSectionResizeMode(self.COL_OBS, QHeaderView.Stretch)
        self.tabela.verticalHeader().setVisible(False)
        esquerda.addWidget(self.tabela, stretch=1)

        self.tabela.itemChanged.connect(self._item_editado)

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
        esquerda.addLayout(acoes)

        # Exportação rápida
        ex = QHBoxLayout()
        btn_csv = QPushButton("Exportar CSV…")
        btn_csv.clicked.connect(self._exportar_csv)
        btn_xlsx = QPushButton("Exportar XLSX…")
        btn_xlsx.clicked.connect(self._exportar_xlsx)
        btn_xls = QPushButton("Exportar XLS…")
        btn_xls.clicked.connect(self._exportar_xls)
        btn_txt = QPushButton("Exportar .txt…")
        btn_txt.clicked.connect(self._exportar_txt)
        ex.addWidget(btn_csv)
        ex.addWidget(btn_xlsx)
        ex.addWidget(btn_xls)
        ex.addWidget(btn_txt)
        ex.addStretch(1)
        esquerda.addLayout(ex)
        esquerda_widget.setLayout(esquerda)

        self.painel_item = self._criar_painel_item()
        splitter.addWidget(esquerda_widget)
        splitter.addWidget(self.painel_item)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([1, 1])

        root.addWidget(splitter, stretch=1)

        self.tabela.itemSelectionChanged.connect(self._ao_selecionar)

        self.lbl_resumo = QLabel("")
        self.lbl_resumo.setObjectName("ok")
        root.addWidget(self.lbl_resumo)

        btn_linha = QHBoxLayout()
        btn_adicionar = QPushButton("+ Adicionar códigos")
        btn_adicionar.clicked.connect(self._adicionar)
        if self.modo == "parcial":
            btn_adicionar.setVisible(False)
        btn_linha.addWidget(btn_adicionar)
        btn_salvar_voltar = QPushButton(
            "Encerrar automação e salvar agora"
            if self.modo == "parcial" else "Salvar parcial e voltar"
        )
        btn_salvar_voltar.setObjectName("danger" if self.modo == "parcial"
                                       else "secondary")
        btn_salvar_voltar.clicked.connect(self._salvar_e_voltar)
        btn_preview = QPushButton("Preview .txt")
        btn_preview.setObjectName("secondary")
        btn_preview.clicked.connect(self._preview_txt)
        btn_linha.addWidget(btn_preview)
        btn_linha.addStretch(1)
        self.btn_confirmar = QPushButton(
            "Salvar e continuar busca"
            if self.modo == "parcial" else "Confirmar e salvar ✓"
        )
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
        self._fichas.clear()
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

        item_gtin = QTableWidgetItem(str(r.get("gtin", "")))
        self.tabela.setItem(row, self.COL_GTIN, item_gtin)

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
                "aplicacoes": r.get("aplicacoes", []),
                "codigos_aplicacao": r.get("codigos_aplicacao", []),
                "url": r.get("url", ""),
            },
        )

    def _item_editado(self, item):
        # se o usuário clicar no checkbox de disponível
        if item.column() == self.COL_DISPONIVEL:
            item.setText("Sim" if item.checkState() == Qt.Checked else "Não")
            return
        # se o campo editado for da peça em exibição e a ficha ainda não foi
        # personalizada, regenera a ficha para refletir a edição
        codigo = self._sel_codigo
        if codigo and codigo not in self._fichas:
            if self._linha_do_codigo(codigo) == item.row():
                self._set_ficha(exp.texto_ficha(self._linha_para_dict(item.row())))

    # -- painel lateral do item selecionado ----------------------------------

    def _criar_painel_item(self) -> QScrollArea:
        """Painel à direita: ficha .txt da peça selecionada (edita e copia)."""
        box = QGroupBox("Ficha .txt da peça selecionada")
        v = QVBoxLayout()
        v.setSpacing(8)

        # link do produto referenciado no TecDoc (conferência na revisão)
        self.p_link = QLabel()
        self.p_link.setObjectName("subtitle")
        self.p_link.setWordWrap(True)
        self.p_link.setTextFormat(Qt.RichText)
        self.p_link.setOpenExternalLinks(True)
        self.p_link.setTextInteractionFlags(Qt.TextBrowserInteraction)
        v.addWidget(self.p_link)

        self.p_ficha = QTextEdit()
        self.p_ficha.setFont(QFont("Consolas", 10))
        self.p_ficha.setPlaceholderText(
            "Clique numa peça para ver a ficha .txt dela."
        )
        v.addWidget(self.p_ficha, stretch=1)
        self.p_ficha.textChanged.connect(self._on_ficha_editada)

        acoes = QHBoxLayout()
        self.btn_copiar = QPushButton("Copiar")
        self.btn_copiar.setObjectName("primary")
        self.btn_copiar.clicked.connect(self._copiar_ficha)
        acoes.addWidget(self.btn_copiar)
        btn_regenerar = QPushButton("Regenerar da linha")
        btn_regenerar.clicked.connect(self._regenerar_ficha)
        acoes.addWidget(btn_regenerar)
        acoes.addStretch(1)
        v.addLayout(acoes)

        dica = QLabel(
            "Clique numa peça para ver a ficha .txt dela. Edite o texto à "
            "vontade e use 'Copiar'. O texto editado também é usado no "
            "'Preview .txt' e no 'Exportar .txt'."
        )
        dica.setObjectName("subtitle")
        dica.setWordWrap(True)
        v.addWidget(dica)

        box.setLayout(v)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        scroll.setMinimumWidth(360)
        scroll.setMinimumHeight(360)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        self._painel_limpar()
        return scroll

    def _painel_limpar(self):
        self.p_ficha.blockSignals(True)
        self.p_ficha.clear()
        self.p_ficha.blockSignals(False)
        self.p_link.setText("Produto referenciado: selecione uma peça.")
        self._sel_codigo = None

    def _mostrar_link(self, url: str):
        """Mostra o link do produto referenciado (abre no navegador)."""
        url = (url or "").strip()
        if not url:
            self.p_link.setText(
                "Produto referenciado: link não disponível para esta peça.")
            return
        seguro = html.escape(url, quote=True)
        self.p_link.setText(
            f'Produto referenciado: <a href="{seguro}">{seguro}</a>'
        )

    def _linha_do_codigo(self, codigo: str) -> int:
        for row in range(self.tabela.rowCount()):
            it = self.tabela.item(row, self.COL_CODIGO)
            if it and it.text() == codigo:
                return row
        return -1

    def _set_ficha(self, texto: str):
        self.p_ficha.blockSignals(True)
        self.p_ficha.setPlainText(texto)
        self.p_ficha.blockSignals(False)

    def _on_ficha_editada(self):
        """Mantém a edição da ficha atrelada à peça selecionada."""
        codigo = self._sel_codigo
        if not codigo:
            return
        texto = self.p_ficha.toPlainText()
        if texto.strip():
            self._fichas[codigo] = texto
        else:
            self._fichas.pop(codigo, None)

    def _ao_selecionar(self):
        self._on_ficha_editada()
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            self._painel_limpar()
            return
        row = rows[0].row()
        if self._linha_vazia(row):
            self._painel_limpar()
            return
        dados = self._linha_para_dict(row)
        codigo = str(dados.get("codigo", ""))
        self._sel_codigo = codigo
        self._mostrar_link(dados.get("url", ""))
        if codigo in self._fichas:
            self._set_ficha(self._fichas[codigo])
        else:
            self._set_ficha(exp.texto_ficha(dados))

    def _copiar_ficha(self):
        texto = self.p_ficha.toPlainText()
        if not texto.strip():
            QMessageBox.information(
                self, "Nada para copiar", "Selecione uma peça primeiro.")
            return
        QApplication.clipboard().setText(texto)
        flash_sucesso(self.btn_copiar)

    def _regenerar_ficha(self):
        """Descarta a edição e regenera a ficha a partir dos dados da linha."""
        codigo = self._sel_codigo
        if not codigo:
            return
        row = self._linha_do_codigo(codigo)
        if row < 0:
            return
        self._fichas.pop(codigo, None)
        self._set_ficha(exp.texto_ficha(self._linha_para_dict(row)))

    def _linha_vazia(self, row: int) -> bool:
        it = self.tabela.item(row, self.COL_CODIGO)
        return it is None or not it.text()

    def _linha_para_dict(self, row: int) -> dict:
        cross_refs = self.tabela.item(row, self.COL_CODIGO).data(Qt.UserRole) or []
        extras = self.tabela.item(row, self.COL_CODIGO).data(Qt.UserRole + 1) or {}
        return {
            "codigo": self.tabela.item(row, self.COL_CODIGO).text(),
            "descricao": self.tabela.item(row, self.COL_DESCRICAO).text(),
            "marca": self.tabela.item(row, self.COL_MARCA).text(),
            "gtin": self.tabela.item(row, self.COL_GTIN).text(),
            "disponivel": (
                self.tabela.item(row, self.COL_DISPONIVEL).checkState() == Qt.Checked
            ),
            "observacao": self.tabela.item(row, self.COL_OBS).text(),
            "cross_refs": cross_refs,
            "aplicacoes": extras.get("aplicacoes", []),
            "codigos_aplicacao": extras.get("codigos_aplicacao", []),
            "url": extras.get("url", ""),
        }

    # -- leitura ------------------------------------------------------------

    def _x(self):
        return self.resultados

    def _linhas_finais(self) -> list[dict]:
        finais = []
        for row in range(self.tabela.rowCount()):
            codigo = self.tabela.item(row, self.COL_CODIGO).text()
            descricao = self.tabela.item(row, self.COL_DESCRICAO).text()
            marca = self.tabela.item(row, self.COL_MARCA).text()
            gtin = self.tabela.item(row, self.COL_GTIN).text()
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
                "gtin": gtin,
                "aplicacoes": extras.get("aplicacoes", []),
                "codigos_aplicacao": extras.get("codigos_aplicacao", []),
                "url": extras.get("url", ""),
            })
        return finais

    def _atualizar_resumo(self):
        n = self.tabela.rowCount()
        disp = sum(
            1 for row in range(self.tabela.rowCount())
            if self.tabela.item(row, self.COL_DISPONIVEL).checkState() == Qt.Checked
        )
        self.lbl_resumo.setText(f"{n} peça(s) · {disp} disponível(is)")

    # -- ações --------------------------------------------------------------

    def _remover_selecionada(self):
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            return
        rows.sort(key=lambda idx: idx.row(), reverse=True)
        for idx in rows:
            it = self.tabela.item(idx.row(), self.COL_CODIGO)
            if it:
                self._fichas.pop(it.text(), None)
            self.tabela.removeRow(idx.row())
        self._atualizar_resumo()
        self._painel_limpar()

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

    def _exportar_xls(self):
        finais = self._linhas_finais()
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar Excel 97-2003", "resultados.xls", "Excel 97-2003 (*.xls)"
        )
        if caminho:
            try:
                p = exp.exportar_xls(finais, caminho)
                QMessageBox.information(self, "Exportado", f"Salvo em:\n{p}")
            except Exception as exc:
                QMessageBox.critical(self, "Erro", str(exc))

    def _exportar_txt(self):
        finais = self._linhas_finais()
        caminho, _ = QFileDialog.getSaveFileName(
            self, "Salvar TXT", "resultados.txt", "Texto (*.txt)"
        )
        if not caminho:
            return
        try:
            linhas = self._gerar_txt(finais)
            with open(caminho, "w", encoding="utf-8") as f:
                f.write(linhas)
            
            QMessageBox.information(self, "Exportado", f"Salvo em:\n{caminho}")
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))

    def _preview_txt(self):
        """Mostra diálogo com o preview no formato .txt."""
        finais = self._linhas_finais()
        if not finais:
            QMessageBox.information(self, "Sem dados", "Não há linhas para preview.")
            return
        texto = self._gerar_txt(finais)
        from gui.progress_screen import PreviewDialog
        dialog = PreviewDialog(texto, self)
        dialog.exec()

    def _gerar_txt(self, finais: list[dict]) -> str:
        """Gera o texto no formato do coisas.md, usando as fichas editadas."""
        blocos = []
        for r in finais:
            codigo = str(r.get("codigo", ""))
            txt = self._fichas.get(codigo)
            blocos.append(txt if txt is not None else exp.texto_ficha(r))
        return "\n".join(blocos)

    def _confirmar(self):
        finais = self._linhas_finais()
        if not finais:
            QMessageBox.warning(self, "Nada a salvar", "Não há linhas para salvar.")
            return
        self.on_confirmar(finais)

    def _salvar_e_voltar(self):
        finais = self._linhas_finais()
        if not finais:
            QMessageBox.warning(self, "Nada a salvar", "Não há linhas para salvar.")
            return
        if self.modo == "parcial":
            if self.on_encerrar:
                self.on_encerrar(finais)
                return
            QMessageBox.information(
                self, "Não é possível continuar",
                "Modo de retomada não disponível. Feche a busca para salvar.")
            return
        if self.on_salvar_e_voltar:
            self.on_salvar_e_voltar(finais)
        else:
            QMessageBox.information(self, "Salvo", f"{len(finais)} peça(s) pronta(s).")
