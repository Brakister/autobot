"""Tela de login/senha do TecDoc."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLineEdit, QPushButton, QLabel, QGroupBox,
    QCheckBox,
)
from PySide6.QtCore import Qt

import database as db


class LoginScreen(QWidget):
    def __init__(self, on_continue):
        super().__init__()
        self.on_continue = on_continue
        self._build()

    def _build(self):
        root = QVBoxLayout()
        root.setContentsMargins(40, 40, 40, 40)
        root.setSpacing(16)
        root.addStretch(1)

        titulo = QLabel("Cadastro Auto · TecDoc")
        titulo.setObjectName("title")
        titulo.setAlignment(Qt.AlignCenter)
        root.addWidget(titulo)

        sub = QLabel("Entre com suas credenciais do TecAlliance TecDoc")
        sub.setObjectName("subtitle")
        sub.setAlignment(Qt.AlignCenter)
        root.addWidget(sub)

        box = QGroupBox("Credenciais")
        form = QVBoxLayout()
        form.setSpacing(10)

        self.login_edit = QLineEdit()
        self.login_edit.setPlaceholderText("Usuário / e-mail")
        form.addWidget(self.login_edit)

        self.senha_edit = QLineEdit()
        self.senha_edit.setPlaceholderText("Senha")
        self.senha_edit.setEchoMode(QLineEdit.Password)
        form.addWidget(self.senha_edit)

        self.headless_check = QCheckBox(
            "Executar em segundo plano (sem abrir o navegador)"
        )
        form.addWidget(self.headless_check)

        btn_linha = QHBoxLayout()
        self.btn_avancar = QPushButton("Continuar")
        self.btn_avancar.setObjectName("primary")
        self.btn_avancar.clicked.connect(self._validar)
        btn_linha.addStretch(1)
        btn_linha.addWidget(self.btn_avancar)
        btn_linha.addStretch(1)
        form.addLayout(btn_linha)

        self.erro = QLabel("")
        self.erro.setObjectName("error")
        self.erro.setAlignment(Qt.AlignCenter)
        form.addWidget(self.erro)

        box.setLayout(form)
        root.addWidget(box)

        root.addStretch(1)
        self.setLayout(root)

        self._preencher_salvo()

    def _preencher_salvo(self):
        """Preenche com credenciais salvas da última vez (usuário)."""
        usuario = db.get_config("tecdoc_usuario")
        if usuario:
            self.login_edit.setText(usuario)

    def _validar(self):
        usuario = self.login_edit.text().strip()
        senha = self.senha_edit.text()
        if not usuario or not senha:
            self.erro.setText("Preencha usuário e senha.")
            return
        self.erro.setText("")
        # salva apenas o usuário (nunca a senha em claro)
        db.set_config("tecdoc_usuario", usuario)
        self.on_continue(usuario, senha, self.headless_check.isChecked())
