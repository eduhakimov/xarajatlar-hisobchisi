"""Qo'shimcha umumiy yordamchilar: demo rejimi, tray, avtoyuklash, QPainter grafiklar, eksport.

(c) 2026 Bahtiyorjon Hakimov. Barcha huquqlar himoyalangan.
"""
import html
import math
import os
import sys
import tempfile
from pathlib import Path
from typing import Callable, List, Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QAction, QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QMenu, QSizePolicy, QSystemTrayIcon, QWidget

from uzkit.i18n import register, tr
from uzkit.paths import data_dir
from uzkit.theme import PALETTES

register({
    "tray_open": {"uz": "Ochish", "ru": "Открыть", "en": "Open"},
    "tray_quit": {"uz": "Dasturdan chiqish", "ru": "Выйти из программы", "en": "Quit"},
    "tray_hint": {
        "uz": "Dastur fonda ishlashda davom etadi va eslatmalarni ko'rsatadi. Chiqish uchun tray menyusidan foydalaning.",
        "ru": "Программа продолжает работать в фоне и показывать напоминания. Для выхода используйте меню в трее.",
        "en": "The app keeps running in the background and shows reminders. Use the tray menu to quit.",
    },
    "autostart": {"uz": "Windows bilan birga ishga tushirish", "ru": "Запускать вместе с Windows",
                  "en": "Start with Windows"},
    "minimize_to_tray": {"uz": "Yopilganda trayga yashirish (eslatmalar ishlashi uchun)",
                         "ru": "При закрытии сворачивать в трей (чтобы работали напоминания)",
                         "en": "Hide to tray on close (so reminders keep working)"},
    "autostart_failed": {"uz": "Avtoyuklash sozlamasini o'zgartirib bo'lmadi.",
                         "ru": "Не удалось изменить автозапуск.", "en": "Could not change the autostart setting."},
    "no_data": {"uz": "Ma'lumot yo'q", "ru": "Нет данных", "en": "No data"},
})


# --------------------------------------------------------------------------- demo / ma'lumotlar papkasi
_DEMO_DIRS = {}


def is_demo() -> bool:
    """Skrinshot (namuna) rejimi: haqiqiy ma'lumotlarga tegilmaydi."""
    return "--screenshot" in sys.argv


def app_data_dir(slug: str) -> Path:
    """Haqiqiy rejimda %APPDATA%/BahtiyorSoft/<slug>, skrinshot rejimida vaqtinchalik papka."""
    if is_demo() or "pytest" in sys.modules:
        from uzkit.i18n import language
        lang = language()                      # har bir til uchun alohida namunaviy baza
        if lang not in _DEMO_DIRS:
            _DEMO_DIRS[lang] = Path(tempfile.mkdtemp(prefix=f"{slug}_demo_{lang}_"))
        return _DEMO_DIRS[lang]
    return data_dir(slug)


# --------------------------------------------------------------------------- ranglar
def is_dark() -> bool:
    app = QApplication.instance()
    if app is None:
        return False
    return app.palette().window().color().lightness() < 128


def pal() -> dict:
    """Joriy mavzu ranglari (app.json dagi "palette" ham hisobga olinadi)."""
    mode = "dark" if is_dark() else "light"
    p = dict(PALETTES[mode])
    try:
        from uzkit import app as appmod
        p.update((appmod.META.get("palette", {}) or {}).get(mode, {}))
    except Exception:
        pass
    return p


_ICON_CACHE = {}


def icon(name: str, color: str = None, size: int = 20):
    """assets/icons/<name>.svg chiziqli belgisini berilgan rangda QIcon qilib qaytaradi."""
    from PySide6.QtGui import QIcon, QPixmap
    from PySide6.QtCore import QByteArray
    from PySide6.QtSvg import QSvgRenderer
    from uzkit.paths import resource
    color = color or pal()["text"]
    key = (name, color, size)
    if key in _ICON_CACHE:
        return _ICON_CACHE[key]
    f = resource("assets", "icons", f"{name}.svg")
    ic = QIcon()
    if f.exists():
        txt = f.read_text(encoding="utf-8").replace("currentColor", color)
        r = QSvgRenderer(QByteArray(txt.encode("utf-8")))
        for s in (size, size * 2):
            pm = QPixmap(s, s)
            pm.fill(Qt.transparent)
            p = QPainter(pm)
            p.setRenderHint(QPainter.Antialiasing)
            r.render(p)
            p.end()
            ic.addPixmap(pm)
    _ICON_CACHE[key] = ic
    return ic


