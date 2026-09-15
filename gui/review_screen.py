"""Tela de revisão 'Está tudo certo?' com tabela editável.

Permite ao usuário revisar, editar (inline ou via diálogo no duplo clique),
remover linhas e, ao confirmar, salvar no SQLite e exportar CSV/XLSX/XLS/TXT.
"""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QLineEdit, QPlainTextEdit, QCheckBox, QScrollArea,
    QFrame, QSplitter,
)
from PySide6.QtCore import Qt

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
                "Revise os resultados abaixo. Você pode editar qualquer campo, "
                "marcar/desmarcar disponível e remover linhas antes de confirmar."
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
            QAbstractItemView.DoubleClicked | QAbstractItemView.EditKeyPressed
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

        # Resumo cross-references (mostrado ao selecionar uma linha)
        box_xref = QGroupBox("Cross-references da peça selecionada")
        vx = QVBoxLayout()
        self.lbl_xref = QLabel("Selecione uma linha para ver as referências cruzadas.")
        self.lbl_xref.setObjectName("subtitle")
        self.lbl_xref.setWordWrap(True)
        vx.addWidget(self.lbl_xref)
        box_xref.setLayout(vx)
        esquerda.addWidget(box_xref)

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
        self.tabela.itemSelectionChanged.connect(self._mostrar_xref)

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
            },
        )

    def _item_editado(self, item):
        # se o usuário clicar no checkbox de disponível
        if item.column() == self.COL_DISPONIVEL:
            item.setText("Sim" if item.checkState() == Qt.Checked else "Não")

    # -- painel lateral do item selecionado ----------------------------------

    def _criar_painel_item(self) -> QScrollArea:
        """Painel à direita com os dados individuais do item selecionado."""
        box = QGroupBox("Dados do item selecionado")
        form = QFormLayout()
        form.setSpacing(8)

        self.p_codigo = QLineEdit()
        self.p_codigo.setReadOnly(True)
        form.addRow("Código:", self.p_codigo)

        self.p_descricao = QLineEdit()
        form.addRow("Descrição:", self.p_descricao)

        self.p_marca = QLineEdit()
        form.addRow("Marca:", self.p_marca)

        self.p_gtin = QLineEdit()
        form.addRow("GTIN:", self.p_gtin)

        self.p_disponivel = QCheckBox("Disponível")
        form.addRow("Disponível:", self.p_disponivel)

        self.p_observacao = QPlainTextEdit()
        self.p_observacao.setFixedHeight(55)
        form.addRow("Observação:", self.p_observacao)

        self.p_refs = QPlainTextEdit()
        self.p_refs.setPlaceholderText(
            "Uma referência por linha: CODIGO;MARCA\nEx.: 34206891086;BMW"
        )
        form.addRow("Cross-references:", self.p_refs)

        self.p_codigos_apl = QPlainTextEdit()
        self.p_codigos_apl.setPlaceholderText("Um código por linha")
        form.addRow("Códigos da aplicação:", self.p_codigos_apl)

        self.p_aplicacoes = QPlainTextEdit()
        self.p_aplicacoes.setPlaceholderText(
            "Uma aplicação por linha\nEx.: BMW 1 (F40) 2019-"
        )
        form.addRow("Aplicações:", self.p_aplicacoes)

        btn_aplicar = QPushButton("Aplicar alterações ←")
        btn_aplicar.setObjectName("primary")
        btn_aplicar.clicked.connect(self._painel_aplicar)
        form.addRow(btn_aplicar)

        dica = QLabel(
            "Edite os campos e clique em 'Aplicar alterações' para gravar na "
            "linha. Selecione outra linha para trocar o item."
        )
        dica.setObjectName("subtitle")
        dica.setWordWrap(True)
        form.addRow(dica)

        box.setLayout(form)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(box)
        scroll.setMinimumWidth(330)
        scroll.setMinimumHeight(360)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        self._painel_limpar()
        return scroll

    def _painel_limpar(self):
        self.p_codigo.clear()
        self.p_descricao.clear()
        self.p_marca.clear()
        self.p_gtin.clear()
        self.p_disponivel.setChecked(False)
        self.p_observacao.clear()
        self.p_refs.clear()
        self.p_codigos_apl.clear()
        self.p_aplicacoes.clear()

    def _painel_mostrar(self, dados: dict):
        """Preenche o painel com os dados do item selecionado."""
        if not dados or not dados.get("codigo"):
            self._painel_limpar()
            return
        self.p_codigo.setText(str(dados.get("codigo", "")))
        self.p_descricao.setText(str(dados.get("descricao", "")))
        self.p_marca.setText(str(dados.get("marca", "")))
        self.p_gtin.setText(str(dados.get("gtin", "")))
        self.p_disponivel.setChecked(bool(dados.get("disponivel", False)))
        self.p_observacao.setPlainText(str(dados.get("observacao", "")))

        linhas = []
        for ref in dados.get("cross_refs", []) or []:
            if isinstance(ref, dict):
                linhas.append(
                    f"{ref.get('codigo_ref', '')};"
                    f"{ref.get('marca_ref', '') or ''}"
                )
            elif ref:
                linhas.append(
                    f"{ref[0] if len(ref) > 0 else ''};"
                    f"{ref[1] if len(ref) > 1 and ref[1] else ''}"
                )
        self.p_refs.setPlainText("\n".join(linhas))
        self.p_codigos_apl.setPlainText(
            "\n".join(str(c) for c in dados.get("codigos_aplicacao", []))
        )
        self.p_aplicacoes.setPlainText(
            "\n".join(str(a) for a in dados.get("aplicacoes", []))
        )

    def _painel_para_dict(self) -> dict:
        refs = []
        for linha in self.p_refs.toPlainText().splitlines():
            linha = linha.strip()
            if not linha:
                continue
            partes = [p.strip() for p in linha.split(";", 1)]
            cod = partes[0]
            marca = partes[1] if len(partes) > 1 and partes[1] else None
            if cod:
                refs.append({"codigo_ref": cod, "marca_ref": marca})
        return {
            "codigo": self.p_codigo.text(),
            "descricao": self.p_descricao.text(),
            "marca": self.p_marca.text(),
            "gtin": self.p_gtin.text(),
            "disponivel": self.p_disponivel.isChecked(),
            "observacao": self.p_observacao.toPlainText(),
            "cross_refs": refs,
            "codigos_aplicacao": [
                c.strip()
                for c in self.p_codigos_apl.toPlainText().splitlines()
                if c.strip()
            ],
            "aplicacoes": [
                a.strip()
                for a in self.p_aplicacoes.toPlainText().splitlines()
                if a.strip()
            ],
        }

    def _ao_selecionar(self):
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            self._painel_limpar()
            return
        row = rows[0].row()
        if self._linha_vazia(row):
            self._painel_limpar()
            return
        self._painel_mostrar(self._linha_para_dict(row))

    def _painel_aplicar(self):
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            QMessageBox.information(
                self, "Nenhum item selecionado",
                "Clique numa linha da tabela antes de aplicar.")
            return
        row = rows[0].row()
        if self._linha_vazia(row):
            return
        dados = self._painel_para_dict()
        self._aplicar_dict_na_linha(row, dados)
        self._atualizar_resumo()
        self._painel_mostrar(dados)

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
        }

    def _aplicar_dict_na_linha(self, row: int, dados: dict) -> None:
        self.tabela.blockSignals(True)
        self.tabela.item(row, self.COL_DESCRICAO).setText(str(dados.get("descricao", "")))
        self.tabela.item(row, self.COL_MARCA).setText(str(dados.get("marca", "")))
        self.tabela.item(row, self.COL_GTIN).setText(str(dados.get("gtin", "")))
        disp_item = self.tabela.item(row, self.COL_DISPONIVEL)
        disp_item.setCheckState(Qt.Checked if dados.get("disponivel") else Qt.Unchecked)
        disp_item.setText("Sim" if dados.get("disponivel") else "Não")
        self.tabela.item(row, self.COL_OBS).setText(str(dados.get("observacao", "")))
        self.tabela.item(row, self.COL_CODIGO).setData(
            Qt.UserRole, dados.get("cross_refs", [])
        )
        self.tabela.item(row, self.COL_CODIGO).setData(
            Qt.UserRole + 1,
            {
                "aplicacoes": dados.get("aplicacoes", []),
                "codigos_aplicacao": dados.get("codigos_aplicacao", []),
            },
        )
        self.tabela.blockSignals(False)

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
        """Gera o texto no formato do coisas.md."""
        linhas = []
        for r in finais:
            codigo = str(r.get("codigo", "")).upper()
            marca = str(r.get("marca", "")).upper()
            gtin = str(r.get("gtin", "")).upper()
            descricao = str(r.get("descricao", "")).upper()

            cross_refs = r.get("cross_refs", [])
            codigos_extra = []
            for ref in cross_refs:
                if isinstance(ref, dict):
                    codigos_extra.append(ref.get("codigo_ref", ""))
                elif ref:
                    codigos_extra.append(ref[0] if len(ref) > 0 else "")
            vistos = set()
            codigos_unicos = []
            for c in codigos_extra:
                c_upper = c.upper()
                if c_upper and c_upper not in vistos:
                    vistos.add(c_upper)
                    codigos_unicos.append(c_upper)
            codigos_str = ",".join(codigos_unicos)
            if codigos_str:
                codigos_str += ";"

            aplicacoes = r.get("aplicacoes", [])
            aplicacoes_texto = "\n".join(str(a).upper() for a in aplicacoes) if aplicacoes else "-"

            linhas.append(f"{codigo}   {marca}")
            linhas.append("")
            if gtin:
                linhas.append(f"GTIN: {gtin}")
            linhas.append("")
            linhas.append("PRODUTO:")
            linhas.append(descricao)
            linhas.append("")
            linhas.append("INFORMAÇÕES TÉCNICAS:")
            linhas.append(f"CÓDIGOS: {codigos_str}")
            linhas.append(f"MARCA: {marca}")
            linhas.append("")
            linhas.append("APLICAÇÕES:")
            linhas.append(aplicacoes_texto)
            linhas.append("")
            linhas.append("")
        return "\n".join(linhas)

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
