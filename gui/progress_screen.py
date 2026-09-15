"""Tela de progresso mostrada enquanto a automação Playwright roda."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QProgressBar, QPlainTextEdit,
    QPushButton, QDialog, QTextEdit,
)
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont


class PreviewDialog(QDialog):
    """Diálogo que mostra preview do texto no formato .txt."""
    
    def __init__(self, texto: str, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Preview Parcial .txt")
        self.setMinimumSize(500, 400)
        
        layout = QVBoxLayout()
        
        sub = QLabel("Preview dos resultados já coletados no formato .txt:")
        sub.setObjectName("subtitle")
        layout.addWidget(sub)
        
        self.texto = QTextEdit()
        self.texto.setReadOnly(True)
        self.texto.setPlainText(texto)
        self.texto.setFont(QFont("Consolas", 10))
        layout.addWidget(self.texto)
        
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        btn_fechar = QPushButton("Fechar")
        btn_fechar.clicked.connect(self.close)
        btn_layout.addWidget(btn_fechar)
        layout.addLayout(btn_layout)
        
        self.setLayout(layout)


class ProgressScreen(QWidget):
    pausado = Signal()
    continuar = Signal()
    editar_parciais = Signal()
    destravar_solicitado = Signal()

    def __init__(self):
        super().__init__()
        self._pausado = False
        self._resultados_parciais = []
        self._build()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(52, 44, 52, 44)
        root.setSpacing(14)

        eyebrow = QLabel("ETAPA 3 DE 3 · AUTOMAÇÃO EM ANDAMENTO")
        eyebrow.setObjectName("eyebrow")
        root.addWidget(eyebrow)

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
        self.lbl_atual.setObjectName("status")
        root.addWidget(self.lbl_atual)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)
        root.addWidget(self.progress)

        # Botões pause/continue e preview
        btn_layout = QHBoxLayout()
        btn_layout.addStretch(1)
        self.btn_editar = QPushButton("Revisar já coletado…")
        self.btn_editar.setObjectName("secondary")
        self.btn_editar.setToolTip(
            "Pausa a busca e abre a tela de revisão com o que já foi "
            "coletado, para editar e salvar sem perder progresso."
        )
        self.btn_editar.clicked.connect(self._pedir_edicao)
        btn_layout.addWidget(self.btn_editar)

        self.btn_pause = QPushButton("Pausar")
        self.btn_pause.setObjectName("secondary")
        self.btn_pause.clicked.connect(self._toggle_pause)
        btn_layout.addWidget(self.btn_pause)

        self.btn_destravar = QPushButton("Destravar")
        self.btn_destravar.setObjectName("danger")
        self.btn_destravar.setToolTip(
            "Pula a tentativa travada e tenta esse código outra vez no fim do lote."
        )
        self.btn_destravar.clicked.connect(self._pedir_desbloqueio)
        btn_layout.addWidget(self.btn_destravar)
        
        self.btn_preview = QPushButton("Preview parcial .txt")
        self.btn_preview.setObjectName("secondary")
        self.btn_preview.clicked.connect(self._mostrar_preview)
        btn_layout.addWidget(self.btn_preview)
        
        btn_layout.addStretch(1)
        root.addLayout(btn_layout)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setPlaceholderText("Log da execução…")
        root.addWidget(self.log, stretch=1)

        self.setLayout(root)

    def _toggle_pause(self):
        self._pausado = not self._pausado
        if self._pausado:
            self.btn_pause.setText("Continuar")
            self.btn_pause.setObjectName("primary")
            self.pausado.emit()
        else:
            self.btn_pause.setText("Pausar")
            self.btn_pause.setObjectName("secondary")
            self.continuar.emit()
        self.btn_pause.style().unpolish(self.btn_pause)
        self.btn_pause.style().polish(self.btn_pause)

    def _pedir_edicao(self):
        """Pausa (se preciso) e avisa a MainWindow para abrir a revisão."""
        if not self._pausado:
            self._toggle_pause()  # emite pausado → thread para
        self.editar_parciais.emit()

    def _pedir_desbloqueio(self):
        self.btn_destravar.setEnabled(False)
        self.lbl_atual.setText("Destravando no próximo ponto seguro…")
        self.destravar_solicitado.emit()

    def esta_pausado(self) -> bool:
        return self._pausado

    def atualizar_resultados(self, resultados: list[dict]):
        """Atualiza os resultados parciais para preview."""
        self._resultados_parciais = resultados

    def _gerar_preview_txt(self) -> str:
        """Gera o preview no formato .txt do coisas.md."""
        if not self._resultados_parciais:
            return "Nenhum resultado coletado ainda."
        
        linhas = []
        for r in self._resultados_parciais:
            codigo = str(r.get("codigo", "")).upper()
            marca = str(r.get("marca", "")).upper()
            gtin = str(r.get("gtin", "")).upper()
            descricao = str(r.get("descricao", "")).upper()
            
            # Cross-references como códigos
            cross_refs = r.get("cross_refs", [])
            codigos_extra = []
            for ref in cross_refs:
                if isinstance(ref, dict):
                    codigos_extra.append(ref.get("codigo_ref", ""))
                elif ref:
                    codigos_extra.append(ref[0] if len(ref) > 0 else "")
            # Remove duplicados preservando ordem
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
            
            # Aplicações
            aplicacoes = r.get("aplicacoes", [])
            aplicacoes_texto = "\n".join(str(a).upper() for a in aplicacoes) if aplicacoes else "-"
            
            linhas.append(f"{codigo}   {marca}")
            linhas.append("")
            if gtin:
                linhas.append(f"GTIN: {gtin}")
            linhas.append("")
            linhas.append(f"PRODUTO:")
            linhas.append(f"{descricao}")
            linhas.append("")
            linhas.append(f"INFORMAÇÕES TÉCNICAS:")
            linhas.append(f"CÓDIGOS: {codigos_str}")
            linhas.append(f"MARCA: {marca}")
            linhas.append("")
            linhas.append(f"APLICAÇÕES:")
            linhas.append(f"{aplicacoes_texto}")
            linhas.append("")
            linhas.append("")  # Linha em branco entre peças
        
        return "\n".join(linhas)

    def _mostrar_preview(self):
        """Mostra o diálogo de preview."""
        texto = self._gerar_preview_txt()
        dialog = PreviewDialog(texto, self)
        dialog.exec()

    def iniciar(self, total: int):
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self.log.clear()
        self._pausado = False
        self.btn_destravar.setEnabled(True)
        self.btn_pause.setText("Pausar")
        self.btn_pause.setObjectName("secondary")
        self.btn_pause.style().unpolish(self.btn_pause)
        self.btn_pause.style().polish(self.btn_pause)

    def continuar_em_andamento(self):
        """Volta do estado pausado para 'em andamento' (sem emitir sinal)."""
        self._pausado = False
        self.btn_pause.setText("Pausar")
        self.btn_pause.setObjectName("secondary")
        self.btn_pause.style().unpolish(self.btn_pause)
        self.btn_pause.style().polish(self.btn_pause)

    def atualizar(self, index: int, total: int, codigo: str):
        self.btn_destravar.setEnabled(True)
        self.progress.setValue(index)
        self.lbl_atual.setText(
            f"({index}/{total}) Buscando código: {codigo}"
        )
        self.log.appendPlainText(f"[{index}/{total}] {codigo} …")

    def log_erro(self, msg: str):
        self.log.appendPlainText(f"      ! {msg}")