def accent() -> str:
    try:
        from uzkit import app as appmod
        return appmod.META.get("accent", "#2563eb")
    except Exception:
        return "#2563eb"


def mix(c1: str, c2: str, t: float) -> QColor:
    a, b = QColor(c1), QColor(c2)
    return QColor(int(a.red() + (b.red() - a.red()) * t), int(a.green() + (b.green() - a.green()) * t),
                  int(a.blue() + (b.blue() - a.blue()) * t))


def soft(color: str, t: float = 0.82) -> QColor:
    """Rangning och (fon uchun) varianti, mavzuga mos."""
    return mix(color, pal()["surface"], t)


CHART_COLORS = ["#2563eb", "#059669", "#ea580c", "#7c3aed", "#db2777", "#0891b2", "#ca8a04", "#dc2626",
                "#4f46e5", "#16a34a", "#9333ea", "#0d9488", "#e11d48", "#65a30d"]


# --------------------------------------------------------------------------- avtoyuklash (HKCU Run)
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"


def autostart_command(extra_args: str = "--tray") -> str:
    """Avtoyuklash uchun buyruq qatori (exe yoki python skripti)."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" {extra_args}'.strip()
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    if pyw.exists():
        exe = pyw
    main = Path(sys.argv[0]).resolve()
    return f'"{exe}" "{main}" {extra_args}'.strip()


def is_autostart(name: str, winreg_mod=None) -> bool:
    try:
        wr = winreg_mod or __import__("winreg")
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_READ) as k:
            wr.QueryValueEx(k, name)
            return True
    except Exception:
        return False


def set_autostart(name: str, enabled: bool, command: str, winreg_mod=None) -> bool:
    """Faqat foydalanuvchi belgilaganda chaqiriladi. HKCU\\...\\Run qiymatini yozadi yoki o'chiradi."""
    try:
        wr = winreg_mod or __import__("winreg")
        with wr.OpenKey(wr.HKEY_CURRENT_USER, RUN_KEY, 0, wr.KEY_SET_VALUE) as k:
            if enabled:
                wr.SetValueEx(k, name, 0, wr.REG_SZ, command)
            else:
                try:
                    wr.DeleteValue(k, name)
                except FileNotFoundError:
                    pass
        return True
    except Exception:
        return False


# --------------------------------------------------------------------------- tray
class Tray:
    """Tray belgisi: Ochish / Chiqish menyusi va bildirishnomalar."""

    def __init__(self, win, icon):
        self.win = win
        self.icon = QSystemTrayIcon(icon, win)
        self.icon.setToolTip(win.windowTitle())
        m = QMenu(win)
        a = QAction(tr("tray_open"), win)
        a.triggered.connect(self.show_window)
        m.addAction(a)
        self.menu = m
        m.addSeparator()
        q = QAction(tr("tray_quit"), win)
        q.triggered.connect(self.quit)
        m.addAction(q)
        self.icon.setContextMenu(m)
        self.icon.activated.connect(self._activated)
        self.icon.messageClicked.connect(self.show_window)
        self.quitting = False

    def available(self) -> bool:
        return QSystemTrayIcon.isSystemTrayAvailable()

    def show(self):
        if self.available():
            self.icon.show()

    def _activated(self, reason):
        if reason in (QSystemTrayIcon.Trigger, QSystemTrayIcon.DoubleClick):
            self.show_window()

    def show_window(self):
        self.win.showNormal()
        self.win.raise_()
        self.win.activateWindow()

    def quit(self):
        self.quitting = True
        self.icon.hide()
        self.win.close()
        QApplication.quit()

    def notify(self, title: str, text: str, ms: int = 10000):
        if self.available() and self.icon.isVisible():
            self.icon.showMessage(title, text, QSystemTrayIcon.Information, ms)


