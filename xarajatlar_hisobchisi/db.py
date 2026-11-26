"""SQLite: hisoblar, toifalar, operatsiyalar, kurslar, byudjet, qarzlar, takroriy to'lovlar."""
import shutil
import sqlite3
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from . import money

SCHEMA = """
CREATE TABLE IF NOT EXISTS accounts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, kind TEXT DEFAULT 'cash',
    currency TEXT DEFAULT 'UZS', opening INTEGER DEFAULT 0, color TEXT DEFAULT '#12805c',
    archived INTEGER DEFAULT 0, pos INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL, kind TEXT NOT NULL,
    color TEXT DEFAULT '#868e96', icon TEXT DEFAULT 'cat_other', key TEXT, pos INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS transactions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, kind TEXT NOT NULL,
    account_id INTEGER NOT NULL REFERENCES accounts(id), amount INTEGER NOT NULL,
    category_id INTEGER REFERENCES categories(id), note TEXT DEFAULT '',
    to_account_id INTEGER REFERENCES accounts(id), to_amount INTEGER, recurring_id INTEGER,
    created TEXT);
CREATE INDEX IF NOT EXISTS ix_tx_date ON transactions(date);
CREATE TABLE IF NOT EXISTS rates (
    id INTEGER PRIMARY KEY AUTOINCREMENT, date TEXT NOT NULL, currency TEXT NOT NULL, rate TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS budgets (
    month TEXT NOT NULL, category_id INTEGER NOT NULL REFERENCES categories(id) ON DELETE CASCADE,
    amount INTEGER NOT NULL, PRIMARY KEY (month, category_id));
CREATE TABLE IF NOT EXISTS debts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, direction TEXT NOT NULL, person TEXT NOT NULL,
    amount INTEGER NOT NULL, currency TEXT DEFAULT 'UZS', date TEXT NOT NULL, due TEXT, note TEXT DEFAULT '',
    closed INTEGER DEFAULT 0);
CREATE TABLE IF NOT EXISTS debt_payments (
    id INTEGER PRIMARY KEY AUTOINCREMENT, debt_id INTEGER NOT NULL REFERENCES debts(id) ON DELETE CASCADE,
    date TEXT NOT NULL, amount INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS recurring (
    id INTEGER PRIMARY KEY AUTOINCREMENT, kind TEXT NOT NULL, account_id INTEGER NOT NULL REFERENCES accounts(id),
    category_id INTEGER REFERENCES categories(id), amount INTEGER NOT NULL, note TEXT DEFAULT '',
    freq TEXT NOT NULL, next_date TEXT NOT NULL, anchor_day INTEGER, active INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT);
"""

# kalit, belgisi, rangi
DEFAULT_EXPENSE = [("food", "cat_food", "#e8590c"), ("transport", "cat_transport", "#1c7ed6"),
                   ("utility", "cat_utility", "#f59f00"), ("home", "cat_home", "#7048e8"),
                   ("phone", "cat_phone", "#0c8599"), ("health", "cat_health", "#e03131"),
                   ("edu", "cat_edu", "#2f9e44"), ("clothes", "cat_clothes", "#d6336c"),
                   ("fun", "cat_fun", "#9c36b5"), ("cafe", "cat_cafe", "#a0522d"), ("gift", "cat_gift", "#c2255c"),
                   ("other_e", "cat_other", "#868e96")]
DEFAULT_INCOME = [("salary", "cat_salary", "#12805c"), ("scholar", "cat_scholar", "#1971c2"),
                  ("grant", "cat_grant", "#f08c00"), ("side", "cat_side", "#5c940d"), ("other_i", "cat_other", "#868e96")]


