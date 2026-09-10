"""Folha de estilos QSS (tema escuro) para o app."""

STYLE = """
QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: 'Segoe UI', sans-serif;
    font-size: 13px;
}
QMainWindow, QDialog {
    background-color: #1e1e2e;
}
QStackedWidget {
    background-color: #1e1e2e;
}

/* Botões */
QPushButton {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}
QPushButton:hover {
    background-color: #45475a;
}
QPushButton:pressed {
    background-color: #585b70;
}
QPushButton:disabled {
    background-color: #313244;
    color: #6c7086;
    border-color: #313244;
}
QPushButton#primary {
    background-color: #89b4fa;
    color: #11111b;
    border: none;
}
QPushButton#primary:hover {
    background-color: #a6c8ff;
}
QPushButton#secondary {
    background-color: #313244;
    border: 1px solid #45475a;
}
QPushButton#secondary:hover {
    background-color: #45475a;
}
QPushButton#danger {
    background-color: #f38ba8;
    color: #11111b;
    border: none;
}
QPushButton#danger:hover {
    background-color: #f5a3bb;
}

/* Campos de texto */
QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 8px;
    selection-background-color: #89b4fa;
    selection-color: #11111b;
}
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus {
    border-color: #89b4fa;
}

/* ComboBox */
QComboBox {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    padding: 6px 8px;
}
QComboBox QAbstractItemView {
    background-color: #313244;
    selection-background-color: #89b4fa;
    selection-color: #11111b;
    border: 1px solid #45475a;
}

/* Checkbox / Radio */
QCheckBox, QRadioButton {
    spacing: 8px;
}
QCheckBox::indicator, QRadioButton::indicator {
    width: 16px;
    height: 16px;
}

/* GroupBox */
QGroupBox {
    border: 1px solid #45475a;
    border-radius: 8px;
    margin-top: 14px;
    padding-top: 8px;
    font-weight: 600;
}
QGroupBox::title {
    subcontrol-origin: margin;
    left: 10px;
    padding: 0 4px;
    color: #a6adc8;
}

/* Tabelas */
QTableWidget, QTableView {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    gridline-color: #313244;
    border: 1px solid #313244;
    border-radius: 6px;
    selection-background-color: #45475a;
}
QHeaderView::section {
    background-color: #313244;
    color: #cdd6f4;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    padding: 6px;
    font-weight: 600;
}
QTableCornerButton::section {
    background-color: #313244;
}

/* Progressbar */
QProgressBar {
    background-color: #313244;
    border: 1px solid #45475a;
    border-radius: 6px;
    text-align: center;
    color: #cdd6f4;
    height: 20px;
}
QProgressBar::chunk {
    background-color: #89b4fa;
    border-radius: 5px;
}

/* Labels de título */
QLabel#title {
    font-size: 22px;
    font-weight: 700;
    color: #ffffff;
}
QLabel#subtitle {
    color: #a6adc8;
}
QLabel#error {
    color: #f38ba8;
    font-weight: 600;
}
QLabel#ok {
    color: #a6e3a1;
}
"""