# --------------------------------------------------------------------------- progress halqasi
class ProgressRing(QWidget):
    def __init__(self, size: int = 64, thickness: int = 7, parent=None):
        super().__init__(parent)
        self._v = 0.0
        self._color = None
        self._text = None
        self._thick = thickness
        self.setFixedSize(size, size)

    def set_value(self, v: float, color: str = None, text: str = None):
        self._v = max(0.0, min(1.0, v))
        self._color = color
        self._text = text
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = pal()
        t = self._thick
        r = QRectF(t / 2 + 1, t / 2 + 1, self.width() - t - 2, self.height() - t - 2)
        pen = QPen(QColor(c["surface2"]), t)
        pen.setCapStyle(Qt.RoundCap)
        p.setPen(pen)
        p.drawEllipse(r)
        if self._v > 0:
            pen.setColor(QColor(self._color or accent()))
            p.setPen(pen)
            p.drawArc(r, 90 * 16, -int(self._v * 360 * 16))
        p.setPen(QColor(c["text"]))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(max(7.0, self.height() / 5.2))
        p.setFont(f)
        p.drawText(self.rect(), Qt.AlignCenter, self._text if self._text is not None else f"{round(self._v * 100)}%")


# --------------------------------------------------------------------------- donut
class DonutChart(QWidget):
    """Halqasimon diagramma + o'ng tomonda afsona (legend)."""

    def __init__(self, parent=None, fmt: Callable[[float], str] = None):
        super().__init__(parent)
        self.data: List[Tuple[str, float, str]] = []
        self.center_text = ""
        self.center_sub = ""
        self.fmt = fmt or (lambda v: f"{v:,.0f}".replace(",", " "))
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, data: Sequence[Tuple[str, float, str]], center_text: str = "", center_sub: str = ""):
        self.data = [(l, float(v), c) for l, v, c in data if v > 0]
        self.center_text, self.center_sub = center_text, center_sub
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = pal()
        w, h = self.width(), self.height()
        d = min(h - 10, w * 0.45)
        if w - d - 30 < 230:                      # afsona uchun joy qoldirish
            d = min(h - 10, max(100.0, w - 260))
        rect = QRectF(8, (h - d) / 2, d, d)
        total = sum(v for _, v, _ in self.data)
        thick = max(14.0, d * 0.16)
        inner = rect.adjusted(thick / 2, thick / 2, -thick / 2, -thick / 2)
        if total <= 0:
            pen = QPen(QColor(c["surface2"]), thick)
            p.setPen(pen)
            p.drawEllipse(inner)
            p.setPen(QColor(c["muted"]))
            p.drawText(rect, Qt.AlignCenter, tr("no_data"))
            return
        start = 90.0
        for label, v, col in self.data:
            span = -360.0 * v / total
            pen = QPen(QColor(col), thick)
            pen.setCapStyle(Qt.FlatCap)
            p.setPen(pen)
            p.drawArc(inner, int(start * 16), int(span * 16) - (8 if len(self.data) > 1 else 0))
            start += span
        # markaz matni
        p.setPen(QColor(c["text"]))
        f = QFont(self.font())
        f.setBold(True)
        f.setPointSizeF(max(8.0, d / 13))
        p.setFont(f)
        tr_rect = QRectF(inner.left(), inner.center().y() - d * 0.14, inner.width(), d * 0.16)
        p.drawText(tr_rect, Qt.AlignCenter, self.center_text)
        f.setBold(False)
        f.setPointSizeF(max(7.5, d / 20))
        p.setFont(f)
        p.setPen(QColor(c["muted"]))
        p.drawText(QRectF(inner.left(), inner.center().y() + d * 0.02, inner.width(), d * 0.12), Qt.AlignCenter,
                   self.center_sub)
        # afsona
        lx = rect.right() + 18
        n = len(self.data)
        row_h = min(26.0, (h - 10) / max(n, 1))
        y = (h - row_h * n) / 2
        f.setPointSizeF(9)
        p.setFont(f)
        fm = p.fontMetrics()
        for label, v, col in self.data:
            p.setPen(Qt.NoPen)
            p.setBrush(QColor(col))
            p.drawRoundedRect(QRectF(lx, y + row_h / 2 - 5, 10, 10), 3, 3)
            pct = f"{v / total * 100:.0f}%"
            val = self.fmt(v)
            p.setPen(QColor(c["text"]))
            avail = w - lx - 20 - fm.horizontalAdvance(f"{val}  {pct}") - 8
            p.drawText(QRectF(lx + 16, y, max(avail, 20), row_h), Qt.AlignVCenter | Qt.AlignLeft,
                       fm.elidedText(label, Qt.ElideRight, int(max(avail, 20))))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(lx, y, w - lx - 4, row_h), Qt.AlignVCenter | Qt.AlignRight, f"{val}  {pct}")
            y += row_h


