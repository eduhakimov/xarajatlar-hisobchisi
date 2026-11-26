"""Pul bilan ishlash (interfeyssiz): summalar butun "tiyin/sent"da saqlanadi (1 so'm = 100)."""
import calendar
import re
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Dict, Optional

CURRENCIES = ["UZS", "USD", "RUB"]
SYMBOLS = {"UZS": "so'm", "USD": "$", "RUB": "₽"}
DECIMALS = {"UZS": 0, "USD": 2, "RUB": 2}
# Qisqa birliklar (interfeys tili bo'yicha almashtiriladi): mlrd, mln, ming
SHORT_UNITS = {"bn": "mlrd", "m": "mln", "k": "ming"}


def parse_amount(text: str) -> int:
    """'1 250 000', '1,250.50', '1250,5', '12 800.00' -> butun minor birliklar (x100). Xato bo'lsa ValueError."""
    s = (text or "").strip().replace(" ", " ").replace("'", "").replace("_", "")
    s = re.sub(r"[^\d.,\s-]", "", s).strip()
    s = s.replace(" ", "")
    if not s or s in ("-", ".", ","):
        raise ValueError("empty")
    if "," in s and "." in s:
        # oxirgi uchragan belgi — kasr ajratgich
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        if len(parts) == 2 and len(parts[1]) in (1, 2):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif s.count(".") > 1:
        s = s.replace(".", "")
    elif "." in s and len(s.split(".")[1]) == 3 and len(s.split(".")[0]) <= 3:
        s = s.replace(".", "")            # 12.800 -> 12800 (minglik ajratgich)
    try:
        d = Decimal(s)
    except InvalidOperation:
        raise ValueError(text)
    return int((d * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def group(n: int, sep: str = " ") -> str:
    s = f"{abs(n):,}".replace(",", sep)
    return ("-" if n < 0 else "") + s


def fmt(cents: int, currency: str = "UZS", sign: bool = False, symbol: bool = True) -> str:
    dec = DECIMALS.get(currency, 2)
    neg = cents < 0
    v = abs(cents)
    whole, frac = divmod(v, 100)
    if dec == 0:
        whole = (v + 50) // 100
        body = group(whole)
    else:
        body = f"{group(whole)}.{frac:02d}"
    pre = "-" if neg else ("+" if sign and cents > 0 else "")
    if not symbol:
        return pre + body
    sym = SYMBOLS.get(currency, currency)
    if currency == "USD":
        return f"{pre}${body}"
    return f"{pre}{body} {sym}"


def short(cents: int, currency: str = "UZS") -> str:
    """Grafiklar uchun qisqa: 1,2 mln / 850 ming / $1.2k."""
    v = cents / 100
    a = abs(v)
    if currency == "UZS":
        u = SHORT_UNITS
        if a >= 1e9:
            return f"{v / 1e9:.1f} {u['bn']}".replace(".0 ", " ")
        if a >= 1e6:
            return f"{v / 1e6:.1f} {u['m']}".replace(".0 ", " ")
        if a >= 1e3:
            return f"{v / 1e3:.0f} {u['k']}"
        return f"{v:.0f}"
    if a >= 1e6:
        return f"{v / 1e6:.1f}M"
    if a >= 1e3:
        return f"{v / 1e3:.1f}k"
    return f"{v:.0f}"


def convert(cents: int, src: str, dst: str, rates: Dict[str, Decimal]) -> int:
    """rates: valyuta -> 1 birligi necha so'm (UZS = 1). Natija ham minor birliklarda."""
    if src == dst:
        return cents
    r_src = Decimal(1) if src == "UZS" else Decimal(rates.get(src) or 0)
    r_dst = Decimal(1) if dst == "UZS" else Decimal(rates.get(dst) or 0)
    if r_src <= 0 or r_dst <= 0:
        raise ValueError(f"no rate for {src}->{dst}")
    v = Decimal(cents) * r_src / r_dst
    return int(v.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------- sanalar
def add_months(d: date, n: int, anchor_day: Optional[int] = None) -> date:
    """Oy qo'shish; oy oxiri muammosi: 31-yanvar + 1 oy = 28/29-fevral, keyin anchor bo'yicha 31-mart."""
    y, m = divmod(d.month - 1 + n, 12)
    y += d.year
    m += 1
    day = anchor_day or d.day
    return date(y, m, min(day, calendar.monthrange(y, m)[1]))


def next_date(freq: str, current: date, anchor_day: Optional[int] = None) -> date:
    if freq == "daily":
        return current + timedelta(days=1)
    if freq == "weekly":
        return current + timedelta(days=7)
    if freq == "monthly":
        return add_months(current, 1, anchor_day)
    if freq == "yearly":
        return add_months(current, 12, anchor_day)
    raise ValueError(freq)


def month_key(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def month_range(key: str):
    y, m = map(int, key.split("-"))
    return date(y, m, 1), date(y, m, calendar.monthrange(y, m)[1])


def prev_months(key: str, n: int):
    """key dan oldingi n ta oy (key ham kiradi), eskisidan yangisiga."""
    y, m = map(int, key.split("-"))
    out = []
    for i in range(n - 1, -1, -1):
        d = add_months(date(y, m, 1), -i)
        out.append(month_key(d))
    return out


def budget_level(spent: int, limit: int) -> str:
    """'ok' (< 80%), 'warn' (80–100%), 'over' (> 100%)."""
    if limit <= 0:
        return "ok"
    r = spent / limit
    if r > 1:
        return "over"
    if r >= 0.8:
        return "warn"
    return "ok"
