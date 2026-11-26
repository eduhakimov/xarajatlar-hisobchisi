import os
import sqlite3
import sys
import tempfile
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from xarajatlar_hisobchisi import money
from xarajatlar_hisobchisi.db import DB, restore_from, validate_db_file

RATES = {"UZS": Decimal(1), "USD": Decimal("12800"), "RUB": Decimal("140")}


def test_parse_amount():
    assert money.parse_amount("1 250 000") == 125_000_000
    assert money.parse_amount("1250000") == 125_000_000
    assert money.parse_amount("1,250.50") == 125_050
    assert money.parse_amount("1250,5") == 125_050
    assert money.parse_amount("12.800") == 1_280_000
    assert money.parse_amount("12 800.00 so'm") == 1_280_000
    assert money.parse_amount("1.250.000") == 125_000_000
    assert money.parse_amount("0.99") == 99
    for bad in ("", "abc", ",", "-"):
        with pytest.raises(ValueError):
            money.parse_amount(bad)


def test_fmt_and_short():
    assert money.fmt(125_000_000, "UZS") == "1 250 000 so'm"
    assert money.fmt(-5_000_00, "UZS") == "-5 000 so'm"
    assert money.fmt(125_050, "USD") == "$1 250.50"
    assert money.fmt(1_000, "RUB", sign=True) == "+10.00 ₽"
    assert money.short(125_000_000) == "1.2 mln"
    assert money.short(85_000_000) == "850 ming"
    assert money.short(150_000, "USD") == "1.5k"


def test_convert():
    assert money.convert(100, "USD", "UZS", RATES) == 1_280_000      # $1 -> 12 800 so'm
    assert money.convert(1_280_000, "UZS", "USD", RATES) == 100
    assert money.convert(10_000, "RUB", "USD", RATES) == round(10_000 * 140 / 12800)
    assert money.convert(500, "UZS", "UZS", {}) == 500
    with pytest.raises(ValueError):
        money.convert(100, "USD", "UZS", {"UZS": Decimal(1)})


def test_next_date_month_end():
    assert money.next_date("monthly", date(2026, 1, 31), 31) == date(2026, 2, 28)
    assert money.next_date("monthly", date(2026, 2, 28), 31) == date(2026, 3, 31)
    assert money.next_date("monthly", date(2028, 1, 31), 31) == date(2028, 2, 29)
    assert money.next_date("weekly", date(2026, 1, 1)) == date(2026, 1, 8)
    assert money.next_date("yearly", date(2024, 2, 29), 29) == date(2025, 2, 28)
    assert money.next_date("monthly", date(2026, 12, 15), 15) == date(2027, 1, 15)
    with pytest.raises(ValueError):
        money.next_date("hourly", date(2026, 1, 1))


def test_months_and_budget_level():
    assert money.prev_months("2026-02", 3) == ["2025-12", "2026-01", "2026-02"]
    assert money.month_range("2026-02") == (date(2026, 2, 1), date(2026, 2, 28))
    assert money.budget_level(50, 100) == "ok"
    assert money.budget_level(85, 100) == "warn"
    assert money.budget_level(101, 100) == "over"
    assert money.budget_level(10, 0) == "ok"


def make_db():
    db = DB(Path(tempfile.mkdtemp()) / "x.db")
    names = {k: k for k in ("food", "transport", "utility", "home", "phone", "health", "edu", "clothes", "fun", "cafe",
                            "gift", "other_e", "salary", "scholar", "grant", "side", "other_i")}
    db.seed(names, {"cash": "Naqd", "card": "Humo"})
    return db


def test_balances_and_transfers():
    db = make_db()
    cash, card = [a["id"] for a in db.accounts()]
    usd = db.save_account(None, name="USD", kind="usd_cash", currency="USD", opening=10_000, color="#000", archived=0)
    cats = {c["key"]: c["id"] for c in db.categories()}
    db.save_account(cash, name="Naqd", kind="cash", currency="UZS", opening=1_000_000, color="#000", archived=0)
    db.add_tx(date(2026, 3, 1), "income", card, 5_000_000, cats["salary"])
    db.add_tx(date(2026, 3, 2), "expense", card, 1_200_000, cats["food"])
    db.add_tx(date(2026, 3, 3), "transfer", card, 1_000_000, None, "", cash)
    db.add_tx(date(2026, 3, 4), "transfer", card, 1_280_000, None, "", usd, 100)
    assert db.balance(card) == 5_000_000 - 1_200_000 - 1_000_000 - 1_280_000
    assert db.balance(cash) == 2_000_000
    assert db.balance(usd) == 10_100
    assert db.balance(card, until=date(2026, 3, 1)) == 5_000_000
    db.set_rate("USD", Decimal("12800"), date(2026, 3, 1))
    total = db.total_balance("UZS")
    assert total == db.balance(card) + db.balance(cash) + 10_100 * 12800
    with pytest.raises(ValueError):
        db.add_tx(date(2026, 3, 5), "transfer", card, 100, None, "", card)
    with pytest.raises(ValueError):
        db.add_tx(date(2026, 3, 5), "expense", card, 0, cats["food"])


