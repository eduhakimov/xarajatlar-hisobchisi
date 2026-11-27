"""Bir oylik real ssenariy: qo'lda hisoblangan qoldiqlar, ko'p valyutali o'tkazma, byudjet, qarz, takroriy."""
import os
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from xarajatlar_hisobchisi import money  # noqa: E402
from xarajatlar_hisobchisi.db import DB, restore_from  # noqa: E402


def test_parse_amount_fractions_vs_grouping():
    assert money.parse_amount("0.125") == 13          # 0,125 -> 0,13 (yarimdan yuqoriga)
    assert money.parse_amount("-0.125") == -13
    assert money.parse_amount("12.800") == 1_280_000  # minglik ajratgich
    assert money.parse_amount("1.5") == 150


def _db(tmp_path):
    db = DB(tmp_path / "Ҳисоб o'quv" / "x.db")
    names = {k: k for k in ("food", "transport", "utility", "home", "phone", "health", "edu", "clothes", "fun",
                            "cafe", "gift", "other_e", "salary", "scholar", "grant", "side", "other_i")}
    db.seed(names, {"cash": "Naqd", "card": "Karta"})
    return db


def test_month_scenario_hand_values(tmp_path):
    db = _db(tmp_path)
    cash, card = (a["id"] for a in db.accounts())
    usd = db.save_account(None, name="Dollar", kind="cash", currency="USD", opening=50_000, color="#000",
                          archived=0)                                     # $500.00
    db.set_rate("USD", Decimal("12800"), date(2026, 3, 1))
    cats = {c["key"]: c["id"] for c in db.categories()}
    db.add_tx(date(2026, 3, 1), "income", card, 650_000_000, cats["salary"])          # 6 500 000 so'm
    db.add_tx(date(2026, 3, 2), "expense", card, 45_000_000, cats["food"])            # 450 000
    db.add_tx(date(2026, 3, 5), "expense", cash, 12_000_000, cats["transport"])       # 120 000
    db.add_tx(date(2026, 3, 6), "transfer", card, 100_000_000, to_account_id=cash)    # 1 000 000
    db.add_tx(date(2026, 3, 7), "transfer", usd, 10_000, to_account_id=card,
              to_amount=money.convert(10_000, "USD", "UZS", db.current_rates()))     # $100 -> 1 280 000
    db.add_tx(date(2026, 4, 1), "expense", card, 1_000_000, cats["food"])             # keyingi oy
    assert db.balance(card, date(2026, 3, 31)) == 650_000_000 - 45_000_000 - 100_000_000 + 128_000_000
    assert db.balance(cash) == -12_000_000 + 100_000_000
    assert db.balance(usd) == 40_000
    inc, exp = db.month_totals("2026-03", "UZS")
    assert (inc, exp) == (650_000_000, 57_000_000)             # o'tkazmalar daromad/xarajat emas
    # jami (aprel xarajati bilan): karta 6 320 000 + naqd 880 000 + $400 · 12 800 = 12 320 000 so'm
    assert db.total_balance("UZS") == 632_000_000 + 88_000_000 + 512_000_000
    db.set_budget("2026-03", cats["food"], 50_000_000)
    db.set_budget("2026-03", cats["transport"], 10_000_000)
    use = {c["key"]: (s, lim) for c, s, lim in db.budget_usage("2026-03", "UZS")}
    assert money.budget_level(*use["food"]) == "warn"         # 90 %
    assert money.budget_level(*use["transport"]) == "over"    # 120 %


def test_recurring_month_end_anchor(tmp_path):
    db = _db(tmp_path)
    card = db.accounts()[1]["id"]
    db.save_recurring(None, "expense", card, None, 9_900_000, "ijara", "monthly", date(2026, 1, 31))
    n = db.run_recurring(date(2026, 4, 30))
    assert n == 4
    dates = sorted(t["date"] for t in db.transactions())
    assert dates == ["2026-01-31", "2026-02-28", "2026-03-31", "2026-04-30"]
    assert db.run_recurring(date(2026, 4, 30)) == 0            # ikki marta yaratilmaydi
    assert db.recurring()[0]["next_date"] == "2026-05-31"      # 31-sana langari saqlanadi


def test_debt_partial_payments(tmp_path):
    db = _db(tmp_path)
    did = db.save_debt(None, "lent", "Ali", 300_000_00, "UZS", date(2026, 3, 1), date(2026, 4, 1), "")
    db.add_payment(did, 100_000_00, date(2026, 3, 10))
    assert db.debt_remaining(did) == 200_000_00
    db.add_payment(did, 200_000_00, date(2026, 3, 20))
    assert db.debt_remaining(did) == 0
    assert db.debts()[0]["closed"] == 1


def test_restore_into_unicode_path(tmp_path):
    db = _db(tmp_path)
    card = db.accounts()[1]["id"]
    db.add_tx(date(2026, 3, 1), "income", card, 500, None, "биринчи")
    bk = tmp_path / "Заxира o'quv.db"
    db.backup_to(str(bk))
    db.add_tx(date(2026, 3, 2), "income", card, 1, None)
    path = db.path
    restore_from(db, str(bk))
    db2 = DB(path)
    assert [t["note"] for t in db2.transactions()] == ["биринчи"]
    db2.close()


@pytest.fixture
def win(tmp_path, monkeypatch):
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    from PySide6.QtWidgets import QApplication
    from uzkit import app as appmod, i18n
    from uzkit.settings import Settings
    QApplication.instance() or QApplication([])
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings("xarajat_ui_test")
    appmod.SETTINGS.set("base", "XYZ")
    appmod.SETTINGS.set("last_account", "nonsense")
    i18n.set_language("uz")
    from xarajatlar_hisobchisi import window as wmod
    monkeypatch.setattr(wmod, "warn", lambda *a, **k: None)
    w = wmod.MainWindow()
    yield w, wmod, tmp_path
    w.close()


def test_ui_cross_currency_transfer_dialog(win, monkeypatch):
    w, wmod, tmp = win
    assert w.base() == "UZS"
    usd = w.db.save_account(None, name="USD", kind="cash", currency="USD", opening=0, color="#000", archived=0)
    w.db.set_rate("USD", Decimal("12800"), date.today())
    card = w.db.accounts()[1]["id"]
    dlg = wmod.TxDialog(w, None, "transfer")
    dlg.account.setCurrentIndex(dlg.account.findData(card))
    dlg.to_account.setCurrentIndex(dlg.to_account.findData(usd))
    dlg.amount.setText("1 280 000")
    dlg._save(False)                       # oyna ko'rsatilmagan holda ham kurs bo'yicha hisoblanadi
    t = w.db.transactions(kind="transfer")[0]
    assert t["amount"] == 128_000_000 and t["to_amount"] == 10_000
    assert w.db.balance(usd) == 10_000
    # ro'yxatni unicode yo'lga eksport
    out = tmp / "Экспорт o'quv"
    out.mkdir()
    for fmt in ("xlsx", "csv"):
        p = str(out / f"харажат.{fmt}")
        monkeypatch.setattr(wmod.QFileDialog, "getSaveFileName", lambda *a, **k: (p, ""))
        w.txp.export(fmt)
        assert os.path.getsize(p) > 100
