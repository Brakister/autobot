"""Entry point do Cadastro Auto."""
import sys
import os
import subprocess
import tempfile

from PySide6.QtCore import QThread, Signal, Qt
from PySide6.QtWidgets import QApplication, QMessageBox, QProgressDialog

import config
import database as db
from gui.main_window import MainWindow
from gui.styles import STYLE
from PySide6.QtGui import QFont
from updater import versao_mais_nova, baixar_instalador


class _CheckThread(QThread):
    """Thread que checa a versão mais recente sem travar a UI."""
    resultado = Signal(object)  # dict | None

    def run(self):
        try:
            info = versao_mais_nova(config.APP_VERSION)
        except Exception:
            info = None
        self.resultado.emit(info)


def _ao_verificar_atualizacao(win, info):
    """Callback thread — mostra diálogo se houver versão nova."""
    if not info:
        return
    versao = info.get("versao", "")
    url = info.get("url", "")
    if not url:
        return
    resposta = QMessageBox.question(
        win, "Atualização disponível",
        f"Uma nova versão do Cadastro Auto está disponível: v{versao}.\n"
        f"Você está na v{config.APP_VERSION}.\n\n"
        f"Notas: {info.get('notas', '')}\n\n"
        "Baixar e instalar agora? O aplicativo será fechado para instalar.",
        QMessageBox.Yes | QMessageBox.No,
        QMessageBox.Yes,
    )
    if resposta != QMessageBox.Yes:
        return
    _baixar_e_instalar(win, url)


def _baixar_e_instalar(win, url: str):
    """Baixa o instalador para a pasta temporária, abre e encerra o app."""
    destino = os.path.join(
        tempfile.gettempdir(),
        f"CadastroAuto-Setup-{config.APP_VERSION}.exe",
    )
    prog = QProgressDialog("Baixando atualização…", "Cancelar", 0, 100, win)
    prog.setWindowTitle("Atualização")
    prog.setWindowModality(Qt.WindowModal)
    prog.setValue(0)

    def _atualizar_pct(pct):
        prog.setValue(pct)

    try:
        baixar_instalador(url, destino, progresso_cb=_atualizar_pct)
    except Exception as exc:
        QMessageBox.warning(win, "Falha ao baixar",
                            f"Não foi possível baixar a atualização:\n{exc}")
        prog.close()
        return

    prog.setValue(100)
    prog.close()

    # abre o instalador (Inno Setup — instala por usuário)
    try:
        os.startfile(destino)  # Windows
    except Exception:
        subprocess.Popen([destino], shell=True)

    QApplication.quit()


def main() -> int:
    config.configurar_playwright()
    db.init_db()

    app = QApplication(sys.argv)
    app.setStyleSheet(STYLE)
    app.setFont(QFont("Segoe UI", 10))

    win = MainWindow()
    win.show()

    # Checar atualização apenas quando o app for executado como executável (frozen)
    if getattr(sys, "frozen", False):
        thread = _CheckThread()
        thread.resultado.connect(lambda info: _ao_verificar_atualizacao(win, info))
        thread.start()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())