"""Dasturni ishga tushirish: QApplication, mavzu, til, jurnal, xatolarni ushlash.

Har bir dasturning main.py fayli:

    from uzkit.app import run
    from myapp.window import MainWindow
    if __name__ == "__main__":
        run(MainWindow)

Buyruq qatori parametrlari (test va skrinshot uchun):
    --screenshot FILE.png   oynani ochib, rasmga olib, yopadi
    --lang uz|ru|en         tilni majburan tanlash (sozlamaga yozilmaydi)
    --theme light|dark      mavzuni majburan tanlash
    --page N                (ixtiyoriy) oyna set_page(N) metodini qo'llasa
    --selftest              oynani yaratib, darhol 0 kod bilan chiqadi
"""
import json
import logging
import logging.handlers
import sys
import traceback
from pathlib import Path

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from . import i18n
from .paths import data_dir, resource
from .settings import Settings
from .theme import apply_theme

_log = logging.getLogger("app")
META: dict = {}
SETTINGS: Settings = None  # type: ignore
_LOG_FILE = None


def load_meta() -> dict:
    """app.json: dastur nomi, versiyasi, rangi va h.k."""
    p = resource("app.json")
    return json.loads(p.read_text(encoding="utf-8-sig"))


def app_name() -> str:
    n = META.get("name", {})
    return n.get(i18n.language()) or n.get("uz") or META.get("slug", "App")


def app_description() -> str:
    d = META.get("description", {})
    return d.get(i18n.language()) or d.get("uz") or ""


def log_exception(ex: BaseException):
    _log.error("".join(traceback.format_exception(type(ex), ex, ex.__traceback__)))


def _setup_logging(slug: str):
    global _LOG_FILE
    _LOG_FILE = data_dir(slug) / "log.txt"
    h = logging.handlers.RotatingFileHandler(_LOG_FILE, maxBytes=1_000_000, backupCount=2, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(h)


def _excepthook(etype, value, tb):
    _log.error("".join(traceback.format_exception(etype, value, tb)))
    try:
        QMessageBox.critical(None, i18n.tr("error"),
                             f"{i18n.tr('unexpected_error')}\n{_LOG_FILE}\n\n{value}")
    except Exception:
        pass


def _arg(name: str, default=None):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def run(window_cls, meta: dict = None) -> int:
    global META, SETTINGS
    META = meta or load_meta()
    slug = META["slug"]
    if "--screenshot" in sys.argv or "--selftest" in sys.argv:
        # Skrinshot/tekshiruv rejimi: foydalanuvchining haqiqiy sozlama va ma'lumotlariga tegmaslik
        import os
        import tempfile
        os.environ["APPDATA"] = tempfile.mkdtemp(prefix=f"{slug}_shot_")
    _setup_logging(slug)
    sys.excepthook = _excepthook

    # Windows vazifalar panelida o'z belgisi chiqishi uchun
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(f"BahtiyorSoft.{slug}")
    except Exception:
        pass

    QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName("BahtiyorSoft")
    app.setApplicationName(slug)
    app.setApplicationVersion(META.get("version", "1.0.0"))
    app.setFont(QFont(META.get("font") or "Segoe UI", 10))

    SETTINGS = Settings(slug)
    i18n.set_language(_arg("--lang") or SETTINGS.get("language", i18n.DEFAULT_LANG))
    app.setApplicationDisplayName(app_name())
    theme_mode = _arg("--theme") or SETTINGS.get("theme", "system")
    apply_theme(app, theme_mode, META.get("accent", "#2563eb"))

    icon_path = resource("assets", "icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    win = window_cls()
    if "--selftest" in sys.argv:
        win.close()
        return 0

    page = _arg("--page")
    if page is not None and hasattr(win, "set_page"):
        try:
            win.set_page(int(page))
        except Exception:
            pass

    shot = _arg("--screenshot")
    if shot:
        win.resize(*META.get("screenshot_size", [1180, 760]))
        win.show()

        def grab():
            win.grab().save(shot)
            app.quit()
        QTimer.singleShot(int(_arg("--delay", "1500")), grab)
        return app.exec()

    win.show()
    return app.exec()