def test_month_totals_categories_budget():
    db = make_db()
    card = db.accounts()[1]["id"]
    usd = db.save_account(None, name="USD", kind="usd_cash", currency="USD", opening=0, color="#000", archived=0)
    db.set_rate("USD", Decimal("10000"), date(2026, 1, 1))
    cats = {c["key"]: c["id"] for c in db.categories()}
    db.add_tx(date(2026, 4, 2), "income", card, 900_000, cats["salary"])
    db.add_tx(date(2026, 4, 3), "expense", card, 300_000, cats["food"])
    db.add_tx(date(2026, 4, 4), "expense", usd, 1_000, cats["edu"])          # $10 -> 100 000 so'm
    db.add_tx(date(2026, 5, 1), "expense", card, 50_000, cats["food"])
    assert db.month_totals("2026-04", "UZS") == (900_000, 300_000 + 10_000_000)
    by = db.by_category(date(2026, 4, 1), date(2026, 4, 30), "expense", "UZS")
    assert [c["key"] for c, _ in by] == ["edu", "food"]
    db.set_budget("2026-04", cats["food"], 250_000)
    use = db.budget_usage("2026-04", "UZS")
    assert use[0][1] == 300_000 and use[0][2] == 250_000
    assert db.copy_budgets("2026-04", "2026-05") == 1
    assert db.budgets("2026-05") == {cats["food"]: 250_000}
    db.set_budget("2026-05", cats["food"], 0)
    assert db.budgets("2026-05") == {}
    txs = db.transactions(date(2026, 4, 1), date(2026, 4, 30), text="")
    assert len(txs) == 3


def test_debts():
    db = make_db()
    did = db.save_debt(None, "lent", "Ali", 1_000_000, "UZS", date(2026, 1, 1), None, "")
    db.add_payment(did, 400_000, date(2026, 1, 5))
    assert db.debt_remaining(did) == 600_000
    db.add_payment(did, 600_000, date(2026, 1, 9))
    assert db.debt_remaining(did) == 0
    assert db.debts(False) == []
    assert db.debts(True)[0]["closed"] == 1
    with pytest.raises(ValueError):
        db.add_payment(did, 0, date(2026, 1, 9))


def test_recurring_generation():
    db = make_db()
    card = db.accounts()[1]["id"]
    cats = {c["key"]: c["id"] for c in db.categories()}
    rid = db.save_recurring(None, "expense", card, cats["home"], 2_500_000, "Ijara", "monthly", date(2026, 1, 31))
    due = db.due_recurring(date(2026, 4, 15))
    assert [d for _, d in due] == [date(2026, 1, 31), date(2026, 2, 28), date(2026, 3, 31)]
    assert db.run_recurring(date(2026, 4, 15)) == 3
    assert db.run_recurring(date(2026, 4, 15)) == 0
    r = [x for x in db.recurring() if x["id"] == rid][0]
    assert r["next_date"] == "2026-04-30"
    assert len(db.transactions(kind="expense")) == 3


def test_category_delete_moves_transactions():
    db = make_db()
    card = db.accounts()[1]["id"]
    cats = {c["key"]: c["id"] for c in db.categories()}
    db.add_tx(date(2026, 1, 2), "expense", card, 1000, cats["fun"])
    db.delete_category(cats["fun"], cats["other_e"])
    assert db.transactions()[0]["category_id"] == cats["other_e"]


def test_backup_restore_roundtrip(tmp_path):
    db = make_db()
    card = db.accounts()[1]["id"]
    db.add_tx(date(2026, 1, 2), "income", card, 777, None)
    bk = tmp_path / "b.db"
    db.backup_to(str(bk))
    assert validate_db_file(str(bk))
    db.add_tx(date(2026, 1, 3), "income", card, 1, None)
    path = db.path
    safety = restore_from(db, str(bk))
    assert safety.exists()
    db2 = DB(path)
    assert len(db2.transactions()) == 1
    bad = tmp_path / "bad.db"
    bad.write_bytes(b"not a db")
    assert not validate_db_file(str(bad))
    other = tmp_path / "other.db"
    sqlite3.connect(str(other)).execute("CREATE TABLE x(a)").connection.close()
    assert not validate_db_file(str(other))
    with pytest.raises(ValueError):
        restore_from(db2, str(bad))


def test_export(tmp_path):
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from xarajatlar_hisobchisi import window
    db = make_db()
    card = db.accounts()[1]["id"]
    cats = {c["key"]: c["id"] for c in db.categories()}
    db.add_tx(date(2026, 1, 2), "expense", card, 12_345_600, cats["food"], "bozor")
    rows = db.transactions()
    window.export_transactions(rows, str(tmp_path / "a.xlsx"), "xlsx")
    window.export_transactions(rows, str(tmp_path / "a.csv"), "csv")
    from openpyxl import load_workbook
    ws = load_workbook(tmp_path / "a.xlsx").active
    assert ws.cell(row=4, column=5).value == -123456.0
    txt = (tmp_path / "a.csv").read_text(encoding="utf-8-sig")
    assert "-123456,0" in txt and "bozor" in txt


def test_dialogs_open():
    from PySide6.QtWidgets import QApplication
    QApplication.instance() or QApplication([])
    from uzkit import app as appmod
    from uzkit.settings import Settings
    appmod.META = appmod.load_meta()
    appmod.SETTINGS = Settings(appmod.META["slug"] + "_test")
    from xarajatlar_hisobchisi import window
    w = window.MainWindow()
    window.load_demo(w.db)
    w.data_changed()
    for k in ("expense", "income", "transfer"):
        d = window.TxDialog(w, None, k)
        d.amount.setText("125 000")
        assert d.amount.cents() == 12_500_000
        d.close()
    t = w.db.transactions(kind="transfer")[0]
    window.TxDialog(w, t).close()
    window.CategoryDialog(w).close()
    window.AccountDialog(w).close()
    window.DebtDialog(w).close()
    window.RecurringDialog(w).close()
    for i in range(7):
        w.set_page(i)
    w.close()
