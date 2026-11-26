"""BaseMainWindow — barcha dasturlarning asosiy oynasi.

Tayyor narsalar: menyu (Fayl / Sozlamalar / Yordam), til va mavzu tanlash, qo'llanma,
"Dastur haqida", holat qatori, oyna o'lchamini eslab qolish, ixtiyoriy chap navigatsiya.

Foydalanish:
    class MainWindow(BaseMainWindow):
        def __init__(self):
            super().__init__()
            self.add_page("Asosiy", "home", HomePage())     # chap menyu bilan
            # yoki: self.set_central(widget)                 # bitta sahifa
"""
import sys

from PySide6.QtCore import QByteArray, QProcess, Qt, QUrl
from PySide6.QtGui import QAction, QActionGroup, QDesktopServices, QIcon
from PySide6.QtWidgets import (QApplication, QDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
                               QMainWindow, QPushButton, QStackedWidget, QTextBrowser, QVBoxLayout, QWidget)

from . import AUTHOR, AUTHOR_GITHUB, COPYRIGHT_YEAR, app as appmod, i18n
from .i18n import tr
from .paths import resource
from .theme import apply_theme


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        meta = appmod.META
        self.setWindowTitle(tr("about"))
        self.setMinimumWidth(460)
        l = QVBoxLayout(self)
        l.setSpacing(8)
        top = QHBoxLayout()
        icon = QLabel()
        ip = resource("assets", "icon.png")
        if ip.exists():
            from PySide6.QtGui import QPixmap
            icon.setPixmap(QPixmap(str(ip)).scaled(72, 72, Qt.KeepAspectRatio, Qt.SmoothTransformation))
        top.addWidget(icon)
        col = QVBoxLayout()
        t = QLabel(appmod.app_name())
        t.setObjectName("Title")
        col.addWidget(t)
        col.addWidget(QLabel(f"{tr('version')} {meta.get('version', '1.0.0')}"))
        top.addLayout(col, 1)
        l.addLayout(top)
        d = QLabel(appmod.app_description())
        d.setWordWrap(True)
        l.addWidget(d)
        c = QLabel(f"© {COPYRIGHT_YEAR} {AUTHOR}. {tr('rights')}<br>"
                   f"<a href='{AUTHOR_GITHUB}'>{AUTHOR_GITHUB}</a>")
        c.setOpenExternalLinks(True)
        c.setObjectName("Muted")
        c.setWordWrap(True)
        l.addWidget(c)
        b = QPushButton(tr("close"))
        b.clicked.connect(self.accept)
        l.addWidget(b, 0, Qt.AlignRight)


