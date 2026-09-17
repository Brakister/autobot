"""Utilidades de UI compartilhadas (por exemplo: feedback visual de cópia)."""
from PySide6.QtCore import QTimer


def flash_sucesso(
    botao,
    texto="Copiado!",
    original="Copiar",
    ms=1200,
):
    """Pisca o botão em verde por alguns instantes como confirmação de cópia."""
    botao.setText(texto)
    botao.setObjectName("success")
    botao.style().unpolish(botao)
    botao.style().polish(botao)

    def _voltar():
        botao.setText(original)
        botao.setObjectName("primary")
        botao.style().unpolish(botao)
        botao.style().polish(botao)

    QTimer.singleShot(ms, _voltar)