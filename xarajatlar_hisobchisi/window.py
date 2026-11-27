"""Asosiy oyna: chapda balans va hisoblar paneli, o'ngda ish sahifalari."""
import random
import sys
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path

from PySide6.QtCore import QDate, QSize, Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox,
                               QDateEdit, QDialog, QDialogButtonBox, QFileDialog, QFormLayout, QFrame, QGridLayout,
                               QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMenu,
                               QProgressBar, QPushButton, QScrollArea, QSizePolicy, QStackedWidget, QTableWidget,
                               QTableWidgetItem, QToolButton, QVBoxLayout, QWidget)

from uzkit import app as appmod
from uzkit.i18n import register, tr
from uzkit.paths import resource
from uzkit.widgets import Card, ask, error, info, open_path, primary_button, warn
from uzkit.window import BaseMainWindow

from . import money
from .db import DB, restore_from, validate_db_file
from .strings import STRINGS
from .ui_extra import BarChart, DonutChart, accent, app_data_dir, icon, is_demo, mix, pal, write_xlsx

register(STRINGS)
SLUG = "xarajatlar-hisobchisi"
INCOME_C, EXPENSE_C = "#12805c", "#e03131"
ACCOUNT_KINDS = ["cash", "humo", "uzcard", "visa", "usd_cash", "deposit", "other"]
CAT_ICONS = ["cat_food", "cat_transport", "cat_utility", "cat_home", "cat_phone", "cat_health", "cat_edu",
             "cat_clothes", "cat_fun", "cat_cafe", "cat_gift", "cat_shop", "cat_sport", "cat_travel", "cat_kids",
             "cat_tax", "cat_salary", "cat_scholar", "cat_grant", "cat_side", "cat_other"]
COLORS = ["#e8590c", "#1c7ed6", "#f59f00", "#7048e8", "#0c8599", "#e03131", "#2f9e44", "#d6336c", "#9c36b5",
          "#a0522d", "#12805c", "#5c940d", "#868e96"]


def qd(d: date) -> QDate:
    return QDate(d.year, d.month, d.day)


def pd(q: QDate) -> date:
    return date(q.year(), q.month(), q.day())


def icon_button(name, tip, text=""):
    b = QPushButton(text)
    b.setIcon(icon(name, pal()["text"]))
    b.setIconSize(QSize(18, 18))
    b.setToolTip(tip)
    b.setAccessibleName(tip)
    if not text:
        b.setFixedWidth(40)
    return b


class AmountEdit(QLineEdit):
    """Summa maydoni: yozish davomida minglik bo'shliqlar qo'yiladi."""

    def __init__(self, big=False):
        super().__init__()
        self.setPlaceholderText("0")
        self.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        if big:
            self.setObjectName("BigAmount")
        self.textEdited.connect(self._fmt)

    def _fmt(self, text):
        raw = text.replace(" ", "")
        if not raw:
            return
        sep = "." if "." in raw else ("," if "," in raw else None)
        whole, frac = (raw.split(sep, 1) + [""])[:2] if sep else (raw, None)
        digits = "".join(ch for ch in whole if ch.isdigit())
        if not digits:
            return
        new = money.group(int(digits)) + (sep + "".join(ch for ch in frac if ch.isdigit())[:2] if sep else "")
        if new != text:
            pos = len(text) - self.cursorPosition()
            self.setText(new)
            self.setCursorPosition(max(0, len(new) - pos))

    def cents(self) -> int:
        return money.parse_amount(self.text())

    def set_cents(self, c: int, currency="UZS"):
        self.setText(money.fmt(c, currency, symbol=False))


