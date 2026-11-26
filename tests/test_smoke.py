"""Tutun testi: oyna xatosiz yaratiladimi."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


def test_window_creates():
    from PySide6.QtWidgets import QApplication
    from uzkit import app as appmod, i18n
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings(appmod.META["slug"] + "_test")
    qapp = QApplication.instance() or QApplication([])
    from xarajatlar_hisobchisi.window import MainWindow
    for lang in ("uz", "ru", "en"):
        i18n.set_language(lang)
        w = MainWindow()
        w.close()


def test_translations_complete():
    from uzkit import i18n
    import xarajatlar_hisobchisi.window  # noqa: registers strings
    assert i18n.missing_keys() == {}
