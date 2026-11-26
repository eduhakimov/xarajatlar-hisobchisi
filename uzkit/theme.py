"""Zamonaviy yorug' / qorong'i mavzu (Fluent uslubiga yaqin)."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

PALETTES = {
    "light": {
        "bg": "#f5f6f8", "surface": "#ffffff", "surface2": "#eef0f4", "border": "#d9dde5",
        "text": "#1c1f26", "muted": "#5f6675", "hover": "#e6e9ef",
    },
    "dark": {
        "bg": "#1b1d22", "surface": "#24272e", "surface2": "#2d3139", "border": "#3a3f4a",
        "text": "#e8eaef", "muted": "#a2a9b8", "hover": "#323742",
    },
}


def system_is_dark() -> bool:
    try:
        import winreg
        k = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                           r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
        v, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return v == 0
    except Exception:
        return False


def resolve_mode(mode: str) -> str:
    if mode == "system":
        return "dark" if system_is_dark() else "light"
    return mode if mode in PALETTES else "light"


def _shade(hex_color: str, factor: float) -> str:
    c = QColor(hex_color)
    h, s, l, a = c.getHslF()
    l = max(0.0, min(1.0, l * factor))
    c.setHslF(h, s, l, a)
    return c.name()


def _arrow_files(color: str) -> tuple:
    """Spinbox/combobox o'qlari uchun kichik SVG fayllar (rang mavzuga mos)."""
    import tempfile
    from pathlib import Path
    d = Path(tempfile.gettempdir()) / "BahtiyorSoft_ui"
    d.mkdir(exist_ok=True)
    c = color.lstrip("#")
    up, down = d / f"up_{c}.svg", d / f"down_{c}.svg"
    tpl = ('<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10" viewBox="0 0 10 10">'
           '<path d="{d}" fill="none" stroke="#{c}" stroke-width="1.6" stroke-linecap="round" '
           'stroke-linejoin="round"/></svg>')
    if not up.exists():
        up.write_text(tpl.format(d="M2 6.5 L5 3.5 L8 6.5", c=c), encoding="utf-8")
    if not down.exists():
        down.write_text(tpl.format(d="M2 3.5 L5 6.5 L8 3.5", c=c), encoding="utf-8")
    return up.as_posix(), down.as_posix()


def _font() -> str:
    """app.json "font" — dasturning asosiy shrifti (Windows 10/11 da bor bo'lgani: Segoe UI, Segoe UI Variable
    Display, Bahnschrift, Calibri, Cambria, Candara, Corbel, Consolas...). Default: Segoe UI."""
    try:
        from . import app as appmod
        return appmod.META.get("font") or "Segoe UI"
    except Exception:
        return "Segoe UI"


