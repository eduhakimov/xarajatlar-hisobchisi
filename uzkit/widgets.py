"""Barcha dasturlarda qayta ishlatiladigan tayyor vidjetlar va fon ishchisi."""
import os
import subprocess
import sys
import traceback
from pathlib import Path
from typing import Callable, List, Optional

from PySide6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, Signal, Slot
from PySide6.QtWidgets import (QFileDialog, QFrame, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
                               QPushButton, QSizePolicy, QVBoxLayout, QWidget)

from .i18n import tr


# --------------------------------------------------------------------------- Card
class Card(QFrame):
    """Yumaloq burchakli panel. title berilsa sarlavha bilan."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self.setObjectName("Card")
        self.lay = QVBoxLayout(self)
        self.lay.setContentsMargins(16, 14, 16, 16)
        self.lay.setSpacing(10)
        self.title_label = None
        if title:
            self.title_label = QLabel(title)
            self.title_label.setObjectName("SectionTitle")
            self.lay.addWidget(self.title_label)

    def add(self, w) -> QWidget:
        if isinstance(w, QWidget):
            self.lay.addWidget(w)
        else:
            self.lay.addLayout(w)
        return w


def primary_button(text: str, parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setObjectName("Primary")
    b.setCursor(Qt.PointingHandCursor)
    return b


def danger_button(text: str, parent=None) -> QPushButton:
    b = QPushButton(text, parent)
    b.setObjectName("Danger")
    b.setCursor(Qt.PointingHandCursor)
    return b


def header(title: str, subtitle: str = "") -> QWidget:
    """Sahifa yuqorisidagi katta sarlavha + izoh."""
    w = QWidget()
    l = QVBoxLayout(w)
    l.setContentsMargins(0, 0, 0, 4)
    l.setSpacing(2)
    t = QLabel(title)
    t.setObjectName("Title")
    l.addWidget(t)
    if subtitle:
        s = QLabel(subtitle)
        s.setObjectName("Subtitle")
        s.setWordWrap(True)
        l.addWidget(s)
    return w


# --------------------------------------------------------------------------- PathPicker
class PathPicker(QWidget):
    """Matn maydoni + "Tanlash..." tugmasi. mode: 'open' | 'save' | 'dir' | 'open_many'."""
    changed = Signal(str)

    def __init__(self, mode: str = "open", file_filter: str = "", placeholder: str = "", parent=None):
        super().__init__(parent)
        self.mode, self.file_filter = mode, file_filter
        l = QHBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        self.edit = QLineEdit()
        self.edit.setPlaceholderText(placeholder)
        self.edit.textChanged.connect(self.changed.emit)
        self.btn = QPushButton(tr("browse"))
        self.btn.clicked.connect(self._pick)
        l.addWidget(self.edit, 1)
        l.addWidget(self.btn)

    def _pick(self):
        start = self.edit.text() or str(Path.home())
        if self.mode == "dir":
            p = QFileDialog.getExistingDirectory(self, tr("select_folder"), start)
        elif self.mode == "save":
            p, _ = QFileDialog.getSaveFileName(self, tr("save"), start, self.file_filter)
        else:
            p, _ = QFileDialog.getOpenFileName(self, tr("select_file"), start, self.file_filter)
        if p:
            self.edit.setText(os.path.normpath(p))

    def path(self) -> str:
        return self.edit.text().strip()

    def set_path(self, p: str):
        self.edit.setText(p)


# --------------------------------------------------------------------------- DropArea
class DropArea(QFrame):
    """Fayllarni sudrab tashlash maydoni. Bosilganda fayl tanlash oynasi ochiladi."""
    files_dropped = Signal(list)

    def __init__(self, text: str = "", file_filter: str = "", extensions: Optional[List[str]] = None,
                 allow_dirs: bool = False, multiple: bool = True, parent=None):
        super().__init__(parent)
        self.setObjectName("DropArea")
        self.setAcceptDrops(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(110)
        self.file_filter, self.multiple, self.allow_dirs = file_filter, multiple, allow_dirs
        self.extensions = [e.lower().lstrip(".") for e in (extensions or [])]
        l = QVBoxLayout(self)
        self.label = QLabel(text or tr("drop_here"))
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setObjectName("Muted")
        self.label.setWordWrap(True)
        l.addWidget(self.label)

    def _accept(self, path: str) -> bool:
        if os.path.isdir(path):
            return self.allow_dirs
        if not self.extensions:
            return True
        return Path(path).suffix.lower().lstrip(".") in self.extensions

    def _set_active(self, v: bool):
        self.setProperty("active", "true" if v else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    def dragEnterEvent(self, e):
        if e.mimeData().hasUrls():
            e.acceptProposedAction()
            self._set_active(True)

    def dragLeaveEvent(self, e):
        self._set_active(False)

    def dropEvent(self, e):
        self._set_active(False)
        paths = [u.toLocalFile() for u in e.mimeData().urls() if u.isLocalFile()]
        paths = [p for p in paths if self._accept(p)]
        if not self.multiple:
            paths = paths[:1]
        if paths:
            self.files_dropped.emit(paths)

    def mouseReleaseEvent(self, e):
        if e.button() != Qt.LeftButton:
            return
        if self.multiple:
            paths, _ = QFileDialog.getOpenFileNames(self, tr("select_file"), str(Path.home()), self.file_filter)
        else:
            p, _ = QFileDialog.getOpenFileName(self, tr("select_file"), str(Path.home()), self.file_filter)
            paths = [p] if p else []
        if paths:
            self.files_dropped.emit(paths)


# --------------------------------------------------------------------------- Worker
class _WorkerSignals(QObject):
    progress = Signal(int, str)      # foiz, xabar
    result = Signal(object)
    error = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    """Og'ir ishni fon oqimida bajaradi, interfeys qotmaydi.

        w = Worker(fn, arg1, arg2)      # fn(progress_cb, *args) yoki fn(*args)
        w.signals.result.connect(...)
        w.signals.progress.connect(lambda pct, msg: ...)
        run_worker(w)

    Agar fn birinchi parametri `progress` deb nomlangan bo'lsa, unga callback uzatiladi:
        progress(pct:int, msg:str)  va  progress.cancelled -> bool
    """

    def __init__(self, fn: Callable, *args, **kwargs):
        super().__init__()
        self.fn, self.args, self.kwargs = fn, args, kwargs
        self.signals = _WorkerSignals()
        self._cancel = False
        self.setAutoDelete(True)

    def cancel(self):
        self._cancel = True

    @property
    def cancelled(self) -> bool:
        return self._cancel

    @Slot()
    def run(self):
        try:
            import inspect
            params = list(inspect.signature(self.fn).parameters)
            if params and params[0] == "progress":
                def cb(pct=0, msg=""):
                    self.signals.progress.emit(int(pct), str(msg))
                cb.cancelled = lambda: self._cancel
                res = self.fn(cb, *self.args, **self.kwargs)
            else:
                res = self.fn(*self.args, **self.kwargs)
            self.signals.result.emit(res)
        except Exception as ex:  # noqa
            from .app import log_exception
            log_exception(ex)
            self.signals.error.emit(f"{ex}")
        finally:
            self.signals.finished.emit()


def run_worker(w: Worker) -> Worker:
    QThreadPool.globalInstance().start(w)
    return w


# --------------------------------------------------------------------------- yordamchi funksiyalar
def info(parent, text: str, title: str = ""):
    QMessageBox.information(parent, title or tr("done"), text)


def warn(parent, text: str, title: str = ""):
    QMessageBox.warning(parent, title or tr("warning"), text)


def error(parent, text: str, title: str = ""):
    QMessageBox.critical(parent, title or tr("error"), text)


def ask(parent, text: str, title: str = "") -> bool:
    box = QMessageBox(QMessageBox.Question, title or tr("confirm"), text, parent=parent)
    yes = box.addButton(tr("yes"), QMessageBox.YesRole)
    box.addButton(tr("no"), QMessageBox.NoRole)
    box.exec()
    return box.clickedButton() is yes


def open_path(path: str):
    """Fayl yoki papkani Windows Explorer'da ochadi."""
    try:
        os.startfile(path)  # type: ignore[attr-defined]
    except Exception:
        subprocess.Popen(["explorer", path])


def reveal_in_explorer(path: str):
    """Explorer'da faylni belgilab ko'rsatadi."""
    subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])


def human_size(n: float) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if abs(n) < 1024 or unit == "TB":
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def is_admin() -> bool:
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def relaunch_as_admin() -> bool:
    """Dasturni administrator sifatida qayta ishga tushiradi (UAC oynasi chiqadi)."""
    try:
        import ctypes
        if getattr(sys, "frozen", False):
            exe, params = sys.executable, " ".join(f'"{a}"' for a in sys.argv[1:])
        else:
            exe, params = sys.executable, " ".join(f'"{a}"' for a in sys.argv)
        r = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, params, None, 1)
        return r > 32
    except Exception:
        return False


def no_window_flags() -> int:
    """subprocess uchun: qora konsol oynasi chiqmasin."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)


def run_hidden(cmd, **kw) -> subprocess.CompletedProcess:
    """Buyruqni konsol oynasisiz ishga tushiradi va natijani qaytaradi."""
    kw.setdefault("capture_output", True)
    kw.setdefault("text", True)
    kw.setdefault("encoding", "utf-8")
    kw.setdefault("errors", "replace")
    return subprocess.run(cmd, creationflags=no_window_flags(), **kw)
