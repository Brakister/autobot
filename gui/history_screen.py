"""Tela de histórico de sessões salvas no SQLite.

Lista as corridas (data, códigos, total, concluída), permite re-exportar e
reabrir uma sessão antiga na revisão.
"""
import json
from datetime import datetime

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView,
    QFileDialog, QMessageBox, QGroupBox,
)
from PySide6.QtCore import Qt

import database as db
import export as exp


def _parse_lista(v) -> list:
    """DB guarda listas como JSON em texto; devolve sempre uma lista."""
    if not v:
        return []
    if isinstance(v, list):
        return v
    try:
        return json.loads(v)
    except Exception:
        return []


def _da_db(row: dict) -> dict:
    """Converte uma linha do banco no formato que a revisão/exportação usam."""
    return {
        "codigo": row["codigo"],
        "numero_artigo": row.get("numero_artigo", "") or "",
        "descricao": row.get("descricao", "") or "",
        "marca": row.get("marca", "") or "",
        "disponivel": bool(row.get("disponivel")),
        "observacao": row.get("observacao", "") or "",
        "cross_refs": [
            {"codigo_ref": r["codigo_ref"], "marca_ref": r["marca_ref"]}
            for r in row.get("cross_refs", [])
        ],
        "gtin": row.get("gtin", "") or "",
        "url": row.get("url", "") or "",
        "aplicacoes": _parse_lista(row.get("aplicacoes")),
        "codigos_aplicacao": _parse_lista(row.get("codigos_aplicacao")),
    }