# =========================================================================== tezkor kiritish dialogi
class TxDialog(QDialog):
    def __init__(self, win, tx=None, kind="expense"):
        super().__init__(win)
        self.win = win
        self.db: DB = win.db
        self.tx = tx
        self.saved_any = False
        self.setWindowTitle(tr("edit_tx") if tx else tr("new_tx"))
        self.setMinimumWidth(520)
        l = QVBoxLayout(self)
        l.setSpacing(10)
        seg = QHBoxLayout()
        self.kind_grp = QButtonGroup(self)
        for i, k in enumerate(("expense", "income", "transfer")):
            b = QPushButton(tr("k_" + k))
            b.setCheckable(True)
            b.setObjectName("Seg")
            b.setProperty("kind", k)
            self.kind_grp.addButton(b, i)
            seg.addWidget(b)
        l.addLayout(seg)
        self.amount = AmountEdit(big=True)
        arow = QHBoxLayout()
        arow.addWidget(self.amount, 1)
        self.cur_lbl = QLabel()
        self.cur_lbl.setObjectName("CurLabel")
        arow.addWidget(self.cur_lbl)
        l.addLayout(arow)
        form = QFormLayout()
        form.setSpacing(8)
        self.account = QComboBox()
        self.to_account = QComboBox()
        for a in self.db.accounts():
            for cb in (self.account, self.to_account):
                cb.addItem(icon("wallet", a["color"], 16), f"{a['name']} ({a['currency']})", a["id"])
        self.to_amount = AmountEdit()
        self.to_amount.setPlaceholderText(tr("to_amount_ph"))
        self.date = QDateEdit(QDate.currentDate())
        self.date.setCalendarPopup(True)
        self.date.setDisplayFormat("dd.MM.yyyy")
        self.note = QLineEdit()
        self.note.setPlaceholderText(tr("note_ph"))
        form.addRow(tr("account"), self.account)
        self.to_row_lbl = QLabel(tr("to_account"))
        form.addRow(self.to_row_lbl, self.to_account)
        self.to_amt_lbl = QLabel(tr("to_amount"))
        form.addRow(self.to_amt_lbl, self.to_amount)
        form.addRow(tr("date"), self.date)
        form.addRow(tr("note"), self.note)
        l.addLayout(form)
        self.cat_lbl = QLabel(tr("category"))
        self.cat_lbl.setObjectName("Muted")
        l.addWidget(self.cat_lbl)
        self.cat_host = QWidget()
        self.cat_grid = QGridLayout(self.cat_host)
        self.cat_grid.setContentsMargins(0, 0, 0, 0)
        self.cat_grid.setSpacing(6)
        l.addWidget(self.cat_host)
        self.cat_grp = QButtonGroup(self)
        self.cat_grp.setExclusive(True)
        bb = QHBoxLayout()
        bb.addStretch(1)
        self.b_cancel = QPushButton(tr("cancel"))
        self.b_more = QPushButton(tr("save_more"))
        self.b_more.setToolTip("Ctrl+Enter")
        self.b_save = primary_button(tr("save"))
        self.b_save.setDefault(True)
        for b in (self.b_cancel, self.b_more, self.b_save):
            bb.addWidget(b)
        if tx:
            self.b_more.hide()
        l.addLayout(bb)
        self.b_cancel.clicked.connect(self.reject)
        self.b_save.clicked.connect(lambda: self._save(False))
        self.b_more.clicked.connect(lambda: self._save(True))
        QShortcut(QKeySequence("Ctrl+Return"), self, activated=lambda: self._save(True))
        self.kind_grp.idClicked.connect(lambda *_: self._kind_changed())
        self.account.currentIndexChanged.connect(lambda *_: self._cur())
        self.to_account.currentIndexChanged.connect(lambda *_: self._cur())

        last_acc = win.settings.get("last_account")
        if tx:
            kind = tx["kind"]
            self.account.setCurrentIndex(max(0, self.account.findData(tx["account_id"])))
            cur = self.db.account(tx["account_id"])["currency"]
            self.amount.set_cents(tx["amount"], cur)
            self.date.setDate(qd(date.fromisoformat(tx["date"])))
            self.note.setText(tx["note"] or "")
            if tx["kind"] == "transfer":
                self.to_account.setCurrentIndex(max(0, self.to_account.findData(tx["to_account_id"])))
                if tx["to_amount"] and tx["to_amount"] != tx["amount"]:
                    self.to_amount.set_cents(tx["to_amount"], self.db.account(tx["to_account_id"])["currency"])
        elif last_acc:
            self.account.setCurrentIndex(max(0, self.account.findData(last_acc)))
        if self.to_account.count() > 1 and self.to_account.currentData() == self.account.currentData():
            self.to_account.setCurrentIndex(1 if self.account.currentIndex() == 0 else 0)
        self.kind_grp.button(("expense", "income", "transfer").index(kind)).setChecked(True)
        self._kind_changed(select_cat=tx["category_id"] if tx else None)
        self.amount.setFocus()

    def kind(self):
        return ("expense", "income", "transfer")[max(0, self.kind_grp.checkedId())]

    def _cur(self):
        a = self.db.account(self.account.currentData()) if self.account.currentData() else None
        self.cur_lbl.setText(a["currency"] if a else "")
        b = self.db.account(self.to_account.currentData()) if self.to_account.currentData() else None
        diff = self.kind() == "transfer" and a and b and a["currency"] != b["currency"]
        self.to_amount.setVisible(bool(diff))
        self.to_amt_lbl.setVisible(bool(diff))

    def _kind_changed(self, select_cat=None):
        k = self.kind()
        tr_ = k == "transfer"
        self.to_account.setVisible(tr_)
        self.to_row_lbl.setVisible(tr_)
        self.cat_host.setVisible(not tr_)
        self.cat_lbl.setVisible(not tr_)
        self.amount.setProperty("kind", k)
        self.amount.style().unpolish(self.amount)
        self.amount.style().polish(self.amount)
        for b in self.cat_grp.buttons():
            self.cat_grp.removeButton(b)
            b.deleteLater()
        if not tr_:
            cats = self.db.categories(k)
            for i, c in enumerate(cats):
                b = QToolButton()
                b.setText(c["name"])
                b.setIcon(icon(c["icon"], c["color"], 22))
                b.setIconSize(QSize(22, 22))
                b.setToolButtonStyle(Qt.ToolButtonTextUnderIcon)
                b.setCheckable(True)
                b.setObjectName("CatChip")
                b.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
                b.setMinimumHeight(62)
                b.setProperty("cid", c["id"])
                self.cat_grp.addButton(b)
                self.cat_grid.addWidget(b, i // 4, i % 4)
                if c["id"] == select_cat:
                    b.setChecked(True)
            if self.cat_grp.checkedButton() is None and self.cat_grp.buttons():
                self.cat_grp.buttons()[0].setChecked(True)
        self._cur()

    def _save(self, more: bool):
        try:
            cents = self.amount.cents()
            if cents <= 0:
                raise ValueError
        except ValueError:
            warn(self, tr("bad_amount"))
            self.amount.setFocus()
            return
        k = self.kind()
        acc = self.account.currentData()
        if acc is None:
            warn(self, tr("need_account"))
            return
        cat = self.cat_grp.checkedButton().property("cid") if (k != "transfer" and self.cat_grp.checkedButton()) else None
        to_acc = self.to_account.currentData() if k == "transfer" else None
        to_amt = None
        if k == "transfer":
            if to_acc == acc:
                warn(self, tr("same_account"))
                return
            a_cur, b_cur = self.db.account(acc)["currency"], self.db.account(to_acc)["currency"]
            if a_cur != b_cur:          # valyutalar har xil: qabul qilingan summa kerak
                try:
                    to_amt = self.to_amount.cents() if self.to_amount.text().strip() else None
                except ValueError:
                    warn(self, tr("bad_amount"))
                    return
                if not to_amt:
                    a, b = self.db.account(acc), self.db.account(to_acc)
                    try:
                        to_amt = money.convert(cents, a["currency"], b["currency"], self.db.current_rates())
                    except ValueError:
                        warn(self, tr("need_rate"))
                        return
        d = pd(self.date.date())
        note = self.note.text().strip()
        if self.tx:
            self.db.update_tx(self.tx["id"], d, k, acc, cents, cat, note, to_acc, to_amt)
        else:
            self.db.add_tx(d, k, acc, cents, cat, note, to_acc, to_amt)
        if not is_demo():
            self.win.settings.set("last_account", acc)
        self.saved_any = True
        if more:
            self.amount.clear()
            self.note.clear()
            self.amount.setFocus()
            self.win.data_changed()
            self.win.status(tr("tx_saved"))
        else:
            self.accept()


# =========================================================================== umumiy ko'rinish
class Tile(QFrame):
    def __init__(self, title, color):
        super().__init__()
        self.setObjectName("Tile")
        l = QVBoxLayout(self)
        l.setContentsMargins(16, 12, 16, 12)
        l.setSpacing(2)
        t = QLabel(title)
        t.setObjectName("TileTitle")
        self.v = QLabel("0")
        self.v.setObjectName("TileValue")
        self.v.setStyleSheet(f"color: {color};")
        self.sub = QLabel("")
        self.sub.setObjectName("Muted")
        l.addWidget(t)
        l.addWidget(self.v)
        l.addWidget(self.sub)


class Dashboard(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        sc.setFrameShape(QFrame.NoFrame)
        sc.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        host = QWidget()
        sc.setWidget(host)
        outer.addWidget(sc)
        lay = QVBoxLayout(host)
        lay.setContentsMargins(0, 0, 6, 0)
        lay.setSpacing(12)
        top = QHBoxLayout()
        self.title = QLabel()
        self.title.setObjectName("Title")
        top.addWidget(self.title, 1)
        add = primary_button(tr("new_tx_btn"))
        add.setIcon(icon("plus", "#ffffff"))
        add.clicked.connect(lambda: win.new_tx())
        top.addWidget(add)
        lay.addLayout(top)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.t_inc = Tile(tr("month_income"), INCOME_C)
        self.t_exp = Tile(tr("month_expense"), EXPENSE_C)
        self.t_net = Tile(tr("month_net"), accent())
        for t in (self.t_inc, self.t_exp, self.t_net):
            row.addWidget(t, 1)
        lay.addLayout(row)
        r2 = QHBoxLayout()
        r2.setSpacing(12)
        c1 = Card(tr("top_categories"))
        self.donut = DonutChart(fmt=lambda v: money.short(int(v), self.win.base()))
        self.donut.setMinimumHeight(220)
        c1.add(self.donut)
        c2 = Card(tr("six_months"))
        self.bars = BarChart(fmt=lambda v: money.short(int(v), self.win.base()))
        self.bars.setMinimumHeight(220)
        c2.add(self.bars)
        r2.addWidget(c1, 1)
        r2.addWidget(c2, 1)
        lay.addLayout(r2)
        r3 = QHBoxLayout()
        r3.setSpacing(12)
        c3 = Card(tr("recent"))
        self.recent = QTableWidget(0, 4)
        self.recent.horizontalHeader().setVisible(False)
        self.recent.verticalHeader().setVisible(False)
        self.recent.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.recent.setSelectionMode(QAbstractItemView.NoSelection)
        self.recent.setShowGrid(False)
        self.recent.setObjectName("Plain")
        self.recent.setFocusPolicy(Qt.NoFocus)
        self.recent.verticalHeader().setDefaultSectionSize(34)
        hh = self.recent.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self.recent.setMinimumHeight(260)
        c3.add(self.recent)
        c4 = Card(tr("budget_watch"))
        self.bud_box = QVBoxLayout()
        self.bud_box.setSpacing(8)
        c4.add(self.bud_box)
        c4.lay.addStretch(1)
        r3.addWidget(c3, 3)
        r3.addWidget(c4, 2)
        lay.addLayout(r3)
        lay.addStretch(1)

    def refresh(self):
        db, base = self.win.db, self.win.base()
        t = date.today()
        key = money.month_key(t)
        self.title.setText(tr("dash_title", m=month_name(t)))
        inc, exp = db.month_totals(key, base)
        pk = money.prev_months(key, 2)[0]
        pinc, pexp = db.month_totals(pk, base)
        self.t_inc.v.setText(money.fmt(inc, base))
        self.t_exp.v.setText(money.fmt(exp, base))
        self.t_net.v.setText(money.fmt(inc - exp, base, sign=True))
        self.t_net.v.setStyleSheet(f"color: {INCOME_C if inc >= exp else EXPENSE_C};")
        self.t_inc.sub.setText(tr("prev_month", v=money.short(pinc, base)))
        self.t_exp.sub.setText(tr("prev_month", v=money.short(pexp, base)))
        self.t_net.sub.setText(tr("saving_rate", p=round((inc - exp) * 100 / inc)) if inc > 0 else "")
        s, e = money.month_range(key)
        cats = db.by_category(s, e, "expense", base)
        data = [(c["name"] if c else tr("no_category"), v, c["color"] if c else "#868e96") for c, v in cats[:5]]
        rest = sum(v for _, v in cats[5:])
        if rest:
            data.append((tr("others"), rest, "#adb5bd"))
        self.donut.set_data(data, money.short(exp, base), tr("spent"))
        months = money.prev_months(key, 6)
        incs, exps = [], []
        for m in months:
            a, b = db.month_totals(m, base)
            incs.append(a)
            exps.append(b)
        self.bars.set_data([month_short(m) for m in months],
                           [(tr("income"), INCOME_C, incs), (tr("expense"), EXPENSE_C, exps)])
        rows = db.transactions(limit=8)
        self.recent.setRowCount(len(rows))
        for r, tx in enumerate(rows):
            fill_tx_row(self.recent, r, tx, compact=True)
        while self.bud_box.count():
            it = self.bud_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        usage = db.budget_usage(key, base)
        for c, spent, limit in usage[:6]:
            self.bud_box.addWidget(BudgetRow(c, spent, limit, base))
        if not usage:
            e = QLabel(tr("no_budgets"))
            e.setObjectName("Muted")
            e.setWordWrap(True)
            self.bud_box.addWidget(e)


def month_name(d: date) -> str:
    return f"{tr('mon_' + str(d.month))} {d.year}"


def month_short(key: str) -> str:
    y, m = map(int, key.split("-"))
    return tr("mons_" + str(m))


def fill_tx_row(table, r, tx, compact=False):
    """Operatsiya qatori: sana, toifa (belgi bilan), hisob/izoh, summa."""
    k = tx["kind"]
    d = date.fromisoformat(tx["date"])
    it0 = QTableWidgetItem(d.strftime("%d.%m" if compact else "%d.%m.%Y"))
    it0.setData(Qt.UserRole, tx["id"])
    it0.setForeground(QColor(pal()["muted"]))
    table.setItem(r, 0, it0)
    if k == "transfer":
        name = f"{tx['account_name']}  ›  {tx['to_account_name']}"
        it1 = QTableWidgetItem(icon("swap", pal()["muted"], 18), name)
    else:
        name = tx["category_name"] or tr("no_category")
        it1 = QTableWidgetItem(icon(tx["category_icon"] or "cat_other", tx["category_color"] or "#868e96", 18), name)
    if tx["note"]:
        it1.setToolTip(tx["note"])
    table.setItem(r, 1, it1)
    col = 2
    if not compact:
        table.setItem(r, col, QTableWidgetItem("" if k == "transfer" else tx["account_name"]))
        table.setItem(r, col + 1, QTableWidgetItem(tx["note"] or ""))
        col = 4
    else:
        table.setItem(r, col, QTableWidgetItem("" if k == "transfer" else tx["account_name"]))
        table.item(r, col).setForeground(QColor(pal()["muted"]))
        col = 3
    sign = {"income": 1, "expense": -1, "transfer": 0}[k]
    amt = money.fmt(tx["amount"] * (sign or 1), tx["currency"], sign=sign > 0)
    if k == "transfer" and tx["to_amount"] and tx["to_currency"] != tx["currency"]:
        amt += f"  ›  {money.fmt(tx['to_amount'], tx['to_currency'])}"
    it = QTableWidgetItem(amt)
    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
    it.setForeground(QColor(INCOME_C if k == "income" else (EXPENSE_C if k == "expense" else pal()["muted"])))
    f = it.font()
    f.setBold(True)
    it.setFont(f)
    it.setData(Qt.UserRole + 1, tx["amount"] * (sign or 1))
    table.setItem(r, col, it)


class BudgetRow(QWidget):
    def __init__(self, c, spent, limit, base):
        super().__init__()
        l = QVBoxLayout(self)
        l.setContentsMargins(0, 0, 0, 0)
        l.setSpacing(3)
        top = QHBoxLayout()
        ic = QLabel()
        ic.setPixmap(icon(c["icon"], c["color"], 18).pixmap(18, 18))
        top.addWidget(ic)
        n = QLabel(c["name"])
        top.addWidget(n, 1)
        lv = money.budget_level(spent, limit)
        col = {"ok": INCOME_C, "warn": "#e67700", "over": EXPENSE_C}[lv]
        v = QLabel(f"<span style='color:{col}; font-weight:600'>{money.short(spent, base)}</span>"
                   f" / {money.short(limit, base)}")
        top.addWidget(v)
        l.addLayout(top)
        pb = QProgressBar()
        pb.setRange(0, 1000)
        pb.setValue(min(1000, int(spent * 1000 / limit)) if limit else 0)
        pb.setTextVisible(False)
        pb.setFixedHeight(8)
        pb.setStyleSheet(f"QProgressBar::chunk {{ background: {col}; border-radius: 4px; }}")
        l.addWidget(pb)


# =========================================================================== operatsiyalar
class TxPage(QWidget):
    PERIODS = ["this_month", "last_month", "last_30", "this_year", "all", "custom"]

    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        f1 = QHBoxLayout()
        f1.setSpacing(6)
        self.period = QComboBox()
        for p in self.PERIODS:
            self.period.addItem(tr("p_" + p), p)
        self.d1 = QDateEdit()
        self.d2 = QDateEdit()
        for d in (self.d1, self.d2):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd.MM.yyyy")
        self.d1.setDate(QDate.currentDate().addMonths(-1))
        self.d2.setDate(QDate.currentDate())
        self.kind = QComboBox()
        self.kind.addItem(tr("all_types"), None)
        for k in ("expense", "income", "transfer"):
            self.kind.addItem(tr("k_" + k), k)
        self.acc = QComboBox()
        self.cat = QComboBox()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("search_ph"))
        self.search.setClearButtonEnabled(True)
        self.search.addAction(icon("search", pal()["muted"], 16), QLineEdit.LeadingPosition)
        for w in (self.period, self.d1, self.d2, self.kind, self.acc, self.cat):
            w.setMinimumContentsLength(6) if isinstance(w, QComboBox) else None
            f1.addWidget(w)
        f1.addWidget(self.search, 1)
        self.search.setMinimumWidth(150)
        lay.addLayout(f1)
        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels([tr("date"), tr("category"), tr("account"), tr("note"), tr("amount")])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Interactive)
        self.table.setColumnWidth(1, 200)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        hh.setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.setContextMenuPolicy(Qt.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        lay.addWidget(self.table, 1)
        bot = QHBoxLayout()
        self.totals = QLabel()
        self.totals.setObjectName("Totals")
        self.totals.setWordWrap(True)
        self.totals.setSizePolicy(QSizePolicy.Ignored, QSizePolicy.Preferred)
        bot.addWidget(self.totals, 1)
        self.b_edit = icon_button("edit", tr("edit"))
        self.b_del = icon_button("trash", tr("delete"))
        self.b_exp = icon_button("export", tr("export"), tr("export"))
        m = QMenu(self)
        m.addAction("Excel (.xlsx)", lambda: self.export("xlsx"))
        m.addAction("CSV", lambda: self.export("csv"))
        self.b_exp.setMenu(m)
        self.b_add = primary_button(tr("new_tx_btn"))
        self.b_add.setIcon(icon("plus", "#ffffff"))
        for b in (self.b_edit, self.b_del, self.b_exp, self.b_add):
            bot.addWidget(b)
        lay.addLayout(bot)
        self.period.currentIndexChanged.connect(self._period)
        for w in (self.d1, self.d2):
            w.dateChanged.connect(lambda *_: self.refresh())
        for w in (self.kind, self.acc, self.cat):
            w.currentIndexChanged.connect(lambda *_: self.refresh())
        self._t = QTimer(self)
        self._t.setSingleShot(True)
        self._t.timeout.connect(self.refresh)
        self.search.textChanged.connect(lambda *_: self._t.start(250))
        self.b_add.clicked.connect(lambda: win.new_tx())
        self.b_edit.clicked.connect(self.edit)
        self.b_del.clicked.connect(self.delete)
        for key, fn in (("Delete", self.delete), ("F2", self.edit)):
            s = QShortcut(QKeySequence(key), self.table)
            s.setContext(Qt.WidgetShortcut)
            s.activated.connect(fn)
        self._period()

    def fill_filters(self):
        for cb, items, all_key in ((self.acc, [(a["name"], a["id"]) for a in self.win.db.accounts(True)], "all_accounts"),
                                   (self.cat, [(c["name"], c["id"]) for c in self.win.db.categories()], "all_categories")):
            cur = cb.currentData()
            cb.blockSignals(True)
            cb.clear()
            cb.addItem(tr(all_key), None)
            for n, i in items:
                cb.addItem(n, i)
            cb.setCurrentIndex(max(0, cb.findData(cur)))
            cb.blockSignals(False)

    def _period(self):
        p = self.period.currentData()
        custom = p == "custom"
        self.d1.setVisible(custom)
        self.d2.setVisible(custom)
        self.refresh()

    def range(self):
        p = self.period.currentData()
        t = date.today()
        if p == "this_month":
            return money.month_range(money.month_key(t))
        if p == "last_month":
            return money.month_range(money.prev_months(money.month_key(t), 2)[0])
        if p == "last_30":
            return t - timedelta(days=29), t
        if p == "this_year":
            return date(t.year, 1, 1), date(t.year, 12, 31)
        if p == "custom":
            return pd(self.d1.date()), pd(self.d2.date())
        return None, None

    def rows(self):
        s, e = self.range()
        return self.win.db.transactions(s, e, self.acc.currentData(), self.cat.currentData(), self.kind.currentData(),
                                        self.search.text().strip())

    def refresh(self):
        rows = self.rows()
        self.table.setRowCount(len(rows))
        base = self.win.base()
        rates = self.win.db.current_rates()
        inc = exp = 0
        for r, tx in enumerate(rows):
            fill_tx_row(self.table, r, tx)
            try:
                v = money.convert(tx["amount"], tx["currency"], base, rates)
            except ValueError:
                v = 0
            if tx["kind"] == "income":
                inc += v
            elif tx["kind"] == "expense":
                exp += v
        self.totals.setText(tr("totals", n=len(rows), i=money.fmt(inc, base), e=money.fmt(exp, base),
                               d=money.fmt(inc - exp, base, sign=True)))
        self.totals.setToolTip(self.totals.text())

    def _sel(self):
        ids = []
        for idx in self.table.selectionModel().selectedRows():
            it = self.table.item(idx.row(), 0)
            if it:
                ids.append(it.data(Qt.UserRole))
        return ids

    def edit(self):
        ids = self._sel()
        if ids:
            self.win.edit_tx(ids[0])

    def delete(self):
        ids = self._sel()
        if ids and ask(self, tr("confirm_delete_tx", n=len(ids))):
            for i in ids:
                self.win.db.delete_tx(i)
            self.win.data_changed()

    def _menu(self, pos):
        if not self._sel():
            return
        m = QMenu(self)
        m.addAction(tr("edit"), self.edit)
        m.addAction(tr("duplicate"), self._dup)
        m.addSeparator()
        m.addAction(tr("delete"), self.delete)
        m.exec(self.table.viewport().mapToGlobal(pos))

    def _dup(self):
        ids = self._sel()
        if ids:
            t = self.win.db.tx(ids[0])
            self.win.db.add_tx(date.today(), t["kind"], t["account_id"], t["amount"], t["category_id"], t["note"],
                               t["to_account_id"], t["to_amount"])
            self.win.data_changed()

    def export(self, fmt):
        rows = self.rows()
        p, _ = QFileDialog.getSaveFileName(self, tr("export"), str(Path.home() / f"xarajatlar_{date.today():%Y%m%d}.{fmt}"),
                                           "Excel (*.xlsx)" if fmt == "xlsx" else "CSV (*.csv)")
        if not p:
            return
        try:
            export_transactions(rows, p, fmt)
            self.win.status(tr("saved_to", path=p))
        except Exception as ex:
            appmod.log_exception(ex)
            error(self, tr("export_error"))


def export_rows(rows):
    out = []
    for t in rows:
        sign = {"income": 1, "expense": -1, "transfer": -1}[t["kind"]]
        cat = t["category_name"] or (f"{t['account_name']} > {t['to_account_name']}" if t["kind"] == "transfer" else "")
        out.append([date.fromisoformat(t["date"]).strftime("%d.%m.%Y"), tr("k_" + t["kind"]), cat, t["account_name"],
                    round(sign * t["amount"] / 100, 2), t["currency"], t["note"] or ""])
    return out


def export_transactions(rows, path, fmt):
    heads = [tr("date"), tr("type"), tr("category"), tr("account"), tr("amount"), tr("currency"), tr("note")]
    data = export_rows(rows)
    if fmt == "xlsx":
        write_xlsx(path, tr("page_tx"), heads, data, widths=[12, 12, 24, 20, 16, 9, 40], title=tr("page_tx"))
    else:
        import csv
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(heads)
            for r in data:
                w.writerow([str(x).replace(".", ",") if isinstance(x, float) else x for x in r])


# =========================================================================== byudjet
class BudgetPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.key = money.month_key(date.today())
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        top = QHBoxLayout()
        self.prev = QPushButton("‹")
        self.next = QPushButton("›")
        for b in (self.prev, self.next):
            b.setFixedWidth(40)
            b.setObjectName("NavArrow")
        self.lbl = QLabel()
        self.lbl.setObjectName("MonthLabel")
        top.addWidget(self.prev)
        top.addWidget(self.lbl)
        top.addWidget(self.next)
        top.addStretch(1)
        self.copy = QPushButton(tr("copy_last"))
        top.addWidget(self.copy)
        lay.addLayout(top)
        self.summary = QLabel()
        self.summary.setObjectName("Muted")
        lay.addWidget(self.summary)
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels([tr("category"), tr("limit"), tr("spent_col"), tr("progress")])
        hh = self.table.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Fixed)
        self.table.setColumnWidth(1, 170)
        hh.setSectionResizeMode(2, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(3, QHeaderView.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(42)
        self.table.setSelectionMode(QAbstractItemView.NoSelection)
        self.table.setFocusPolicy(Qt.NoFocus)
        lay.addWidget(self.table, 1)
        h = QLabel(tr("budget_hint"))
        h.setObjectName("Muted")
        h.setWordWrap(True)
        lay.addWidget(h)
        self.prev.clicked.connect(lambda: self.shift(-1))
        self.next.clicked.connect(lambda: self.shift(1))
        self.copy.clicked.connect(self.copy_last)

    def shift(self, n):
        y, m = map(int, self.key.split("-"))
        self.key = money.month_key(money.add_months(date(y, m, 1), n))
        self.refresh()

    def refresh(self):
        db, base = self.win.db, self.win.base()
        y, m = map(int, self.key.split("-"))
        self.lbl.setText(month_name(date(y, m, 1)))
        s, e = money.month_range(self.key)
        spent = {c["id"] if c else 0: v for c, v in db.by_category(s, e, "expense", base)}
        bud = db.budgets(self.key)
        cats = db.categories("expense")
        self.table.setRowCount(len(cats))
        tot_l = tot_s = 0
        for r, c in enumerate(cats):
            it = QTableWidgetItem(icon(c["icon"], c["color"], 20), "  " + c["name"])
            self.table.setItem(r, 0, it)
            ed = AmountEdit()
            ed.setObjectName("BudgetEdit")
            ed.setPlaceholderText(tr("no_limit"))
            lim = bud.get(c["id"], 0)
            if lim:
                ed.set_cents(lim, base)
            ed.editingFinished.connect(lambda cid=c["id"], w=ed: self._set(cid, w))
            self.table.setCellWidget(r, 1, ed)
            sp = spent.get(c["id"], 0)
            si = QTableWidgetItem(money.fmt(sp, base))
            si.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.table.setItem(r, 2, si)
            box = QWidget()
            bl = QHBoxLayout(box)
            bl.setContentsMargins(10, 0, 10, 0)
            if lim:
                lv = money.budget_level(sp, lim)
                col = {"ok": INCOME_C, "warn": "#e67700", "over": EXPENSE_C}[lv]
                pb = QProgressBar()
                pb.setRange(0, 1000)
                pb.setValue(min(1000, int(sp * 1000 / lim)))
                pb.setTextVisible(False)
                pb.setFixedHeight(10)
                pb.setStyleSheet(f"QProgressBar::chunk {{ background: {col}; border-radius: 5px; }}")
                bl.addWidget(pb, 1)
                pl = QLabel(f"{round(sp * 100 / lim)}%")
                pl.setStyleSheet(f"color: {col}; font-weight: 600;")
                pl.setFixedWidth(48)
                bl.addWidget(pl)
                tot_l += lim
                tot_s += sp
            else:
                ml = QLabel("—")
                ml.setObjectName("Muted")
                bl.addWidget(ml)
            self.table.setCellWidget(r, 3, box)
        self.summary.setText(tr("budget_summary", s=money.fmt(tot_s, base), l=money.fmt(tot_l, base),
                                left=money.fmt(tot_l - tot_s, base)) if tot_l else tr("no_budgets"))

    def _set(self, cid, w):
        try:
            v = w.cents() if w.text().strip() else 0
        except ValueError:
            warn(self, tr("bad_amount"))
            return
        if v != self.win.db.budgets(self.key).get(cid, 0):
            self.win.db.set_budget(self.key, cid, v)
            QTimer.singleShot(0, self.win.data_changed)

    def copy_last(self):
        src = money.prev_months(self.key, 2)[0]
        n = self.win.db.copy_budgets(src, self.key)
        if n:
            self.win.data_changed()
            self.win.status(tr("copied_n", n=n))
        else:
            info(self, tr("nothing_to_copy"))


# =========================================================================== qarzlar
class DebtDialog(QDialog):
    def __init__(self, win, debt=None):
        super().__init__(win)
        self.setWindowTitle(tr("edit_debt") if debt else tr("new_debt"))
        self.setMinimumWidth(440)
        l = QVBoxLayout(self)
        f = QFormLayout()
        self.dir = QComboBox()
        self.dir.addItem(tr("lent"), "lent")
        self.dir.addItem(tr("borrowed"), "borrowed")
        self.person = QLineEdit()
        self.person.setPlaceholderText(tr("person_ph"))
        self.amount = AmountEdit()
        self.cur = QComboBox()
        self.cur.addItems(money.CURRENCIES)
        ar = QHBoxLayout()
        ar.addWidget(self.amount, 1)
        ar.addWidget(self.cur)
        self.date = QDateEdit(QDate.currentDate())
        self.has_due = QCheckBox(tr("has_due"))
        self.due = QDateEdit(QDate.currentDate().addMonths(1))
        for d in (self.date, self.due):
            d.setCalendarPopup(True)
            d.setDisplayFormat("dd.MM.yyyy")
        self.due.setEnabled(False)
        self.has_due.toggled.connect(self.due.setEnabled)
        dr = QHBoxLayout()
        dr.addWidget(self.due, 1)
        dr.addWidget(self.has_due)
        self.note = QLineEdit()
        f.addRow(tr("debt_dir"), self.dir)
        f.addRow(tr("person"), self.person)
        f.addRow(tr("amount"), ar)
        f.addRow(tr("date"), self.date)
        f.addRow(tr("due"), dr)
        f.addRow(tr("note"), self.note)
        l.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)
        if debt:
            self.dir.setCurrentIndex(max(0, self.dir.findData(debt["direction"])))
            self.person.setText(debt["person"])
            self.cur.setCurrentText(debt["currency"])
            self.amount.set_cents(debt["amount"], debt["currency"])
            self.date.setDate(qd(date.fromisoformat(debt["date"])))
            if debt["due"]:
                self.has_due.setChecked(True)
                self.due.setDate(qd(date.fromisoformat(debt["due"])))
            self.note.setText(debt["note"] or "")

    def _ok(self):
        try:
            if self.amount.cents() <= 0:
                raise ValueError
        except ValueError:
            warn(self, tr("bad_amount"))
            return
        if not self.person.text().strip():
            warn(self, tr("need_person"))
            return
        self.accept()

    def values(self):
        return (self.dir.currentData(), self.person.text().strip(), self.amount.cents(), self.cur.currentText(),
                pd(self.date.date()), pd(self.due.date()) if self.has_due.isChecked() else None,
                self.note.text().strip())


class DebtsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        row = QHBoxLayout()
        row.setSpacing(12)
        self.t_lent = Tile(tr("they_owe"), INCOME_C)
        self.t_borr = Tile(tr("i_owe"), EXPENSE_C)
        row.addWidget(self.t_lent, 1)
        row.addWidget(self.t_borr, 1)
        lay.addLayout(row)
        bar = QHBoxLayout()
        self.show_closed = QCheckBox(tr("show_closed"))
        bar.addWidget(self.show_closed)
        bar.addStretch(1)
        self.b_pay = icon_button("check", tr("add_payment"), tr("add_payment"))
        self.b_edit = icon_button("edit", tr("edit"))
        self.b_del = icon_button("trash", tr("delete"))
        self.b_add = primary_button(tr("new_debt"))
        self.b_add.setIcon(icon("plus", "#ffffff"))
        for b in (self.b_pay, self.b_edit, self.b_del, self.b_add):
            bar.addWidget(b)
        lay.addLayout(bar)
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels([tr("person"), tr("debt_dir"), tr("amount"), tr("paid"), tr("remaining"),
                                              tr("due"), tr("note")])
        hh = self.table.horizontalHeader()
        for i in range(7):
            hh.setSectionResizeMode(i, QHeaderView.Stretch if i in (0, 6) else QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        lay.addWidget(self.table, 1)
        self.empty = QLabel(tr("no_debts"))
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)
        self.show_closed.toggled.connect(lambda *_: self.refresh())
        self.b_add.clicked.connect(self.add)
        self.b_edit.clicked.connect(self.edit)
        self.b_del.clicked.connect(self.delete)
        self.b_pay.clicked.connect(self.pay)

    def refresh(self):
        db, base = self.win.db, self.win.base()
        rates = db.current_rates()
        rows = db.debts(self.show_closed.isChecked())
        self.table.setRowCount(len(rows))
        lent = borr = 0
        t = date.today()
        for r, d in enumerate(rows):
            rem = max(0, d["amount"] - d["paid"])
            try:
                v = money.convert(rem, d["currency"], base, rates)
            except ValueError:
                v = 0
            if not d["closed"]:
                if d["direction"] == "lent":
                    lent += v
                else:
                    borr += v
            overdue = d["due"] and not d["closed"] and date.fromisoformat(d["due"]) < t
            vals = [d["person"], tr(d["direction"]), money.fmt(d["amount"], d["currency"]),
                    money.fmt(d["paid"], d["currency"]), money.fmt(rem, d["currency"]),
                    date.fromisoformat(d["due"]).strftime("%d.%m.%Y") if d["due"] else "—", d["note"] or ""]
            for c, v_ in enumerate(vals):
                it = QTableWidgetItem(v_)
                if c == 0:
                    it.setData(Qt.UserRole, d["id"])
                    f = it.font()
                    f.setBold(True)
                    it.setFont(f)
                if c == 1:
                    it.setForeground(QColor(INCOME_C if d["direction"] == "lent" else EXPENSE_C))
                if c in (2, 3, 4):
                    it.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if c == 5 and overdue:
                    it.setForeground(QColor(EXPENSE_C))
                    it.setText(it.text() + "  " + tr("overdue"))
                if d["closed"]:
                    it.setForeground(QColor(pal()["muted"]))
                self.table.setItem(r, c, it)
        self.t_lent.v.setText(money.fmt(lent, base))
        self.t_borr.v.setText(money.fmt(borr, base))
        self.empty.setVisible(not rows)

    def _cur(self):
        r = self.table.currentRow()
        if r < 0 or not self.table.item(r, 0):
            return None
        did = self.table.item(r, 0).data(Qt.UserRole)
        for d in self.win.db.debts():
            if d["id"] == did:
                return d
        return None

    def add(self):
        dlg = DebtDialog(self.win)
        if dlg.exec():
            self.win.db.save_debt(None, *dlg.values())
            self.win.data_changed()

    def edit(self):
        d = self._cur()
        if d:
            dlg = DebtDialog(self.win, d)
            if dlg.exec():
                self.win.db.save_debt(d["id"], *dlg.values())
                self.win.data_changed()

    def delete(self):
        d = self._cur()
        if d and ask(self, tr("confirm_delete_debt", name=d["person"])):
            self.win.db.delete_debt(d["id"])
            self.win.data_changed()

    def pay(self):
        d = self._cur()
        if not d:
            info(self, tr("select_debt"))
            return
        rem = self.win.db.debt_remaining(d["id"])
        dlg = QDialog(self)
        dlg.setWindowTitle(tr("add_payment"))
        l = QFormLayout(dlg)
        amt = AmountEdit()
        amt.set_cents(rem, d["currency"])
        dt = QDateEdit(QDate.currentDate())
        dt.setCalendarPopup(True)
        dt.setDisplayFormat("dd.MM.yyyy")
        l.addRow(QLabel(tr("remaining_is", v=money.fmt(rem, d["currency"]))))
        l.addRow(tr("amount"), amt)
        l.addRow(tr("date"), dt)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(dlg.accept)
        bb.rejected.connect(dlg.reject)
        l.addRow(bb)
        if dlg.exec():
            try:
                v = amt.cents()
                if v <= 0:
                    raise ValueError
            except ValueError:
                warn(self, tr("bad_amount"))
                return
            self.win.db.add_payment(d["id"], min(v, rem) if rem else v, pd(dt.date()))
            self.win.data_changed()


# =========================================================================== takroriy
class RecurringDialog(QDialog):
    def __init__(self, win, rec=None):
        super().__init__(win)
        self.db = win.db
        self.setWindowTitle(tr("edit_rec") if rec else tr("new_rec"))
        self.setMinimumWidth(440)
        l = QVBoxLayout(self)
        f = QFormLayout()
        self.kind = QComboBox()
        self.kind.addItem(tr("k_expense"), "expense")
        self.kind.addItem(tr("k_income"), "income")
        self.amount = AmountEdit()
        self.account = QComboBox()
        for a in self.db.accounts():
            self.account.addItem(f"{a['name']} ({a['currency']})", a["id"])
        self.cat = QComboBox()
        self.freq = QComboBox()
        for fr in ("monthly", "weekly", "yearly"):
            self.freq.addItem(tr("f_" + fr), fr)
        self.next = QDateEdit(QDate.currentDate())
        self.next.setCalendarPopup(True)
        self.next.setDisplayFormat("dd.MM.yyyy")
        self.note = QLineEdit()
        self.note.setPlaceholderText(tr("rec_note_ph"))
        self.active = QCheckBox(tr("active"))
        self.active.setChecked(True)
        f.addRow(tr("type"), self.kind)
        f.addRow(tr("amount"), self.amount)
        f.addRow(tr("account"), self.account)
        f.addRow(tr("category"), self.cat)
        f.addRow(tr("frequency"), self.freq)
        f.addRow(tr("next_date"), self.next)
        f.addRow(tr("note"), self.note)
        f.addRow("", self.active)
        l.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)
        self.kind.currentIndexChanged.connect(lambda *_: self._cats())
        if rec:
            self.kind.setCurrentIndex(max(0, self.kind.findData(rec["kind"])))
            self.account.setCurrentIndex(max(0, self.account.findData(rec["account_id"])))
            self.amount.set_cents(rec["amount"], rec["currency"])
            self.freq.setCurrentIndex(max(0, self.freq.findData(rec["freq"])))
            self.next.setDate(qd(date.fromisoformat(rec["next_date"])))
            self.note.setText(rec["note"] or "")
            self.active.setChecked(bool(rec["active"]))
        self._cats(rec["category_id"] if rec else None)

    def _cats(self, sel=None):
        self.cat.clear()
        for c in self.db.categories(self.kind.currentData()):
            self.cat.addItem(icon(c["icon"], c["color"], 16), c["name"], c["id"])
        if sel:
            self.cat.setCurrentIndex(max(0, self.cat.findData(sel)))

    def _ok(self):
        try:
            if self.amount.cents() <= 0:
                raise ValueError
        except ValueError:
            warn(self, tr("bad_amount"))
            return
        if self.account.currentData() is None:
            warn(self, tr("need_account"))
            return
        self.accept()

    def values(self):
        return (self.kind.currentData(), self.account.currentData(), self.cat.currentData(), self.amount.cents(),
                self.note.text().strip(), self.freq.currentData(), pd(self.next.date()), self.active.isChecked())


class RecurringPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QVBoxLayout(self)
        lay.setSpacing(10)
        h = QLabel(tr("rec_hint"))
        h.setObjectName("Muted")
        h.setWordWrap(True)
        lay.addWidget(h)
        bar = QHBoxLayout()
        self.auto = QCheckBox(tr("rec_auto"))
        self.auto.setChecked(win.settings.get("rec_auto", True))
        self.auto.toggled.connect(lambda v: None if is_demo() else win.settings.set("rec_auto", v))
        bar.addWidget(self.auto)
        bar.addStretch(1)
        self.b_run = icon_button("repeat", tr("run_now"), tr("run_now"))
        self.b_edit = icon_button("edit", tr("edit"))
        self.b_del = icon_button("trash", tr("delete"))
        self.b_add = primary_button(tr("new_rec"))
        self.b_add.setIcon(icon("plus", "#ffffff"))
        for b in (self.b_run, self.b_edit, self.b_del, self.b_add):
            bar.addWidget(b)
        lay.addLayout(bar)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels([tr("category"), tr("amount"), tr("account"), tr("frequency"),
                                              tr("next_date"), tr("note")])
        hh = self.table.horizontalHeader()
        for i in range(6):
            hh.setSectionResizeMode(i, QHeaderView.Stretch if i in (0, 5) else QHeaderView.ResizeToContents)
        self.table.verticalHeader().setVisible(False)
        self.table.verticalHeader().setDefaultSectionSize(34)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setAlternatingRowColors(True)
        self.table.doubleClicked.connect(lambda *_: self.edit())
        lay.addWidget(self.table, 1)
        self.empty = QLabel(tr("no_rec"))
        self.empty.setObjectName("Muted")
        self.empty.setAlignment(Qt.AlignCenter)
        lay.addWidget(self.empty)
        self.b_add.clicked.connect(self.add)
        self.b_edit.clicked.connect(self.edit)
        self.b_del.clicked.connect(self.delete)
        self.b_run.clicked.connect(self.run)

    def refresh(self):
        rows = self.win.db.recurring()
        self.table.setRowCount(len(rows))
        for r, x in enumerate(rows):
            it = QTableWidgetItem(icon(x["category_icon"] or "cat_other", x["category_color"] or "#868e96", 18),
                                  x["category_name"] or tr("no_category"))
            it.setData(Qt.UserRole, x["id"])
            sign = 1 if x["kind"] == "income" else -1
            vals = [money.fmt(sign * x["amount"], x["currency"], sign=sign > 0), x["account_name"],
                    tr("f_" + x["freq"]), date.fromisoformat(x["next_date"]).strftime("%d.%m.%Y"), x["note"] or ""]
            self.table.setItem(r, 0, it)
            for c, v in enumerate(vals, 1):
                i2 = QTableWidgetItem(v)
                if c == 1:
                    i2.setForeground(QColor(INCOME_C if sign > 0 else EXPENSE_C))
                    i2.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                if not x["active"]:
                    i2.setForeground(QColor(pal()["muted"]))
                self.table.setItem(r, c, i2)
        self.empty.setVisible(not rows)

    def _cur(self):
        r = self.table.currentRow()
        if r < 0 or not self.table.item(r, 0):
            return None
        rid = self.table.item(r, 0).data(Qt.UserRole)
        return next((x for x in self.win.db.recurring() if x["id"] == rid), None)

    def add(self):
        if not self.win.db.accounts():
            warn(self, tr("need_account"))
            return
        dlg = RecurringDialog(self.win)
        if dlg.exec():
            self.win.db.save_recurring(None, *dlg.values())
            self.win.data_changed()

    def edit(self):
        x = self._cur()
        if x:
            dlg = RecurringDialog(self.win, x)
            if dlg.exec():
                self.win.db.save_recurring(x["id"], *dlg.values())
                self.win.data_changed()

    def delete(self):
        x = self._cur()
        if x and ask(self, tr("confirm_delete_rec")):
            self.win.db.delete_recurring(x["id"])
            self.win.data_changed()

    def run(self):
        n = self.win.db.run_recurring(date.today())
        self.win.data_changed()
        info(self, tr("rec_created", n=n))