def build_qss(mode: str, accent: str, p: dict = None) -> str:
    p = p or PALETTES[mode]
    up, down = _arrow_files(p["muted"])
    acc_hover = _shade(accent, 1.12 if mode == "dark" else 0.9)
    acc_press = _shade(accent, 0.8)
    return f"""
* {{ font-family: "{_font()}", "Segoe UI", Arial; font-size: 10pt; }}
QMainWindow, QDialog {{ background: {p['bg']}; color: {p['text']}; }}
QWidget {{ color: {p['text']}; }}
QToolTip {{ background: {p['surface']}; color: {p['text']}; border: 1px solid {p['border']}; padding: 4px; }}
QMenuBar {{ background: {p['surface']}; border-bottom: 1px solid {p['border']}; }}
QMenuBar::item {{ padding: 6px 10px; background: transparent; }}
QMenuBar::item:selected {{ background: {p['hover']}; border-radius: 4px; }}
QMenu {{ background: {p['surface']}; border: 1px solid {p['border']}; padding: 4px; }}
QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
QMenu::item:selected {{ background: {p['hover']}; }}
QStatusBar {{ background: {p['surface']}; border-top: 1px solid {p['border']}; color: {p['muted']}; }}
QFrame#Card {{ background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 10px; }}
QLabel#Title {{ font-size: 16pt; font-weight: 600; }}
QLabel#Subtitle {{ color: {p['muted']}; }}
QLabel#Muted {{ color: {p['muted']}; }}
QLabel#SectionTitle {{ font-size: 11pt; font-weight: 600; }}
QPushButton {{ background: {p['surface2']}; border: 1px solid {p['border']}; border-radius: 6px;
               padding: 7px 14px; min-height: 18px; }}
QPushButton:hover {{ background: {p['hover']}; }}
QPushButton:pressed {{ background: {p['border']}; }}
QPushButton:disabled {{ color: {p['muted']}; background: {p['surface2']}; }}
QPushButton#Primary {{ background: {accent}; color: white; border: 1px solid {accent}; font-weight: 600; }}
QPushButton#Primary:hover {{ background: {acc_hover}; }}
QPushButton#Primary:pressed {{ background: {acc_press}; }}
QPushButton#Primary:disabled {{ background: {p['border']}; border-color: {p['border']}; color: {p['muted']}; }}
QPushButton#Danger {{ background: #d64545; color: white; border: 1px solid #d64545; }}
QPushButton#Danger:hover {{ background: #c03a3a; }}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QDateEdit, QTimeEdit, QDateTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {p['surface']}; border: 1px solid {p['border']}; border-radius: 6px; padding: 5px 8px;
    selection-background-color: {accent}; selection-color: white; }}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus, QTextEdit:focus,
QDateEdit:focus, QTimeEdit:focus, QDateTimeEdit:focus {{ border: 1px solid {accent}; }}
QAbstractSpinBox {{ padding-right: 22px; }}
QAbstractSpinBox::up-button {{ subcontrol-origin: border; subcontrol-position: top right; width: 20px;
    border: none; background: transparent; }}
QAbstractSpinBox::down-button {{ subcontrol-origin: border; subcontrol-position: bottom right; width: 20px;
    border: none; background: transparent; }}
QAbstractSpinBox::up-button:hover, QAbstractSpinBox::down-button:hover {{ background: {p['hover']}; }}
QAbstractSpinBox::up-arrow {{ image: url({up}); width: 10px; height: 10px; }}
QAbstractSpinBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox::down-arrow {{ image: url({down}); width: 10px; height: 10px; }}
QComboBox QAbstractItemView {{ background: {p['surface']}; border: 1px solid {p['border']};
    selection-background-color: {accent}; selection-color: white; }}
QTableView, QTreeView, QListView, QTableWidget, QTreeWidget, QListWidget {{
    background: {p['surface']}; alternate-background-color: {p['surface2']}; border: 1px solid {p['border']};
    border-radius: 8px; gridline-color: {p['border']}; selection-background-color: {accent}; selection-color: white; }}
QHeaderView::section {{ background: {p['surface2']}; color: {p['text']}; padding: 6px; border: none;
    border-right: 1px solid {p['border']}; border-bottom: 1px solid {p['border']}; font-weight: 600; }}
QTabWidget::pane {{ border: 1px solid {p['border']}; border-radius: 8px; background: {p['surface']}; top: -1px; }}
QTabBar::tab {{ background: transparent; padding: 8px 16px; border-bottom: 2px solid transparent; color: {p['muted']}; }}
QTabBar::tab:selected {{ color: {p['text']}; border-bottom: 2px solid {accent}; font-weight: 600; }}
QTabBar::tab:hover {{ color: {p['text']}; }}
QProgressBar {{ background: {p['surface2']}; border: none; border-radius: 5px; height: 10px; text-align: center; }}
QProgressBar::chunk {{ background: {accent}; border-radius: 5px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; }}
QGroupBox {{ border: 1px solid {p['border']}; border-radius: 8px; margin-top: 14px; padding-top: 8px; }}
QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 4px; font-weight: 600; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {p['border']}; border-radius: 4px; min-height: 30px; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {p['border']}; border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ width: 0; height: 0; }}
QListWidget#NavList {{ background: {p['surface']}; border: none; border-right: 1px solid {p['border']};
    border-radius: 0; padding: 6px; outline: 0; }}
QListWidget#NavList::item {{ padding: 9px 10px; border-radius: 6px; margin: 1px 0; }}
QListWidget#NavList::item:selected {{ background: {p['hover']}; color: {p['text']}; font-weight: 600;
    border-left: 3px solid {accent}; }}
QListWidget#NavList::item:hover {{ background: {p['hover']}; }}
QFrame#DropArea {{ border: 2px dashed {p['border']}; border-radius: 10px; background: {p['surface']}; }}
QFrame#DropArea[active="true"] {{ border-color: {accent}; background: {p['hover']}; }}
QSlider::groove:horizontal {{ height: 4px; background: {p['border']}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {accent}; width: 14px; height: 14px; margin: -6px 0; border-radius: 7px; }}
"""