# --------------------------------------------------------------------------- ustunli diagramma
class BarChart(QWidget):
    """Guruhlangan ustunli diagramma. series: [(nomi, rang, [qiymatlar...])]."""

    def __init__(self, parent=None, fmt: Callable[[float], str] = None):
        super().__init__(parent)
        self.labels: List[str] = []
        self.series: List[Tuple[str, str, List[float]]] = []
        self.fmt = fmt or (lambda v: f"{v:,.0f}".replace(",", " "))
        self.highlight_last = False
        self.show_values = False
        self.setMinimumHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_data(self, labels, series, show_values: bool = False):
        self.labels = list(labels)
        self.series = [(n, c, [float(x) for x in vals]) for n, c, vals in series]
        self.show_values = show_values
        self.update()

    @staticmethod
    def _nice_max(v: float) -> float:
        """Yuqori chegara = 4 * "chiroyli" qadam (1, 2, 5 x 10^k), shunda belgilar butun va toza bo'ladi."""
        if v <= 0:
            return 4.0
        raw = v / 4
        exp = 10 ** math.floor(math.log10(raw))
        for m in (1, 2, 5, 10):
            if m * exp >= raw:
                return 4 * m * exp
        return 40 * exp

    def paintEvent(self, e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c = pal()
        w, h = self.width(), self.height()
        f = QFont(self.font())
        f.setPointSizeF(8.5)
        p.setFont(f)
        fm = p.fontMetrics()
        vmax = self._nice_max(max([max(s[2]) for s in self.series if s[2]] + [0]))
        left = max(fm.horizontalAdvance(self.fmt(vmax)), fm.horizontalAdvance("0")) + 10
        legend_h = 22 if len(self.series) > 1 else 0
        top, bottom, right = 10 + legend_h, 24, 8
        ph = h - top - bottom
        pw = w - left - right
        # to'r
        steps = 4
        for i in range(steps + 1):
            y = top + ph - ph * i / steps
            p.setPen(QPen(QColor(c["border"]), 1, Qt.DashLine if i else Qt.SolidLine))
            p.drawLine(QPointF(left, y), QPointF(w - right, y))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(0, y - 9, left - 6, 18), Qt.AlignRight | Qt.AlignVCenter, self.fmt(vmax * i / steps))
        n = len(self.labels)
        if n == 0:
            p.setPen(QColor(c["muted"]))
            p.drawText(self.rect(), Qt.AlignCenter, tr("no_data"))
            return
        k = max(len(self.series), 1)
        group = pw / n
        bw = min(34.0, group * 0.7 / k)
        for i, lab in enumerate(self.labels):
            gx = left + group * i + (group - bw * k - 3 * (k - 1)) / 2
            for j, (name, col, vals) in enumerate(self.series):
                v = vals[i] if i < len(vals) else 0
                bh = ph * v / vmax if vmax else 0
                r = QRectF(gx + j * (bw + 3), top + ph - bh, bw, bh)
                if bh > 0:
                    path = QPainterPath()
                    rad = min(5.0, bw / 2, bh)
                    path.addRoundedRect(r.adjusted(0, 0, 0, rad), rad, rad)
                    p.save()
                    p.setClipRect(QRectF(r.left(), r.top(), r.width(), r.height()))
                    p.fillPath(path, QColor(col))
                    p.restore()
                    if self.show_values and v:
                        p.setPen(QColor(c["muted"]))
                        p.drawText(QRectF(r.left() - 20, r.top() - 16, r.width() + 40, 14), Qt.AlignCenter,
                                   self.fmt(v))
            p.setPen(QColor(c["muted"]))
            p.drawText(QRectF(left + group * i, h - bottom + 4, group, bottom - 4), Qt.AlignHCenter | Qt.AlignTop,
                       fm.elidedText(lab, Qt.ElideRight, int(group)))
        if legend_h:
            x = left
            for name, col, _ in self.series:
                p.setPen(Qt.NoPen)
                p.setBrush(QColor(col))
                p.drawRoundedRect(QRectF(x, 5, 10, 10), 3, 3)
                p.setPen(QColor(c["text"]))
                p.drawText(QPointF(x + 15, 14), name)
                x += 30 + fm.horizontalAdvance(name)