class ManualDialog(QDialog):
    """Qo'llanma: app.json dagi "manual" yoki assets/manual_<til>.md fayli."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"{tr('manual')} — {appmod.app_name()}")
        self.resize(720, 600)
        l = QVBoxLayout(self)
        view = QTextBrowser()
        view.setOpenExternalLinks(True)
        lang = i18n.language()
        text = ""
        for cand in (f"manual_{lang}.md", "manual_uz.md"):
            p = resource("assets", cand)
            if p.exists():
                text = p.read_text(encoding="utf-8")
                break
        if not text:
            m = appmod.META.get("manual", {})
            text = m.get(lang) or m.get("uz") or appmod.app_description()
        view.setMarkdown(text)
        l.addWidget(view)
        b = QPushButton(tr("close"))
        b.clicked.connect(self.accept)
        l.addWidget(b, 0, Qt.AlignRight)


class BaseMainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.settings = appmod.SETTINGS
        self.setWindowTitle(f"{appmod.app_name()}  {appmod.META.get('version', '')}")
        self.setMinimumSize(900, 600)
        self._nav = None
        self._stack = None
        self._build_menu()
        self.statusBar().showMessage(tr("ready"))
        geo = self.settings.get("geometry") if self.settings else None
        if geo:
            try:
                self.restoreGeometry(QByteArray.fromBase64(geo.encode()))
            except Exception:
                self.resize(1180, 760)
        else:
            self.resize(1180, 760)

    # ------------------------------------------------------------------ menyu
    def _build_menu(self):
        mb = self.menuBar()
        self.menu_file = mb.addMenu(tr("file"))
        act_exit = QAction(tr("exit"), self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        self.menu_file.addAction(act_exit)

        self.menu_settings = mb.addMenu(tr("settings"))
        lang_menu = self.menu_settings.addMenu(tr("language"))
        g = QActionGroup(self)
        for code, name in i18n.LANGUAGES.items():
            a = QAction(name, self, checkable=True)
            a.setChecked(code == i18n.language())
            a.triggered.connect(lambda _=False, c=code: self._change_language(c))
            g.addAction(a)
            lang_menu.addAction(a)
        theme_menu = self.menu_settings.addMenu(tr("theme"))
        tg = QActionGroup(self)
        cur = self.settings.get("theme", "system") if self.settings else "system"
        for code, key in (("system", "theme_system"), ("light", "theme_light"), ("dark", "theme_dark")):
            a = QAction(tr(key), self, checkable=True)
            a.setChecked(code == cur)
            a.triggered.connect(lambda _=False, c=code: self._change_theme(c))
            tg.addAction(a)
            theme_menu.addAction(a)

        self.menu_help = mb.addMenu(tr("help"))
        a = QAction(tr("manual"), self)
        a.setShortcut("F1")
        a.triggered.connect(lambda: ManualDialog(self).exec())
        self.menu_help.addAction(a)
        a = QAction(tr("about"), self)
        a.triggered.connect(lambda: AboutDialog(self).exec())
        self.menu_help.addAction(a)

    def _change_language(self, code: str):
        if code == i18n.language():
            return
        from .widgets import ask
        if ask(self, tr("restart_lang"), tr("restart_title")):
            self.settings.set("language", code)
            args = [a for a in sys.argv[1:]]
            if getattr(sys, "frozen", False):
                QProcess.startDetached(sys.executable, args)
            else:
                QProcess.startDetached(sys.executable, sys.argv)
            QApplication.quit()

    def _change_theme(self, mode: str):
        self.settings.set("theme", mode)
        apply_theme(QApplication.instance(), mode, appmod.META.get("accent", "#2563eb"))
        self.on_theme_changed()

    def on_theme_changed(self):
        """Grafik chizuvchi dasturlar qayta yozishi mumkin."""

    # ------------------------------------------------------------------ sahifalar
    def set_central(self, w: QWidget, margins: int = 18):
        holder = QWidget()
        l = QVBoxLayout(holder)
        l.setContentsMargins(margins, margins, margins, margins)
        l.addWidget(w)
        self.setCentralWidget(holder)

    def add_page(self, title: str, widget: QWidget, icon: QIcon = None):
        """Chap navigatsiya paneliga sahifa qo'shadi."""
        if self._nav is None:
            root = QWidget()
            h = QHBoxLayout(root)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            self._nav = QListWidget()
            self._nav.setObjectName("NavList")
            self._nav.setFixedWidth(220)
            self._stack = QStackedWidget()
            h.addWidget(self._nav)
            h.addWidget(self._stack, 1)
            self._nav.currentRowChanged.connect(self._stack.setCurrentIndex)
            self.setCentralWidget(root)
        page = QWidget()
        l = QVBoxLayout(page)
        l.setContentsMargins(22, 18, 22, 18)
        l.addWidget(widget)
        self._stack.addWidget(page)
        it = QListWidgetItem(title)
        if icon:
            it.setIcon(icon)
        self._nav.addItem(it)
        if self._nav.count() == 1:
            self._nav.setCurrentRow(0)
        return widget

    def set_page(self, i: int):
        if self._nav is not None and 0 <= i < self._nav.count():
            self._nav.setCurrentRow(i)

    def status(self, text: str, ms: int = 5000):
        self.statusBar().showMessage(text, ms)

    # ------------------------------------------------------------------ yopish
    def closeEvent(self, e):
        try:
            if self.settings and "--screenshot" not in sys.argv:
                self.settings.set("geometry", bytes(self.saveGeometry().toBase64()).decode())
        except Exception:
            pass
        super().closeEvent(e)
