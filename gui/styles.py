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

QPushButton#success {
    background-color: #16a34a;
    color: #ffffff;
    border: 1px solid #22c55e;
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 600;
}
QPushButton#success:hover {
    background-color: #22c55e;
}
QPushButton#success:pressed {
    background-color: #1a8f3a;
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

# Tema revisto: aplicado depois das regras legadas para preservar os nomes de
# objetos existentes e modernizar todas as telas de uma vez.
STYLE = """
QWidget { background-color: #0b1220; color: #e5edf8; font-family: "Segoe UI", "Inter", sans-serif; font-size: 13px; }
QMainWindow, QDialog, QStackedWidget { background-color: #0b1220; }
QDialog { border: 1px solid #26364d; }
QLabel#eyebrow { color: #60a5fa; font-size: 11px; font-weight: 700; letter-spacing: 1px; }
QLabel#title { color: #f8fbff; font-size: 28px; font-weight: 700; }
QLabel#subtitle { color: #9aacbf; font-size: 14px; }
QLabel#status { color: #7dd3fc; font-weight: 600; }
QLabel#error { color: #fda4af; font-weight: 600; }
QLabel#ok { color: #86efac; font-weight: 600; }
QLabel#metric { color: #f8fbff; font-size: 20px; font-weight: 700; }

QGroupBox { background-color: #111c2e; border: 1px solid #253650; border-radius: 12px; margin-top: 15px; padding: 16px 14px 14px; font-size: 13px; font-weight: 700; color: #dbeafe; }
QGroupBox::title { subcontrol-origin: margin; left: 14px; padding: 0 6px; color: #bfdbfe; }

QPushButton { min-height: 20px; background-color: #19283d; color: #dce8f8; border: 1px solid #31445f; border-radius: 8px; padding: 8px 14px; font-weight: 600; }
QPushButton:hover { background-color: #263a55; border-color: #4b6688; }
QPushButton:pressed { background-color: #142137; }
QPushButton:disabled { background-color: #142137; color: #65758a; border-color: #203047; }
QPushButton#primary { background-color: #2563eb; color: white; border: 1px solid #3b82f6; }
QPushButton#primary:hover { background-color: #3b82f6; border-color: #60a5fa; }
QPushButton#secondary { background-color: transparent; border-color: #3b4d67; }
QPushButton#secondary:hover { background-color: #1b2b42; }
QPushButton#danger { background-color: #be123c; color: white; border: 1px solid #e11d48; }
QPushButton#danger:hover { background-color: #e11d48; }

QLineEdit, QPlainTextEdit, QTextEdit, QSpinBox, QComboBox { background-color: #0c1626; color: #edf5ff; border: 1px solid #2c405c; border-radius: 8px; padding: 8px 10px; selection-background-color: #2563eb; selection-color: white; }
QLineEdit:hover, QPlainTextEdit:hover, QTextEdit:hover, QComboBox:hover { border-color: #49627f; }
QLineEdit:focus, QPlainTextEdit:focus, QTextEdit:focus, QComboBox:focus { border: 2px solid #3b82f6; padding: 7px 9px; }
QPlainTextEdit { line-height: 1.45; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background-color: #142137; border: 1px solid #31445f; selection-background-color: #2563eb; selection-color: white; }

QCheckBox, QRadioButton { spacing: 8px; color: #c7d5e8; }
QCheckBox::indicator, QRadioButton::indicator { width: 17px; height: 17px; }
QCheckBox::indicator:unchecked { border: 1px solid #526987; border-radius: 4px; background: #0c1626; }
QCheckBox::indicator:checked { border: 1px solid #60a5fa; border-radius: 4px; background: #2563eb; }

QListWidget, QTableWidget, QTableView { background-color: #0c1626; alternate-background-color: #101d30; border: 1px solid #263a55; border-radius: 8px; outline: none; }
QListWidget::item { padding: 8px 10px; border-radius: 5px; }
QListWidget::item:hover { background: #182942; }
QListWidget::item:selected, QTableWidget::item:selected { background: #1d4ed8; color: white; }
QTableWidget::item { padding: 5px; }
QHeaderView::section { background-color: #17263b; color: #cfe0f7; border: none; border-right: 1px solid #30435d; border-bottom: 1px solid #30435d; padding: 9px 8px; font-weight: 700; }
QTableCornerButton::section { background-color: #17263b; }

QProgressBar { background-color: #0c1626; border: 1px solid #2c405c; border-radius: 7px; text-align: center; color: #eaf2fd; height: 18px; font-weight: 600; }
QProgressBar::chunk { background-color: #2563eb; border-radius: 6px; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 4px; }
QScrollBar::handle:vertical { background: #344861; border-radius: 5px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #4b6688; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QToolTip { background-color: #17263b; color: #edf5ff; border: 1px solid #3b4d67; padding: 6px; }
"""