def apply_theme(app: QApplication, mode: str, accent: str = "#2563eb") -> str:
    """Mavzuni qo'llaydi va haqiqiy rejimni ('light'/'dark') qaytaradi."""
    real = resolve_mode(mode)
    app.setStyle("Fusion")
    try:  # app.json "palette": {"light": {...}, "dark": {...}} — dasturga xos fon/sirt ranglari
        from . import app as appmod
        over = (appmod.META.get("palette", {}) or {}).get(real, {})
    except Exception:
        over = {}
    p = {**PALETTES[real], **over}
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(p["bg"]))
    pal.setColor(QPalette.WindowText, QColor(p["text"]))
    pal.setColor(QPalette.Base, QColor(p["surface"]))
    pal.setColor(QPalette.AlternateBase, QColor(p["surface2"]))
    pal.setColor(QPalette.Text, QColor(p["text"]))
    pal.setColor(QPalette.Button, QColor(p["surface2"]))
    pal.setColor(QPalette.ButtonText, QColor(p["text"]))
    pal.setColor(QPalette.Highlight, QColor(accent))
    pal.setColor(QPalette.HighlightedText, QColor("#ffffff"))
    pal.setColor(QPalette.PlaceholderText, QColor(p["muted"]))
    pal.setColor(QPalette.ToolTipBase, QColor(p["surface"]))
    pal.setColor(QPalette.ToolTipText, QColor(p["text"]))
    pal.setColor(QPalette.Link, QColor(accent))
    pal.setColor(QPalette.Disabled, QPalette.Text, QColor(p["muted"]))
    pal.setColor(QPalette.Disabled, QPalette.ButtonText, QColor(p["muted"]))
    app.setPalette(pal)
    app.setStyleSheet(build_qss(real, accent, p) + _app_style(real, accent))
    return real


def _app_style(mode: str, accent: str) -> str:
    """Dasturning o'ziga xos uslubi: assets/style.qss (umumiy) va assets/style_dark.qss / style_light.qss.

    Fayllarda {accent}, {bg}, {surface}, {surface2}, {border}, {text}, {muted}, {hover} o'rinbosarlari ishlaydi.
    Bu har bir dasturga alohida, takrorlanmas ko'rinish berish uchun.
    """
    try:
        from .paths import resource
        vals = dict(PALETTES[mode])
        try:
            from . import app as _a
            vals.update((_a.META.get("palette", {}) or {}).get(mode, {}))
        except Exception:
            pass
        vals["accent"] = accent
        try:
            from . import app as appmod
            vals.update((appmod.META.get("palette", {}) or {}).get(mode, {}))
        except Exception:
            pass
        out = ""
        for name in ("style.qss", f"style_{mode}.qss"):
            p = resource("assets", name)
            if p.exists():
                txt = p.read_text(encoding="utf-8")
                for k, v in vals.items():
                    txt = txt.replace("{" + k + "}", v)
                out += "\n" + txt
        return out
    except Exception:
        return ""


def colors(mode: str) -> dict:
    """Grafiklar va maxsus chizish uchun joriy ranglar."""
    return dict(PALETTES[resolve_mode(mode)])