class HistoryScreen(QWidget):
    """Coluna: data | código(s) | nº peças | concluída
    Detalhe embaixo + botões de exportação/abrir na revisão."""

    COL_DATA = 0
    COL_CODIGOS = 1
    COL_PECAS = 2
    COL_CONCLUIDA = 3

    def __init__(self, on_back=None, on_abrir_revisao=None):
        super().__init__()
        self.on_back = on_back
        self.on_abrir_revisao = on_abrir_revisao
        self._sessoes: list[dict] = []
        self._pecas: list[dict] = []  # sessão selecionada (formato de exportação)
        self._build()
        self._carregar()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(12)

        titulo = QLabel("Histórico de sessões")
        titulo.setObjectName("title")
        root.addWidget(titulo)

        sub = QLabel(
            "Execuções salvas. Selecione uma linha para ver as peças e "
            "re-exportar."
        )
        sub.setObjectName("subtitle")
        sub.setWordWrap(True)
        root.addWidget(sub)

        self.tabela = QTableWidget(0, 4)
        self.tabela.setHorizontalHeaderLabels(
            ["Data", "Código(s)", "Peças", "Concluída"]
        )
        self.tabela.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tabela.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tabela.setAlternatingRowColors(True)
        self.tabela.verticalHeader().setVisible(False)
        header = self.tabela.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionResizeMode(self.COL_CODIGOS, QHeaderView.Stretch)
        self.tabela.itemSelectionChanged.connect(self._selecionou)
        root.addWidget(self.tabela, stretch=2)

        box = QGroupBox("Peças da sessão selecionada")
        v = QVBoxLayout()
        self.lbl_resumo = QLabel("Selecione uma sessão.")
        self.lbl_resumo.setObjectName("subtitle")
        v.addWidget(self.lbl_resumo)
        self.editor = QTableWidget(0, 4)
        self.editor.setHorizontalHeaderLabels(
            ["Código", "Descrição", "Marca", "Disponível"]
        )
        self.editor.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.editor.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch)
        self.editor.verticalHeader().setVisible(False)
        v.addWidget(self.editor, stretch=1)
        box.setLayout(v)
        root.addWidget(box, stretch=3)

        # ações
        acoes = QHBoxLayout()
        btn_reabrir = QPushButton("Abrir como revisão")
        btn_reabrir.setObjectName("primary")
        btn_reabrir.clicked.connect(self._reabrir)
        acoes.addWidget(btn_reabrir)
        acoes.addStretch(1)
        btn_csv = QPushButton("Exportar CSV…")
        btn_csv.clicked.connect(lambda: self._exportar("csv"))
        btn_xlsx = QPushButton("Exportar Excel…")
        btn_xlsx.clicked.connect(lambda: self._exportar("xlsx"))
        btn_txt = QPushButton("Exportar fichas…")
        btn_txt.clicked.connect(lambda: self._exportar("txt"))
        btn_limpar_cache = QPushButton("Limpar cache de buscas")
        btn_limpar_cache.clicked.connect(self._limpar_cache)
        acoes.addWidget(btn_csv)
        acoes.addWidget(btn_xlsx)
        acoes.addWidget(btn_txt)
        acoes.addWidget(btn_limpar_cache)
        root.addLayout(acoes)

        btn_linha = QHBoxLayout()
        btn_voltar = QPushButton("← Voltar")
        btn_voltar.clicked.connect(self._voltar)
        btn_linha.addWidget(btn_voltar)
        btn_linha.addStretch(1)
        root.addLayout(btn_linha)

        self.setLayout(root)

    # -- dados ---------------------------------------------------------------

    def _carregar(self):
        self._sessoes = db.todas_sessoes() or []
        self.tabela.setRowCount(0)
        for s in self._sessoes:
            row = self.tabela.rowCount()
            self.tabela.insertRow(row)
            self.tabela.setItem(
                row, self.COL_DATA,
                QTableWidgetItem(self._fmt_data(s.get("criada_em", ""))),
            )
            self.tabela.setItem(
                row, self.COL_CODIGOS,
                QTableWidgetItem(s.get("codigo_busca", "") or ""),
            )
            self.tabela.setItem(
                row, self.COL_PECAS,
                QTableWidgetItem(str(s.get("total_pecas", 0))),
            )
            concluida = "Sim" if s.get("concluida") else "Não"
            self.tabela.setItem(
                row, self.COL_CONCLUIDA, QTableWidgetItem(concluida),
            )
            self.tabela.item(row, self.COL_DATA).setData(
                Qt.UserRole, s.get("id", "")
            )

    @staticmethod
    def _fmt_data(iso: str) -> str:
        if not iso:
            return ""
        try:
            return datetime.fromisoformat(iso).strftime("%d/%m/%Y %H:%M")
        except Exception:
            return iso

    def _sessao_selecionada(self) -> dict | None:
        rows = self.tabela.selectionModel().selectedRows()
        if not rows:
            return None
        row = rows[0].row()
        sid = self.tabela.item(row, self.COL_DATA).data(Qt.UserRole)
        return next((s for s in self._sessoes if s.get("id") == sid), None)

    def _selecionou(self):
        sessao = self._sessao_selecionada()
        if not sessao:
            return
        pecas = db.pecas_da_sessao(sessao["id"]) or []
        self._pecas = [_da_db(p) for p in pecas]
        self._preencher_editor()

    def _preencher_editor(self):
        self.editor.setRowCount(0)
        disp = 0
        for p in self._pecas:
            row = self.editor.rowCount()
            self.editor.insertRow(row)
            self.editor.setItem(row, 0, QTableWidgetItem(p.get("codigo", "")))
            self.editor.setItem(row, 1,
                                QTableWidgetItem(p.get("descricao", "")))
            self.editor.setItem(row, 2, QTableWidgetItem(p.get("marca", "")))
            self.editor.setItem(
                row, 3,
                QTableWidgetItem("Sim" if p.get("disponivel") else "Não"),
            )
            if p.get("disponivel"):
                disp += 1
        self.lbl_resumo.setText(
            f"{len(self._pecas)} peça(s) · {disp} disponível(is)"
        )

    # -- ações ---------------------------------------------------------------

    def _reabrir(self):
        sessao = self._sessao_selecionada()
        if not sessao:
            QMessageBox.information(self, "Nada selecionado",
                                    "Selecione uma sessão primeiro.")
            return
        # atualiza os dados antes de abrir (garante o que está no banco)
        self._pecas = [_da_db(p) for p in
                       (db.pecas_da_sessao(sessao["id"]) or [])]
        if self.on_abrir_revisao:
            self.on_abrir_revisao(sessao["id"], self._pecas)

    def _exportar(self, tipo: str):
        if not self._pecas:
            QMessageBox.information(self, "Nada para exportar",
                                    "Selecione uma sessão com peças.")
            return
        sugestao = f"{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        if tipo == "csv":
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar CSV", f"resultados_{sugestao}.csv",
                "CSV (*.csv)")
            fun = lambda p: exp.exportar_csv(self._pecas, p)
        elif tipo == "xlsx":
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar Excel", f"resultados_{sugestao}.xlsx",
                "Excel (*.xlsx)")
            fun = lambda p: exp.exportar_xlsx(self._pecas, p)
        else:
            caminho, _ = QFileDialog.getSaveFileName(
                self, "Salvar fichas", f"fichas_{sugestao}.txt",
                "Texto (*.txt)")
            fun = lambda p: exp.exportar_txt_fichas(self._pecas, p)
        if not caminho:
            return
        try:
            salvo = fun(caminho)
            QMessageBox.information(self, "Exportado", f"Salvo em:\n{salvo}")
        except Exception as exc:
            QMessageBox.critical(self, "Erro", str(exc))

    def _limpar_cache(self):
        resp = QMessageBox.question(
            self, "Limpar cache",
            "Isso apaga os resultados em cache (não apaga sessões salvas). "
            "Continuar?",
        )
        if resp == QMessageBox.Yes:
            db.limpar_cache()
            QMessageBox.information(self, "Cache limpo",
                                    "Cache de buscas removido.")

    def _voltar(self):
        if self.on_back:
            self.on_back()