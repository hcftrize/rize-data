"""Telegram-safe text formatting helpers."""


def fmt_usd(v: float, decimals: int = 2) -> str:
    if v is None:
        return "—"
    neg = v < 0
    a = abs(v)
    if a >= 1_000_000_000:
        s = f"${a/1_000_000_000:.2f}B"
    elif a >= 1_000_000:
        s = f"${a/1_000_000:.2f}M"
    elif a >= 1_000:
        s = f"${a/1_000:.2f}K"
    else:
        s = f"${a:.{decimals}f}"
    return f"-{s}" if neg else s


def fmt_rize(v: float) -> str:
    if v is None:
        return "—"
    neg = v < 0
    a = abs(v)
    if a >= 1_000_000_000:
        s = f"{a/1_000_000_000:.2f}B RIZE"
    elif a >= 1_000_000:
        s = f"{a/1_000_000:.2f}M RIZE"
    elif a >= 1_000:
        s = f"{a/1_000:.2f}K RIZE"
    else:
        s = f"{a:.2f} RIZE"
    return f"-{s}" if neg else s


def fmt_num(v: float, decimals: int = 2) -> str:
    if v is None:
        return "—"
    neg = v < 0
    a = abs(v)
    if a >= 1_000_000_000:
        s = f"{a/1_000_000_000:.2f}B"
    elif a >= 1_000_000:
        s = f"{a/1_000_000:.2f}M"
    elif a >= 1_000:
        s = f"{a/1_000:.2f}K"
    else:
        s = f"{a:.{decimals}f}"
    return f"-{s}" if neg else s


def fmt_pct(v: float, show_plus: bool = True) -> str:
    if v is None:
        return "—"
    sign = "+" if v > 0 and show_plus else ""
    return f"{sign}{v:.2f}%"


def fmt_price(v: float) -> str:
    """Smart price formatting — 2 decimals >= $1, then 4 significant figures."""
    if v is None:
        return "—"
    if v >= 1000:
        return f"${v:,.2f}"
    if v >= 1:
        return f"${v:.2f}"
    if v >= 0.1:
        return f"${v:.4f}"
    if v >= 0.01:
        return f"${v:.4f}"
    if v >= 0.001:
        return f"${v:.6f}"
    if v >= 0.0001:
        return f"${v:.6f}"
    return f"${v:.8f}"


def fmt_sim_price(v: float) -> str:
    """Price formatting for simulations — 2 decimals for >= 0.01, else significant digits."""
    if v is None:
        return "—"
    if v >= 1000:
        return f"${v:,.0f}"
    if v >= 1:
        return f"${v:.2f}"
    if v >= 0.01:
        return f"${v:.2f}"
    if v >= 0.0001:
        return f"${v:.6f}"
    return f"${v:.8f}"


def pct_arrow(v: float) -> str:
    if v is None:
        return "—"
    emoji = "🟢" if v > 0 else "🔴" if v < 0 else "⚪"
    return f"{emoji} {fmt_pct(v)}"


def parse_amount(s: str) -> float | None:
    """Parse user amount: '1000000', '1M', '-1.3M' etc."""
    if not s:
        return None
    s = s.lower().replace("rize", "").replace(" ", "").strip()
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    if s.count(".") > 1:
        s = s.replace(".", "")
    s = s.replace(",", "")
    multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            try:
                val = float(s[:-1]) * mult
                return -val if neg else val
            except ValueError:
                return None
    try:
        val = float(s)
        return -val if neg else val
    except ValueError:
        return None


def escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def build_table(headers: list[str], rows: list[list[str]], col_widths: list[int] = None) -> str:
    if not col_widths:
        col_widths = [max(len(h), max((len(str(r[i])) for r in rows if i < len(r)), default=0)) + 1
                      for i, h in enumerate(headers)]
    sep = "─" * (sum(col_widths) + len(col_widths) - 1)
    header_row = " ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    data_rows = [" ".join(str(r[i] if i < len(r) else "").ljust(col_widths[i]) for i in range(len(headers))) for r in rows]
    return "\n".join([header_row, sep] + data_rows)