# =========================================================================== hisoblar va toifalar
class AccountDialog(QDialog):
    def __init__(self, win, acc=None):
        super().__init__(win)
        self.setWindowTitle(tr("edit_account") if acc else tr("new_account"))
        self.setMinimumWidth(420)
        l = QVBoxLayout(self)
        f = QFormLayout()
        self.name = QLineEdit()
        self.kind = QComboBox()
        for k in ACCOUNT_KINDS:
            self.kind.addItem(tr("ak_" + k), k)
        self.cur = QComboBox()
        self.cur.addItems(money.CURRENCIES)
        self.opening = AmountEdit()
        self.color = COLORS[random.randrange(len(COLORS))]
        self.color_btn = QPushButton()
        self.color_btn.clicked.connect(self._pick)
        self.archived = QCheckBox(tr("archived"))
        f.addRow(tr("name"), self.name)
        f.addRow(tr("type"), self.kind)
        f.addRow(tr("currency"), self.cur)
        f.addRow(tr("opening"), self.opening)
        f.addRow(tr("color"), self.color_btn)
        f.addRow("", self.archived)
        l.addLayout(f)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)
        self.kind.currentIndexChanged.connect(self._kind)
        if acc:
            self.name.setText(acc["name"])
            self.kind.setCurrentIndex(max(0, self.kind.findData(acc["kind"])))
            self.cur.setCurrentText(acc["currency"])
            self.opening.set_cents(acc["opening"], acc["currency"])
            self.color = acc["color"]
            self.archived.setChecked(bool(acc["archived"]))
        self._paint()

    def _kind(self):
        if self.kind.currentData() == "usd_cash":
            self.cur.setCurrentText("USD")

    def _pick(self):
        c = QColorDialog.getColor(QColor(self.color), self)
        if c.isValid():
            self.color = c.name()
            self._paint()

    def _paint(self):
        self.color_btn.setText(self.color)
        self.color_btn.setStyleSheet(f"QPushButton {{ background: {self.color}; color: white; font-weight: 600; }}")

    def _ok(self):
        if not self.name.text().strip():
            warn(self, tr("need_name"))
            return
        try:
            self.opening.cents() if self.opening.text().strip() else 0
        except ValueError:
            warn(self, tr("bad_amount"))
            return
        self.accept()

    def values(self):
        op = 0
        if self.opening.text().strip():
            op = self.opening.cents()
        return dict(name=self.name.text().strip(), kind=self.kind.currentData(), currency=self.cur.currentText(),
                    opening=op, color=self.color, archived=1 if self.archived.isChecked() else 0)


