"""Janela principal: orquestra o fluxo login → input → marcas → progresso → revisão → salvar."""
from PySide6.QtWidgets import (
    QMainWindow, QStackedWidget, QMessageBox,
)
from PySide6.QtCore import QThread, Signal

import database as db
import export as exp
from gui.login_screen import LoginScreen
from gui.input_screen import InputScreen
from gui.brand_filter import BrandFilterScreen
from gui.progress_screen import ProgressScreen
from gui.review_screen import ReviewScreen


class _BuscaThread(QThread):
    """Thread que roda a automação Playwright sem travar a GUI."""

    progresso = Signal(int, int, str)
    resultado_parcial = Signal(dict)
    concluido = Signal(list)
    falhou = Signal(str)
    mensagem = Signal(str)

    def __init__(self, login, senha, codigos, marcas, headless):
        super().__init__()
        self.login = login
        self.senha = senha
        self.codigos = codigos
        self.marcas = marcas
        self.headless = headless
        self._pausado = False

    def pausar(self):
        self._pausado = True

    def continuar(self):
        self._pausado = False

    def _aguardar_se_pausado(self):
        while self._pausado:
            self.msleep(100)

    def run(self):
        import tecdoc
        try:
            resultados = tecdoc.executar_busca(
                self.login, self.senha, self.codigos, self.marcas,
                headless=self.headless,
                on_progress=lambda i, t, c: self.progresso.emit(i, t, c),
                on_mensagem=lambda m: self.mensagem.emit(m),
                on_pausa=lambda: self._aguardar_se_pausado(),
                on_resultado=lambda r: self.resultado_parcial.emit(r.to_dict()),
            )
            self.concluido.emit([r.to_dict() for r in resultados])
        except Exception as exc:
            self.falhou.emit(str(exc))


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Cadastro Auto · TecDoc")
        self.resize(1000, 720)
        self.codigos: list[str] = []
        self.codigos_sessao: list = []
        self.marcas: list[str] = []
        self.resultados_acumulados: list[dict] = []
        self.headless = False

        self.stack = QStackedWidget()
        self.setCentralWidget(self.stack)

        self.login_screen = LoginScreen(self._pos_login)
        self.input_screen = InputScreen(self._pos_input)
        self.brand_screen = BrandFilterScreen([], self._pos_brand)
        self.progress_screen = ProgressScreen()
        self.review_screen = None  # criado quando há resultados

        self.stack.addWidget(self.login_screen)   # 0
        self.stack.addWidget(self.input_screen)   # 1
        self.stack.addWidget(self.brand_screen)   # 2
        self.stack.addWidget(self.progress_screen)  # 3

    # -- navegação -----------------------------------------------------------

    def _pos_login(self, usuario: str, senha: str, headless: bool = False):
        self.usuario = usuario
        self.senha = senha
        self.headless = headless
        self.stack.setCurrentIndex(1)

    def _pos_input(self, codigos: list):
        self.codigos = codigos
        self.codigos_sessao.extend(codigos)
        marcas_das_linhas = [
            str(item.get("marca", "")).strip()
            for item in codigos if isinstance(item, dict)
        ]
        # Se TODOS os códigos já têm marca informada, pula a tela de marcas.
        if marcas_das_linhas and all(marcas_das_linhas):
            self._pos_brand(sorted(set(marcas_das_linhas)))
            return
        self.stack.setCurrentIndex(2)

    def _pos_brand(self, marcas: list[str]):
        self.marcas = marcas
        self._iniciar_busca()

    # -- busca ---------------------------------------------------------------

    def _iniciar_busca(self):
        if len(self.marcas) == 0:
            QMessageBox.information(
                self, "Sem marcas",
                "Nenhuma marca selecionada. Será considerada a primeira "
                "peça encontrada para cada código.",
            )
        self.progress_screen.iniciar(len(self.codigos))
        self.stack.setCurrentIndex(3)

        self.thread = _BuscaThread(
            self.usuario, self.senha, self.codigos, self.marcas, self.headless
        )
        self.thread.progresso.connect(self._on_progresso)
        self.thread.resultado_parcial.connect(self._on_resultado_parcial)
        self.thread.concluido.connect(self._on_concluido)
        self.thread.falhou.connect(self._on_falha)
        self.thread.mensagem.connect(self._on_mensagem)
        self.progress_screen.pausado.connect(self.thread.pausar)
        self.progress_screen.continuar.connect(self.thread.continuar)
        self.thread.start()

    def _on_progresso(self, index: int, total: int, codigo: str):
        self.progress_screen.atualizar(index, total, codigo)

    def _on_resultado_parcial(self, resultado: dict):
        self.resultados_acumulados.append(resultado)
        self.progress_screen.atualizar_resultados(self.resultados_acumulados)

    def _on_mensagem(self, msg: str):
        self.progress_screen.log_erro(msg)

    def _on_concluido(self, resultados: list[dict]):
        self.resultados_acumulados = resultados
        self.progress_screen.atualizar_resultados(self.resultados_acumulados)
        self._mostrar_revisao(self.resultados_acumulados)

    def _on_falha(self, msg: str):
        self.progress_screen.log_erro(msg)
        QMessageBox.critical(
            self, "Erro na automação",
            f"A automação falhou:\n{msg}\n\nVerifique os seletores no tecdoc.py.",
        )
        self.stack.setCurrentIndex(1)

    # -- revisão -------------------------------------------------------------

    def _mostrar_revisao(self, resultados: list[dict]):
        self.review_screen = ReviewScreen(
            resultados, self._salvar, self._adicionar_codigos,
            self._salvar_parcial_e_voltar
        )
        if self.stack.indexOf(self.review_screen) == -1:
            self.stack.addWidget(self.review_screen)
        self.stack.setCurrentWidget(self.review_screen)

    def _adicionar_codigos(self):
        """Volta para um novo lote mantendo os resultados já coletados."""
        self.input_screen.limpar()
        self.stack.setCurrentWidget(self.input_screen)

    def _salvar_parcial_e_voltar(self, resultados_parciais: list[dict]):
        """Salva parcialmente e volta para input para adicionar mais códigos."""
        # Salva no SQLite
        sid = db.criar_sessao("; ".join(
            item["codigo"] if isinstance(item, dict) else str(item)
            for item in self.codigos_sessao[:20]
        ))
        for r in resultados_parciais:
            referencias = []
            for ref in r.get("cross_refs", []):
                if isinstance(ref, dict):
                    referencias.append(
                        (ref.get("codigo_ref", ""), ref.get("marca_ref"))
                    )
                elif ref:
                    referencias.append((ref[0], ref[1] if len(ref) > 1 else None))
            db.salvar_peca(
                sessao_id=sid,
                codigo=r["codigo"],
                descricao=r.get("descricao"),
                marca=r.get("marca"),
                fornecedor=None,
                disponivel=r.get("disponivel", False),
                observacao=r.get("observacao"),
                cross_refs=referencias,
                aplicacoes=r.get("aplicacoes", []),
                codigos_aplicacao=r.get("codigos_aplicacao", []),
            )
        db.concluir_sessao(sid)
        
        # Exporta parcial
        try:
            csv_path = exp.exportar_csv(resultados_parciais)
            xlsx_path = exp.exportar_xlsx(resultados_parciais)
            xls_path = exp.exportar_xls(resultados_parciais)
        except Exception as exc:
            csv_path = f"(falha: {exc})"
            xlsx_path = ""
            xls_path = ""
        
        QMessageBox.information(
            self, "Salvo parcialmente",
            f"{len(resultados_parciais)} peça(s) salva(s).\n\n"
            f"CSV: {csv_path}\nExcel: {xlsx_path}\nXLS: {xls_path}\n\n"
            f"Retornando para adicionar mais códigos."
        )
        
        # Limpa resultados acumulados e volta para input
        self.resultados_acumulados = []
        self.codigos_sessao = []
        self.input_screen.limpar()
        self.stack.setCurrentWidget(self.input_screen)

    def _salvar(self, finais: list[dict]):
        # 1) cria sessão
        sid = db.criar_sessao("; ".join(
            item["codigo"] if isinstance(item, dict) else str(item)
            for item in self.codigos_sessao[:20]
        ))
        # 2) salva peças
        for r in finais:
            referencias = []
            for ref in r.get("cross_refs", []):
                if isinstance(ref, dict):
                    referencias.append(
                        (ref.get("codigo_ref", ""), ref.get("marca_ref"))
                    )
                elif ref:
                    referencias.append((ref[0], ref[1] if len(ref) > 1 else None))
            db.salvar_peca(
                sessao_id=sid,
                codigo=r["codigo"],
                descricao=r.get("descricao"),
                marca=r.get("marca"),
                fornecedor=None,
                disponivel=r.get("disponivel", False),
                observacao=r.get("observacao"),
                cross_refs=referencias,
                aplicacoes=r.get("aplicacoes", []),
                codigos_aplicacao=r.get("codigos_aplicacao", []),
            )
        db.concluir_sessao(sid)

        # 3) exporta automático para a pasta exports
        try:
            csv_path = exp.exportar_csv(finais)
            xlsx_path = exp.exportar_xlsx(finais)
            xls_path = exp.exportar_xls(finais)
        except Exception as exc:
            csv_path = f"(falha: {exc})"
            xlsx_path = ""
            xls_path = ""

        QMessageBox.information(
            self, "Salvo com sucesso",
            f"{len(finais)} peça(s) salva(s) na sessão.\n\n"
            f"CSV: {csv_path}\nExcel: {xlsx_path}\nXLS: {xls_path}\n\n"
            f"Fechando o aplicativo.",
        )
        self.close()