class DB:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(str(self.path))
        self.con.row_factory = sqlite3.Row
        self.con.execute("PRAGMA foreign_keys = ON")
        self.con.executescript(SCHEMA)
        self.con.commit()

    def close(self):
        self.con.close()

    def get_meta(self, k, default=None):
        r = self.con.execute("SELECT v FROM meta WHERE k=?", (k,)).fetchone()
        return r["v"] if r else default

    def set_meta(self, k, v):
        self.con.execute("INSERT OR REPLACE INTO meta(k, v) VALUES(?, ?)", (k, str(v)))
        self.con.commit()

    # ------------------------------------------------------------------ boshlang'ich ma'lumot
    def seed(self, names: Dict[str, str], account_names: Dict[str, str]):
        """Birinchi ishga tushirish: standart toifalar va hisoblar (nomlar joriy tilda)."""
        if self.get_meta("seeded"):
            return
        for i, (k, ic, col) in enumerate(DEFAULT_EXPENSE):
            self.con.execute("INSERT INTO categories(name, kind, color, icon, key, pos) VALUES(?,?,?,?,?,?)",
                             (names[k], "expense", col, ic, k, i))
        for i, (k, ic, col) in enumerate(DEFAULT_INCOME):
            self.con.execute("INSERT INTO categories(name, kind, color, icon, key, pos) VALUES(?,?,?,?,?,?)",
                             (names[k], "income", col, ic, k, i))
        for i, (k, kind, cur, col) in enumerate((("cash", "cash", "UZS", "#12805c"),
                                                  ("card", "humo", "UZS", "#1c7ed6"))):
            self.con.execute("INSERT INTO accounts(name, kind, currency, opening, color, pos) VALUES(?,?,?,?,?,?)",
                             (account_names[k], kind, cur, 0, col, i))
        self.set_meta("seeded", "1")
        self.con.commit()

    # ------------------------------------------------------------------ hisoblar
    def accounts(self, include_archived=False) -> List[sqlite3.Row]:
        q = "SELECT * FROM accounts" + ("" if include_archived else " WHERE archived=0") + " ORDER BY pos, id"
        return self.con.execute(q).fetchall()

    def account(self, aid):
        return self.con.execute("SELECT * FROM accounts WHERE id=?", (aid,)).fetchone()

    def save_account(self, aid: Optional[int], **kw) -> int:
        cols = ["name", "kind", "currency", "opening", "color", "archived"]
        vals = [kw.get(c) for c in cols]
        if aid:
            self.con.execute(f"UPDATE accounts SET {', '.join(c + '=?' for c in cols)} WHERE id=?", (*vals, aid))
        else:
            pos = self.con.execute("SELECT COALESCE(MAX(pos), 0) + 1 FROM accounts").fetchone()[0]
            aid = self.con.execute(f"INSERT INTO accounts({', '.join(cols)}, pos) VALUES(?,?,?,?,?,?,?)",
                                   (*vals, pos)).lastrowid
        self.con.commit()
        return aid

    def account_used(self, aid) -> bool:
        return bool(self.con.execute("SELECT 1 FROM transactions WHERE account_id=? OR to_account_id=? LIMIT 1",
                                     (aid, aid)).fetchone())

    def delete_account(self, aid):
        self.con.execute("DELETE FROM recurring WHERE account_id=?", (aid,))
        self.con.execute("DELETE FROM accounts WHERE id=?", (aid,))
        self.con.commit()

    def balance(self, aid: int, until: date = None) -> int:
        a = self.account(aid)
        cond = " AND date<=?" if until else ""
        args = (until.isoformat(),) if until else ()
        q = lambda sql, *p: self.con.execute(sql + cond, (*p, *args)).fetchone()[0] or 0  # noqa: E731
        inc = q("SELECT SUM(amount) FROM transactions WHERE account_id=? AND kind='income'", aid)
        exp = q("SELECT SUM(amount) FROM transactions WHERE account_id=? AND kind='expense'", aid)
        out = q("SELECT SUM(amount) FROM transactions WHERE account_id=? AND kind='transfer'", aid)
        tin = q("SELECT SUM(to_amount) FROM transactions WHERE to_account_id=? AND kind='transfer'", aid)
        return a["opening"] + inc - exp - out + tin

    def total_balance(self, base: str) -> int:
        rates = self.current_rates()
        total = 0
        for a in self.accounts():
            try:
                total += money.convert(self.balance(a["id"]), a["currency"], base, rates)
            except ValueError:
                pass
        return total

    # ------------------------------------------------------------------ toifalar
    def categories(self, kind: Optional[str] = None) -> List[sqlite3.Row]:
        if kind:
            return self.con.execute("SELECT * FROM categories WHERE kind=? ORDER BY pos, id", (kind,)).fetchall()
        return self.con.execute("SELECT * FROM categories ORDER BY kind, pos, id").fetchall()

    def category(self, cid):
        return self.con.execute("SELECT * FROM categories WHERE id=?", (cid,)).fetchone()

    def save_category(self, cid: Optional[int], name: str, kind: str, color: str, icon: str) -> int:
        if cid:
            self.con.execute("UPDATE categories SET name=?, kind=?, color=?, icon=? WHERE id=?",
                             (name, kind, color, icon, cid))
        else:
            pos = self.con.execute("SELECT COALESCE(MAX(pos), 0) + 1 FROM categories").fetchone()[0]
            cid = self.con.execute("INSERT INTO categories(name, kind, color, icon, pos) VALUES(?,?,?,?,?)",
                                   (name, kind, color, icon, pos)).lastrowid
        self.con.commit()
        return cid

    def delete_category(self, cid: int, move_to: Optional[int] = None):
        self.con.execute("UPDATE transactions SET category_id=? WHERE category_id=?", (move_to, cid))
        self.con.execute("UPDATE recurring SET category_id=? WHERE category_id=?", (move_to, cid))
        self.con.execute("DELETE FROM budgets WHERE category_id=?", (cid,))
        self.con.execute("DELETE FROM categories WHERE id=?", (cid,))
        self.con.commit()

    def category_used(self, cid) -> int:
        return self.con.execute("SELECT COUNT(*) FROM transactions WHERE category_id=?", (cid,)).fetchone()[0]

    # ------------------------------------------------------------------ operatsiyalar
    def add_tx(self, d: date, kind: str, account_id: int, amount: int, category_id=None, note="",
               to_account_id=None, to_amount=None, recurring_id=None) -> int:
        if amount <= 0:
            raise ValueError("amount")
        if kind == "transfer" and (not to_account_id or to_account_id == account_id):
            raise ValueError("transfer")
        tid = self.con.execute(
            "INSERT INTO transactions(date, kind, account_id, amount, category_id, note, to_account_id, to_amount, "
            "recurring_id, created) VALUES(?,?,?,?,?,?,?,?,?,?)",
            (d.isoformat(), kind, account_id, amount, None if kind == "transfer" else category_id, note,
             to_account_id if kind == "transfer" else None,
             (to_amount if to_amount else amount) if kind == "transfer" else None, recurring_id,
             datetime.now().isoformat(timespec="seconds"))).lastrowid
        self.con.commit()
        return tid

    def update_tx(self, tid: int, d: date, kind: str, account_id: int, amount: int, category_id=None, note="",
                  to_account_id=None, to_amount=None):
        if amount <= 0:
            raise ValueError("amount")
        self.con.execute(
            "UPDATE transactions SET date=?, kind=?, account_id=?, amount=?, category_id=?, note=?, to_account_id=?, "
            "to_amount=? WHERE id=?",
            (d.isoformat(), kind, account_id, amount, None if kind == "transfer" else category_id, note,
             to_account_id if kind == "transfer" else None,
             (to_amount if to_amount else amount) if kind == "transfer" else None, tid))
        self.con.commit()

    def delete_tx(self, tid: int):
        self.con.execute("DELETE FROM transactions WHERE id=?", (tid,))
        self.con.commit()

    def tx(self, tid: int):
        return self.con.execute("SELECT * FROM transactions WHERE id=?", (tid,)).fetchone()

    def transactions(self, start: date = None, end: date = None, account_id=None, category_id=None, kind=None,
                     text: str = "", limit: int = None) -> List[sqlite3.Row]:
        q = ("SELECT t.*, a.name AS account_name, a.currency AS currency, c.name AS category_name, c.color AS "
             "category_color, c.icon AS category_icon, ta.name AS to_account_name, ta.currency AS to_currency "
             "FROM transactions t JOIN accounts a ON a.id=t.account_id LEFT JOIN categories c ON c.id=t.category_id "
             "LEFT JOIN accounts ta ON ta.id=t.to_account_id WHERE 1=1")
        args = []
        if start:
            q += " AND t.date>=?"
            args.append(start.isoformat())
        if end:
            q += " AND t.date<=?"
            args.append(end.isoformat())
        if account_id:
            q += " AND (t.account_id=? OR t.to_account_id=?)"
            args += [account_id, account_id]
        if category_id:
            q += " AND t.category_id=?"
            args.append(category_id)
        if kind:
            q += " AND t.kind=?"
            args.append(kind)
        if text:
            q += " AND (t.note LIKE ? OR c.name LIKE ? OR a.name LIKE ?)"
            args += [f"%{text}%"] * 3
        q += " ORDER BY t.date DESC, t.id DESC"
        if limit:
            q += f" LIMIT {int(limit)}"
        return self.con.execute(q, args).fetchall()

    # ------------------------------------------------------------------ kurslar
    def set_rate(self, currency: str, rate: Decimal, d: date):
        self.con.execute("DELETE FROM rates WHERE currency=? AND date=?", (currency, d.isoformat()))
        self.con.execute("INSERT INTO rates(date, currency, rate) VALUES(?,?,?)", (d.isoformat(), currency, str(rate)))
        self.con.commit()

    def current_rates(self) -> Dict[str, Decimal]:
        out = {"UZS": Decimal(1)}
        for cur in ("USD", "RUB"):
            r = self.con.execute("SELECT rate FROM rates WHERE currency=? ORDER BY date DESC, id DESC LIMIT 1",
                                 (cur,)).fetchone()
            if r:
                out[cur] = Decimal(r["rate"])
        return out

    def rate_history(self) -> List[sqlite3.Row]:
        return self.con.execute("SELECT * FROM rates ORDER BY date DESC, id DESC LIMIT 200").fetchall()

    def delete_rate(self, rid):
        self.con.execute("DELETE FROM rates WHERE id=?", (rid,))
        self.con.commit()

    # ------------------------------------------------------------------ hisob-kitoblar
    def _to_base(self, row, base, rates) -> int:
        try:
            return money.convert(row["amount"], row["currency"], base, rates)
        except ValueError:
            return 0

    def month_totals(self, key: str, base: str) -> Tuple[int, int]:
        s, e = money.month_range(key)
        rates = self.current_rates()
        inc = exp = 0
        for t in self.transactions(s, e):
            if t["kind"] == "income":
                inc += self._to_base(t, base, rates)
            elif t["kind"] == "expense":
                exp += self._to_base(t, base, rates)
        return inc, exp

    def by_category(self, start: date, end: date, kind: str, base: str) -> List[Tuple[sqlite3.Row, int]]:
        rates = self.current_rates()
        sums: Dict[int, int] = {}
        for t in self.transactions(start, end, kind=kind):
            sums[t["category_id"] or 0] = sums.get(t["category_id"] or 0, 0) + self._to_base(t, base, rates)
        out = []
        for cid, v in sums.items():
            out.append((self.category(cid) if cid else None, v))
        return sorted(out, key=lambda x: -x[1])

    # ------------------------------------------------------------------ byudjet
    def budgets(self, key: str) -> Dict[int, int]:
        return {r["category_id"]: r["amount"] for r in
                self.con.execute("SELECT * FROM budgets WHERE month=?", (key,))}

    def set_budget(self, key: str, cid: int, amount: int):
        if amount <= 0:
            self.con.execute("DELETE FROM budgets WHERE month=? AND category_id=?", (key, cid))
        else:
            self.con.execute("INSERT OR REPLACE INTO budgets(month, category_id, amount) VALUES(?,?,?)",
                             (key, cid, amount))
        self.con.commit()

    def copy_budgets(self, src: str, dst: str) -> int:
        n = 0
        for cid, amt in self.budgets(src).items():
            self.con.execute("INSERT OR REPLACE INTO budgets(month, category_id, amount) VALUES(?,?,?)", (dst, cid, amt))
            n += 1
        self.con.commit()
        return n

    def budget_usage(self, key: str, base: str) -> List[Tuple[sqlite3.Row, int, int]]:
        """[(toifa, sarflangan, limit)] — limiti bor xarajat toifalari."""
        s, e = money.month_range(key)
        spent = {c["id"] if c else 0: v for c, v in self.by_category(s, e, "expense", base)}
        out = []
        for cid, limit in self.budgets(key).items():
            c = self.category(cid)
            if c:
                out.append((c, spent.get(cid, 0), limit))
        return sorted(out, key=lambda x: -(x[1] / x[2] if x[2] else 0))

    # ------------------------------------------------------------------ qarzlar
    def debts(self, include_closed=True) -> List[sqlite3.Row]:
        q = "SELECT d.*, COALESCE((SELECT SUM(amount) FROM debt_payments p WHERE p.debt_id=d.id), 0) AS paid FROM debts d"
        if not include_closed:
            q += " WHERE closed=0"
        return self.con.execute(q + " ORDER BY closed, COALESCE(due, '9999'), date").fetchall()

    def save_debt(self, did, direction, person, amount, currency, d: date, due: Optional[date], note) -> int:
        vals = (direction, person, amount, currency, d.isoformat(), due.isoformat() if due else None, note)
        if did:
            self.con.execute("UPDATE debts SET direction=?, person=?, amount=?, currency=?, date=?, due=?, note=? "
                             "WHERE id=?", (*vals, did))
        else:
            did = self.con.execute("INSERT INTO debts(direction, person, amount, currency, date, due, note) "
                                   "VALUES(?,?,?,?,?,?,?)", vals).lastrowid
        self.con.commit()
        self._auto_close(did)
        return did

    def add_payment(self, did: int, amount: int, d: date):
        if amount <= 0:
            raise ValueError("amount")
        self.con.execute("INSERT INTO debt_payments(debt_id, date, amount) VALUES(?,?,?)", (did, d.isoformat(), amount))
        self.con.commit()
        self._auto_close(did)

    def debt_remaining(self, did: int) -> int:
        r = self.con.execute("SELECT amount, COALESCE((SELECT SUM(amount) FROM debt_payments WHERE debt_id=?), 0) "
                             "AS paid FROM debts WHERE id=?", (did, did)).fetchone()
        return max(0, r["amount"] - r["paid"]) if r else 0

    def _auto_close(self, did):
        self.con.execute("UPDATE debts SET closed=? WHERE id=?", (1 if self.debt_remaining(did) == 0 else 0, did))
        self.con.commit()

    def delete_debt(self, did):
        self.con.execute("DELETE FROM debts WHERE id=?", (did,))
        self.con.commit()

    def payments(self, did) -> List[sqlite3.Row]:
        return self.con.execute("SELECT * FROM debt_payments WHERE debt_id=? ORDER BY date", (did,)).fetchall()

    # ------------------------------------------------------------------ takroriy
    def recurring(self) -> List[sqlite3.Row]:
        return self.con.execute(
            "SELECT r.*, a.name AS account_name, a.currency AS currency, c.name AS category_name, c.icon AS "
            "category_icon, c.color AS category_color FROM recurring r JOIN accounts a ON a.id=r.account_id "
            "LEFT JOIN categories c ON c.id=r.category_id ORDER BY r.active DESC, r.next_date").fetchall()

    def save_recurring(self, rid, kind, account_id, category_id, amount, note, freq, next_d: date, active=True) -> int:
        vals = (kind, account_id, category_id, amount, note, freq, next_d.isoformat(), next_d.day, 1 if active else 0)
        if rid:
            self.con.execute("UPDATE recurring SET kind=?, account_id=?, category_id=?, amount=?, note=?, freq=?, "
                             "next_date=?, anchor_day=?, active=? WHERE id=?", (*vals, rid))
        else:
            rid = self.con.execute("INSERT INTO recurring(kind, account_id, category_id, amount, note, freq, "
                                   "next_date, anchor_day, active) VALUES(?,?,?,?,?,?,?,?,?)", vals).lastrowid
        self.con.commit()
        return rid

    def delete_recurring(self, rid):
        self.con.execute("DELETE FROM recurring WHERE id=?", (rid,))
        self.con.commit()

    def due_recurring(self, today: date) -> List[Tuple[sqlite3.Row, date]]:
        """Bugungacha bajarilishi kerak bo'lgan (hali yaratilmagan) to'lovlar ro'yxati."""
        out = []
        for r in self.con.execute("SELECT * FROM recurring WHERE active=1"):
            d = date.fromisoformat(r["next_date"])
            n = 0
            while d <= today and n < 400:
                out.append((r, d))
                d = money.next_date(r["freq"], d, r["anchor_day"])
                n += 1
        return out

    def run_recurring(self, today: date) -> int:
        """Muddati kelgan takroriy to'lovlarni operatsiyaga aylantiradi."""
        n = 0
        for r in self.con.execute("SELECT * FROM recurring WHERE active=1").fetchall():
            d = date.fromisoformat(r["next_date"])
            guard = 0
            while d <= today and guard < 400:
                self.con.execute(
                    "INSERT INTO transactions(date, kind, account_id, amount, category_id, note, recurring_id, created) "
                    "VALUES(?,?,?,?,?,?,?,?)", (d.isoformat(), r["kind"], r["account_id"], r["amount"],
                                                r["category_id"], r["note"], r["id"],
                                                datetime.now().isoformat(timespec="seconds")))
                d = money.next_date(r["freq"], d, r["anchor_day"])
                n += 1
                guard += 1
            self.con.execute("UPDATE recurring SET next_date=? WHERE id=?", (d.isoformat(), r["id"]))
        self.con.commit()
        return n

    # ------------------------------------------------------------------ zaxira
    def backup_to(self, dest: str):
        """Izchil nusxa (sqlite backup API)."""
        dst = sqlite3.connect(dest)
        try:
            self.con.backup(dst)
        finally:
            dst.close()


def validate_db_file(path: str) -> bool:
    try:
        con = sqlite3.connect(f"file:{Path(path).as_posix()}?mode=ro", uri=True)
        try:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            ok = con.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            con.close()
        return ok and {"accounts", "transactions", "categories"} <= tables
    except Exception:
        return False


def restore_from(db: "DB", src: str) -> Path:
    """Tekshirib, joriy bazani almashtiradi. Avtomatik xavfsizlik nusxasi yo'lini qaytaradi. db yopiladi."""
    if not validate_db_file(src):
        raise ValueError("invalid backup")
    target = db.path
    safety = target.with_name(f"{target.stem}_before_restore_{datetime.now():%Y%m%d_%H%M%S}.db")
    db.backup_to(str(safety))
    db.close()
    tmp = target.with_suffix(".restore.tmp")
    shutil.copy2(src, tmp)
    tmp.replace(target)
    return safety