class CategoryDialog(QDialog):
    def __init__(self, win, cat=None, kind="expense"):
        super().__init__(win)
        self.setWindowTitle(tr("edit_category") if cat else tr("new_category"))
        self.setMinimumWidth(440)
        l = QVBoxLayout(self)
        f = QFormLayout()
        self.name = QLineEdit()
        self.kind = QComboBox()
        self.kind.addItem(tr("k_expense"), "expense")
        self.kind.addItem(tr("k_income"), "income")
        self.kind.setCurrentIndex(0 if kind == "expense" else 1)
        f.addRow(tr("name"), self.name)
        f.addRow(tr("type"), self.kind)
        l.addLayout(f)
        l.addWidget(QLabel(tr("icon")))
        grid = QGridLayout()
        grid.setSpacing(4)
        self.icon_grp = QButtonGroup(self)
        self.color = cat["color"] if cat else COLORS[0]
        for i, ic in enumerate(CAT_ICONS):
            b = QToolButton()
            b.setCheckable(True)
            b.setIconSize(QSize(22, 22))
            b.setObjectName("IconPick")
            b.setProperty("ic", ic)
            self.icon_grp.addButton(b)
            grid.addWidget(b, i // 7, i % 7)
        l.addLayout(grid)
        l.addWidget(QLabel(tr("color")))
        crow = QHBoxLayout()
        self.col_grp = QButtonGroup(self)
        for c in COLORS:
            b = QToolButton()
            b.setCheckable(True)
            b.setFixedSize(26, 26)
            b.setProperty("col", c)
            b.setStyleSheet(f"QToolButton {{ background: {c}; border-radius: 13px; border: 2px solid transparent; }}"
                            f"QToolButton:checked {{ border: 3px solid {pal()['text']}; }}")
            self.col_grp.addButton(b)
            crow.addWidget(b)
        crow.addStretch(1)
        l.addLayout(crow)
        bb = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        bb.button(QDialogButtonBox.Ok).setText(tr("save"))
        bb.button(QDialogButtonBox.Cancel).setText(tr("cancel"))
        bb.accepted.connect(self._ok)
        bb.rejected.connect(self.reject)
        l.addWidget(bb)
        cur_icon = cat["icon"] if cat else "cat_other"
        if cat:
            self.name.setText(cat["name"])
            self.kind.setCurrentIndex(0 if cat["kind"] == "expense" else 1)
        for b in self.icon_grp.buttons():
            if b.property("ic") == cur_icon:
                b.setChecked(True)
        for b in self.col_grp.buttons():
            if b.property("col") == self.color:
                b.setChecked(True)
        if not self.col_grp.checkedButton():
            self.col_grp.buttons()[0].setChecked(True)
        self.col_grp.buttonClicked.connect(lambda *_: self._paint())
        self._paint()

    def _paint(self):
        b = self.col_grp.checkedButton()
        self.color = b.property("col") if b else self.color
        for ib in self.icon_grp.buttons():
            ib.setIcon(icon(ib.property("ic"), self.color, 22))

    def _ok(self):
        if not self.name.text().strip():
            warn(self, tr("need_name"))
            return
        self.accept()

    def values(self):
        b = self.icon_grp.checkedButton()
        return (self.name.text().strip(), self.kind.currentData(), self.color, b.property("ic") if b else "cat_other")


class AccountsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        lay.setSpacing(14)
        ac = Card(tr("accounts"))
        self.acc = QTableWidget(0, 4)
        self.acc.setHorizontalHeaderLabels([tr("name"), tr("type"), tr("currency"), tr("balance")])
        hh = self.acc.horizontalHeader()
        hh.setSectionResizeMode(0, QHeaderView.Stretch)
        for i in (1, 2, 3):
            hh.setSectionResizeMode(i, QHeaderView.ResizeToContents)
        self.acc.verticalHeader().setVisible(False)
        self.acc.verticalHeader().setDefaultSectionSize(36)
        self.acc.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.acc.setSelectionMode(QAbstractItemView.SingleSelection)
        self.acc.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.acc.doubleClicked.connect(lambda *_: self.edit_acc())
        ac.add(self.acc)
        r = QHBoxLayout()
        b1 = icon_button("plus", tr("new_account"), tr("new_account"))
        b2 = icon_button("edit", tr("edit"))
        b3 = icon_button("trash", tr("delete"))
        r.addWidget(b1)
        r.addStretch(1)
        r.addWidget(b2)
        r.addWidget(b3)
        ac.add(r)
        b1.clicked.connect(self.add_acc)
        b2.clicked.connect(self.edit_acc)
        b3.clicked.connect(self.del_acc)
        lay.addWidget(ac, 3)
        cc = Card(tr("categories"))
        self.cat_kind = QComboBox()
        self.cat_kind.addItem(tr("k_expense"), "expense")
        self.cat_kind.addItem(tr("k_income"), "income")
        cc.add(self.cat_kind)
        self.cats = QListWidget()
        self.cats.setIconSize(QSize(22, 22))
        self.cats.setObjectName("CatList")
        self.cats.itemDoubleClicked.connect(lambda *_: self.edit_cat())
        cc.add(self.cats)
        r2 = QHBoxLayout()
        c1 = icon_button("plus", tr("new_category"), tr("new_category"))
        c2 = icon_button("edit", tr("edit"))
        c3 = icon_button("trash", tr("delete"))
        r2.addWidget(c1)
        r2.addStretch(1)
        r2.addWidget(c2)
        r2.addWidget(c3)
        cc.add(r2)
        c1.clicked.connect(self.add_cat)
        c2.clicked.connect(self.edit_cat)
        c3.clicked.connect(self.del_cat)
        self.cat_kind.currentIndexChanged.connect(lambda *_: self.refresh())
        lay.addWidget(cc, 2)

    def refresh(self):
        db = self.win.db
        accs = db.accounts(True)
        self.acc.setRowCount(len(accs))
        for r, a in enumerate(accs):
            it = QTableWidgetItem(icon("wallet", a["color"], 18), a["name"])
            it.setData(Qt.UserRole, a["id"])
            self.acc.setItem(r, 0, it)
            self.acc.setItem(r, 1, QTableWidgetItem(tr("ak_" + a["kind"]) if a["kind"] in ACCOUNT_KINDS else a["kind"]))
            self.acc.setItem(r, 2, QTableWidgetItem(a["currency"]))
            b = QTableWidgetItem(money.fmt(db.balance(a["id"]), a["currency"]))
            b.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            f = b.font()
            f.setBold(True)
            b.setFont(f)
            if a["archived"]:
                for c in range(3):
                    self.acc.item(r, c).setForeground(QColor(pal()["muted"]))
                b.setForeground(QColor(pal()["muted"]))
            self.acc.setItem(r, 3, b)
        self.cats.clear()
        for c in db.categories(self.cat_kind.currentData()):
            it = QListWidgetItem(icon(c["icon"], c["color"], 22), c["name"])
            it.setData(Qt.UserRole, c["id"])
            self.cats.addItem(it)

    def _acc_id(self):
        r = self.acc.currentRow()
        return self.acc.item(r, 0).data(Qt.UserRole) if r >= 0 and self.acc.item(r, 0) else None

    def add_acc(self):
        dlg = AccountDialog(self.win)
        if dlg.exec():
            self.win.db.save_account(None, **dlg.values())
            self.win.data_changed()

    def edit_acc(self):
        aid = self._acc_id()
        if aid:
            dlg = AccountDialog(self.win, self.win.db.account(aid))
            if dlg.exec():
                self.win.db.save_account(aid, **dlg.values())
                self.win.data_changed()

    def del_acc(self):
        aid = self._acc_id()
        if not aid:
            return
        a = self.win.db.account(aid)
        if self.win.db.account_used(aid):
            info(self, tr("account_in_use"))
            return
        if ask(self, tr("confirm_delete_account", name=a["name"])):
            self.win.db.delete_account(aid)
            self.win.data_changed()

    def _cat_id(self):
        it = self.cats.currentItem()
        return it.data(Qt.UserRole) if it else None

    def add_cat(self):
        dlg = CategoryDialog(self.win, None, self.cat_kind.currentData())
        if dlg.exec():
            self.win.db.save_category(None, *dlg.values())
            self.win.data_changed()

    def edit_cat(self):
        cid = self._cat_id()
        if cid:
            dlg = CategoryDialog(self.win, self.win.db.category(cid))
            if dlg.exec():
                self.win.db.save_category(cid, *dlg.values())
                self.win.data_changed()

    def del_cat(self):
        cid = self._cat_id()
        if not cid:
            return
        c = self.win.db.category(cid)
        n = self.win.db.category_used(cid)
        others = [x for x in self.win.db.categories(c["kind"]) if x["id"] != cid]
        if n and not others:
            info(self, tr("last_category"))
            return
        move_to = None
        if n:
            target = next((x for x in others if x["key"] in ("other_e", "other_i")), others[-1])
            if not ask(self, tr("confirm_delete_cat_used", name=c["name"], n=n, other=target["name"])):
                return
            move_to = target["id"]
        elif not ask(self, tr("confirm_delete_cat", name=c["name"])):
            return
        self.win.db.delete_category(cid, move_to)
        self.win.data_changed()


# =========================================================================== kurslar va ma'lumotlar
class SettingsPage(QWidget):
    def __init__(self, win):
        super().__init__()
        self.win = win
        lay = QHBoxLayout(self)
        lay.setSpacing(14)
        rc = Card(tr("rates"))
        h = QLabel(tr("rates_hint"))
        h.setObjectName("Muted")
        h.setWordWrap(True)
        rc.add(h)
        f = QFormLayout()
        self.usd = QLineEdit()
        self.rub = QLineEdit()
        self.usd.setPlaceholderText("12 800")
        self.rub.setPlaceholderText("140")
        self.rdate = QDateEdit(QDate.currentDate())
        self.rdate.setCalendarPopup(True)
        self.rdate.setDisplayFormat("dd.MM.yyyy")
        f.addRow("1 USD =", self._suffix(self.usd))
        f.addRow("1 RUB =", self._suffix(self.rub))
        f.addRow(tr("date"), self.rdate)
        rc.add(f)
        sb = primary_button(tr("save_rates"))
        sb.clicked.connect(self.save_rates)
        r = QHBoxLayout()
        r.addStretch(1)
        r.addWidget(sb)
        rc.add(r)
        self.hist = QTableWidget(0, 3)
        self.hist.setHorizontalHeaderLabels([tr("date"), tr("currency"), tr("rate_uzs")])
        self.hist.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.hist.verticalHeader().setVisible(False)
        self.hist.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.hist.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.hist.setContextMenuPolicy(Qt.CustomContextMenu)
        self.hist.customContextMenuRequested.connect(self._hist_menu)
        rc.add(self.hist)
        lay.addWidget(rc, 1)
        col = QVBoxLayout()
        col.setSpacing(14)
        bc = Card(tr("base_currency"))
        self.base = QComboBox()
        self.base.addItems(money.CURRENCIES)
        self.base.setCurrentText(win.base())
        self.base.currentTextChanged.connect(self._base)
        bc.add(self.base)
        hb = QLabel(tr("base_hint"))
        hb.setObjectName("Muted")
        hb.setWordWrap(True)
        bc.add(hb)
        col.addWidget(bc)
        dc = Card(tr("backup"))
        hd = QLabel(tr("backup_hint"))
        hd.setObjectName("Muted")
        hd.setWordWrap(True)
        dc.add(hd)
        rr = QHBoxLayout()
        b1 = icon_button("backup", tr("make_backup"), tr("make_backup"))
        b2 = icon_button("import", tr("restore"), tr("restore"))
        b3 = icon_button("folder", tr("open_data_folder"))
        b1.clicked.connect(win.backup)
        b2.clicked.connect(win.restore)
        b3.clicked.connect(lambda: open_path(str(win.db.path.parent)))
        rr.addWidget(b1)
        rr.addWidget(b2)
        rr.addStretch(1)
        rr.addWidget(b3)
        dc.add(rr)
        col.addWidget(dc)
        col.addStretch(1)
        lay.addLayout(col, 1)

    def _suffix(self, w):
        box = QWidget()
        h = QHBoxLayout(box)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(w, 1)
        h.addWidget(QLabel(tr("sum_sym")))
        return box

    def refresh(self):
        rates = self.win.db.current_rates()
        for cur, w in (("USD", self.usd), ("RUB", self.rub)):
            if cur in rates:
                w.setText(f"{rates[cur].normalize():f}".replace(".", ","))
        rows = self.win.db.rate_history()
        self.hist.setRowCount(len(rows))
        for r, x in enumerate(rows):
            it = QTableWidgetItem(date.fromisoformat(x["date"]).strftime("%d.%m.%Y"))
            it.setData(Qt.UserRole, x["id"])
            self.hist.setItem(r, 0, it)
            self.hist.setItem(r, 1, QTableWidgetItem(x["currency"]))
            v = QTableWidgetItem(money.group(int(Decimal(x["rate"]))) if Decimal(x["rate"]) >= 1000 else x["rate"])
            v.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.hist.setItem(r, 2, v)

    def save_rates(self):
        d = pd(self.rdate.date())
        saved = 0
        for cur, w in (("USD", self.usd), ("RUB", self.rub)):
            t = w.text().strip()
            if not t:
                continue
            try:
                v = Decimal(money.parse_amount(t)) / 100
                if v <= 0:
                    raise ValueError
            except (ValueError, InvalidOperation):
                warn(self, tr("bad_rate", c=cur))
                return
            self.win.db.set_rate(cur, v, d)
            saved += 1
        if saved:
            self.win.data_changed()
            self.win.status(tr("rates_saved"))

    def _hist_menu(self, pos):
        r = self.hist.currentRow()
        if r < 0:
            return
        m = QMenu(self)
        m.addAction(tr("delete"), lambda: (self.win.db.delete_rate(self.hist.item(r, 0).data(Qt.UserRole)),
                                           self.win.data_changed()))
        m.exec(self.hist.viewport().mapToGlobal(pos))

    def _base(self, cur):
        if not is_demo():
            self.win.settings.set("base", cur)
        self.win._base = cur
        self.win.data_changed()


# =========================================================================== demo
def load_demo(db: DB):
    rnd = random.Random(11)
    t = date.today()
    db.set_rate("USD", Decimal("12750"), t - timedelta(days=40))
    db.set_rate("USD", Decimal("12830"), t - timedelta(days=3))
    db.set_rate("RUB", Decimal("139.5"), t - timedelta(days=3))
    accs = db.accounts()
    cash, card = accs[0]["id"], accs[1]["id"]
    db.save_account(cash, name=accs[0]["name"], kind="cash", currency="UZS", opening=1_200_000_000, color="#12805c",
                    archived=0)
    uzc = db.save_account(None, name="Uzcard", kind="uzcard", currency="UZS", opening=1_100_000_000, color="#f08c00",
                          archived=0)
    usd = db.save_account(None, name="Dollar", kind="usd_cash", currency="USD", opening=120_000, color="#2f9e44",
                          archived=0)
    cats = {c["key"]: c["id"] for c in db.categories()}
    exp_plan = [("food", 45_000, 180_000, 9), ("transport", 8_000, 40_000, 8), ("cafe", 35_000, 120_000, 3),
                ("phone", 60_000, 90_000, 1), ("utility", 150_000, 420_000, 2), ("health", 50_000, 300_000, 1),
                ("edu", 150_000, 600_000, 1), ("clothes", 200_000, 700_000, 1), ("fun", 50_000, 200_000, 1),
                ("gift", 100_000, 400_000, 1)]
    start = money.add_months(date(t.year, t.month, 1), -5)
    for k in range(6):
        ms = money.add_months(start, k)
        last_day = money.month_range(money.month_key(ms))[1]
        end = min(last_day, t)
        db.add_tx(ms.replace(day=min(5, end.day)), "income", card, 7_800_000_00 + rnd.randint(0, 4) * 50_000_00,
                  cats["salary"], "Universitet")
        if k % 2 == 0:
            db.add_tx(ms.replace(day=min(20, end.day)), "income", card, rnd.choice([1_200_000_00, 1_500_000_00]),
                      cats["side"], "Kurs darslari")
        if k == 2:
            db.add_tx(ms.replace(day=min(12, end.day)), "income", card, 6_000_000_00, cats["grant"], "Yosh olimlar granti")
        db.add_tx(ms.replace(day=min(1, end.day)), "expense", card, 2_500_000_00, cats["home"], "Ijara")
        for key, lo, hi, per in exp_plan:
            for _ in range(per):
                dd = ms.replace(day=rnd.randint(1, end.day))
                acc = rnd.choice([cash, card, uzc])
                db.add_tx(dd, "expense", acc, rnd.randint(lo, hi) // 1000 * 1000 * 100, cats[key])
    db.add_tx(t - timedelta(days=2), "transfer", card, 1_000_000_00, None, "Naqdga yechish", cash, None)
    db.add_tx(t - timedelta(days=9), "expense", usd, 4_500, cats["edu"], "Online kurs")
    key = money.month_key(t)
    for k, amt in (("food", 3_500_000_00), ("transport", 600_000_00), ("cafe", 800_000_00), ("utility", 900_000_00),
                   ("clothes", 1_000_000_00), ("fun", 500_000_00)):
        db.set_budget(key, cats[k], amt)
    db.save_debt(None, "lent", "Sardor", 2_000_000_00, "UZS", t - timedelta(days=30), t + timedelta(days=10), "")
    did = db.save_debt(None, "borrowed", "Akmal aka", 500_00, "USD", t - timedelta(days=60), t - timedelta(days=5),
                       "Noutbuk uchun")
    db.add_payment(did, 200_00, t - timedelta(days=20))
    db.save_recurring(None, "expense", card, cats["home"], 2_500_000_00, "Ijara", "monthly",
                      money.add_months(date(t.year, t.month, 1), 1))
    db.save_recurring(None, "expense", card, cats["phone"], 90_000_00, "Internet", "monthly",
                      date(t.year, t.month, 1) + timedelta(days=24) if t.day < 25 else
                      money.add_months(date(t.year, t.month, 25), 1))


# =========================================================================== asosiy oyna
class SideNav(QFrame):
    def __init__(self, win):
        super().__init__()
        self.win = win
        self.setObjectName("Side")
        self.setFixedWidth(212)
        l = QVBoxLayout(self)
        l.setContentsMargins(14, 16, 14, 14)
        l.setSpacing(4)
        cap = QLabel(tr("total_balance"))
        cap.setObjectName("SideCap")
        self.total = QLabel()
        self.total.setObjectName("SideTotal")
        self.total.setWordWrap(True)
        l.addWidget(cap)
        l.addWidget(self.total)
        l.addSpacing(10)
        self.grp = QButtonGroup(self)
        self.btns = []
        for i, (k, ic) in enumerate((("page_dash", "pie"), ("page_tx", "list"), ("page_budget", "budget"),
                                     ("page_debts", "handshake"), ("page_rec", "repeat"), ("page_accounts", "wallet"),
                                     ("page_settings", "rate"))):
            b = QPushButton(tr(k).replace("&", "&&"))
            b.setCheckable(True)
            b.setObjectName("SideBtn")
            b.setProperty("ic", ic)
            b.setIconSize(QSize(18, 18))
            b.setCursor(Qt.PointingHandCursor)
            self.grp.addButton(b, i)
            self.btns.append(b)
            l.addWidget(b)
        l.addSpacing(12)
        ac = QLabel(tr("accounts"))
        ac.setObjectName("SideCap")
        l.addWidget(ac)
        self.acc_box = QVBoxLayout()
        self.acc_box.setSpacing(2)
        l.addLayout(self.acc_box)
        l.addStretch(1)
        self.recolor()

    def recolor(self):
        for b in self.btns:
            b.setIcon(icon(b.property("ic"), "#ffffff" if b.isChecked() else "#a8c5b8", 18))

    def refresh(self):
        db, base = self.win.db, self.win.base()
        self.total.setText(money.fmt(db.total_balance(base), base))
        while self.acc_box.count():
            it = self.acc_box.takeAt(0)
            if it.widget():
                it.widget().deleteLater()
        for a in db.accounts()[:8]:
            row = QLabel(f"<span style='color:{a['color']}'>&#9679;</span>&nbsp; {a['name']}"
                         f"<span style='float:right'></span>")
            row.setObjectName("SideAcc")
            w = QWidget()
            h = QHBoxLayout(w)
            h.setContentsMargins(4, 2, 4, 2)
            h.addWidget(row, 1)
            v = QLabel(money.short(db.balance(a["id"]), a["currency"]) + ("" if a["currency"] == "UZS" else f" {a['currency']}"))
            v.setObjectName("SideAccV")
            h.addWidget(v)
            self.acc_box.addWidget(w)


class PageCount:
    """BaseMainWindow._nav o'rnida: tekshiruv vositalari sahifalar sonini bilishi uchun."""

    def __init__(self, stack):
        self.stack = stack

    def count(self):
        return self.stack.count()


class MainWindow(BaseMainWindow):
    def __init__(self):
        super().__init__()
        self.data_dir = app_data_dir(SLUG)
        money.SYMBOLS["UZS"] = tr("sum_sym")
        money.SHORT_UNITS.update(bn=tr("u_bn"), m=tr("u_m"), k=tr("u_k"))
        self.db = DB(self.data_dir / "xarajatlar.db")
        self._base = self.settings.get("base", "UZS") if not is_demo() else "UZS"
        if self._base not in money.CURRENCIES:
            self._base = "UZS"
        self.db.seed({k: tr("cat_" + k) for k in ("food", "transport", "utility", "home", "phone", "health", "edu",
                                                    "clothes", "fun", "cafe", "gift", "other_e", "salary", "scholar",
                                                    "grant", "side", "other_i")},
                     {"cash": tr("acc_cash"), "card": tr("acc_card")})
        if is_demo() and not self.db.get_meta("demo"):
            load_demo(self.db)
            self.db.set_meta("demo", "1")
        root = QWidget()
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        self.side = SideNav(self)
        h.addWidget(self.side)
        self.stack = QStackedWidget()
        h.addWidget(self.stack, 1)
        self.setCentralWidget(root)
        self.dash = Dashboard(self)
        self.txp = TxPage(self)
        self.budget = BudgetPage(self)
        self.debts = DebtsPage(self)
        self.rec = RecurringPage(self)
        self.accounts = AccountsPage(self)
        self.settings_page = SettingsPage(self)
        self.pages = [self.dash, self.txp, self.budget, self.debts, self.rec, self.accounts, self.settings_page]
        titles = ["page_dash", "page_tx", "page_budget", "page_debts", "page_rec", "page_accounts", "page_settings"]
        for w, t in zip(self.pages, titles):
            holder = QWidget()
            hl = QVBoxLayout(holder)
            hl.setContentsMargins(24, 18, 24, 16)
            hl.setSpacing(10)
            if w is not self.dash:
                lab = QLabel(tr(t))
                lab.setObjectName("Title")
                hl.addWidget(lab)
            hl.addWidget(w, 1)
            self.stack.addWidget(holder)
        self.side.grp.idClicked.connect(self.set_page)
        self._nav = PageCount(self.stack)   # uzkit/verify: sahifalar soni
        a = QAction(tr("new_tx"), self)
        a.setShortcut("Ctrl+N")
        a.triggered.connect(lambda: self.new_tx())
        b = QAction(tr("make_backup"), self)
        b.triggered.connect(self.backup)
        c = QAction(tr("restore"), self)
        c.triggered.connect(self.restore)
        first = self.menu_file.actions()[0]
        for x in (a, b, c):
            self.menu_file.insertAction(first, x)
        self.menu_file.insertSeparator(first)
        # takroriy to'lovlar
        if not is_demo() and "pytest" not in sys.modules:
            due = self.db.due_recurring(date.today())
            if due:
                if self.settings.get("rec_auto", True):
                    n = self.db.run_recurring(date.today())
                    QTimer.singleShot(800, lambda: self.status(tr("rec_created", n=n), 8000))
                else:
                    QTimer.singleShot(600, lambda: self._ask_recurring(len(due)))
        self.txp.fill_filters()
        self.data_changed()
        self.set_page(0)

    def _ask_recurring(self, n):
        if ask(self, tr("rec_ask", n=n)):
            self.db.run_recurring(date.today())
            self.data_changed()

    def base(self):
        return self._base

    def set_page(self, i):
        if not 0 <= i < self.stack.count():
            return
        self.stack.setCurrentIndex(i)
        self.side.grp.button(i).setChecked(True)
        self.side.recolor()

    def data_changed(self):
        self.side.refresh()
        self.txp.fill_filters()
        for p in self.pages:
            p.refresh()

    def on_theme_changed(self):
        from .ui_extra import _ICON_CACHE
        _ICON_CACHE.clear()
        self.side.recolor()
        self.data_changed()

    def new_tx(self, kind="expense"):
        if not self.db.accounts():
            warn(self, tr("need_account"))
            return
        dlg = TxDialog(self, None, kind)
        dlg.exec()
        if dlg.saved_any:
            self.data_changed()

    def edit_tx(self, tid):
        t = self.db.tx(tid)
        if not t:
            return
        dlg = TxDialog(self, t)
        if dlg.exec():
            self.data_changed()

    def backup(self):
        p, _ = QFileDialog.getSaveFileName(self, tr("make_backup"),
                                           str(Path.home() / f"xarajatlar_zaxira_{datetime.now():%Y%m%d_%H%M}.db"),
                                           tr("db_files") + " (*.db)")
        if not p:
            return
        try:
            self.db.backup_to(p)
            info(self, tr("backup_done", path=p))
        except Exception as ex:
            appmod.log_exception(ex)
            error(self, tr("backup_error"))

    def restore(self):
        p, _ = QFileDialog.getOpenFileName(self, tr("restore"), str(Path.home()), tr("db_files") + " (*.db)")
        if not p:
            return
        if not validate_db_file(p):
            error(self, tr("restore_invalid"))
            return
        if not ask(self, tr("confirm_restore")):
            return
        try:
            safety = restore_from(self.db, p)
        except Exception as ex:
            appmod.log_exception(ex)
            error(self, tr("restore_error"))
            self.db = DB(self.data_dir / "xarajatlar.db")
            return
        self.db = DB(self.data_dir / "xarajatlar.db")
        self.data_changed()
        info(self, tr("restore_done", path=str(safety)))