# --------------------------------------------------------------------------- eksport
def esc(s) -> str:
    return html.escape(str(s if s is not None else ""))


def write_xlsx(path: str, sheet_title: str, headers: Sequence[str], rows: Sequence[Sequence],
               widths: Sequence[int] = None, title: str = None, accent_hex: str = None,
               fills: Sequence[Optional[str]] = None):
    """Chiroyli Excel jadval: sarlavha, rangli ustun nomlari, kengliklar, muzlatilgan qator."""
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter
    wb = Workbook()
    ws = wb.active
    ws.title = (sheet_title or "Sheet")[:31]
    acc = (accent_hex or accent()).lstrip("#").upper()
    r0 = 1
    if title:
        ws.cell(row=1, column=1, value=title).font = Font(bold=True, size=14)
        r0 = 3
    thin = Side(style="thin", color="D9DDE5")
    for j, h in enumerate(headers, 1):
        cell = ws.cell(row=r0, column=j, value=h)
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = PatternFill("solid", fgColor=acc)
        cell.alignment = Alignment(vertical="center", wrap_text=True)
        cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
    for i, row in enumerate(rows, 1):
        for j, v in enumerate(row, 1):
            cell = ws.cell(row=r0 + i, column=j, value=v)
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = Border(top=thin, bottom=thin, left=thin, right=thin)
            if fills and i - 1 < len(fills) and fills[i - 1]:
                cell.fill = PatternFill("solid", fgColor=fills[i - 1].lstrip("#").upper())
    for j in range(1, len(headers) + 1):
        wdt = widths[j - 1] if widths and j - 1 < len(widths) else 18
        ws.column_dimensions[get_column_letter(j)].width = wdt
    ws.freeze_panes = ws.cell(row=r0 + 1, column=1)
    wb.save(path)


def html_to_pdf(path: str, html_text: str, landscape: bool = False):
    """HTML matnni PDF faylga yozadi (QPrinter, offline)."""
    from PySide6.QtGui import QPageLayout, QPageSize, QTextDocument
    from PySide6.QtCore import QMarginsF
    from PySide6.QtPrintSupport import QPrinter
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(path)
    printer.setPageSize(QPageSize(QPageSize.A4))
    printer.setPageOrientation(QPageLayout.Landscape if landscape else QPageLayout.Portrait)
    printer.setPageMargins(QMarginsF(14, 14, 14, 14), QPageLayout.Millimeter)
    doc = QTextDocument()
    doc.setDefaultFont(QFont("Segoe UI", 10))
    doc.setHtml(html_text)
    doc.print_(printer)
