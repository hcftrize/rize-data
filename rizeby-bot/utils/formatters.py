"""Telegram-safe text formatting helpers."""


def fmt_usd(v: float, decimals: int = 2) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000_000:
        return f"${v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"${v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"${v/1_000:.2f}K"
    return f"${v:.{decimals}f}"


def fmt_rize(v: float) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}B RIZE"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f}M RIZE"
    if v >= 1_000:
        return f"{v/1_000:.2f}K RIZE"
    return f"{v:.2f} RIZE"


def fmt_num(v: float, decimals: int = 2) -> str:
    if v is None:
        return "—"
    if v >= 1_000_000_000:
        return f"{v/1_000_000_000:.2f}B"
    if v >= 1_000_000:
        return f"{v/1_000_000:.2f}M"
    if v >= 1_000:
        return f"{v/1_000:.2f}K"
    return f"{v:.{decimals}f}"


def fmt_pct(v: float, show_plus: bool = True) -> str:
    if v is None:
        return "—"
    sign = "+" if v > 0 and show_plus else ""
    return f"{sign}{v:.2f}%"


def fmt_price(v: float) -> str:
    """Smart price formatting — keeps significant digits."""
    if v is None:
        return "—"
    if v >= 1000:
        return f"${v:,.2f}"
    if v >= 1:
        return f"${v:.4f}"
    if v >= 0.01:
        return f"${v:.6f}"
    return f"${v:.8f}"


def pct_arrow(v: float) -> str:
    if v is None:
        return "—"
    emoji = "🟢" if v > 0 else "🔴" if v < 0 else "⚪"
    return f"{emoji} {fmt_pct(v)}"


def parse_amount(s: str) -> float | None:
    """Parse user amount: '1000000', '1 000 000', '1.000.000', '1,000,000', '1M', '1m rize'."""
    if not s:
        return None
    s = s.lower().replace("rize", "").replace(" ", "").strip()
    # Handle European dot-as-thousand: 1.000.000
    if s.count(".") > 1:
        s = s.replace(".", "")
    s = s.replace(",", "")
    # Handle shorthand
    multipliers = {"k": 1_000, "m": 1_000_000, "b": 1_000_000_000}
    for suffix, mult in multipliers.items():
        if s.endswith(suffix):
            try:
                return float(s[:-1]) * mult
            except ValueError:
                return None
    try:
        return float(s)
    except ValueError:
        return None


def escape_md(text: str) -> str:
    """Escape MarkdownV2 special chars."""
    special = r"\_*[]()~`>#+-=|{}.!"
    return "".join(f"\\{c}" if c in special else c for c in str(text))


def build_table(headers: list[str], rows: list[list[str]], col_widths: list[int] = None) -> str:
    """Build a fixed-width monospace table for Telegram (use inside code block)."""
    if not col_widths:
        col_widths = [max(len(h), max((len(str(r[i])) for r in rows if i < len(r)), default=0)) + 1
                      for i, h in enumerate(headers)]
    sep = "─" * (sum(col_widths) + len(col_widths) - 1)
    header_row = " ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    data_rows = [" ".join(str(r[i] if i < len(r) else "").ljust(col_widths[i]) for i in range(len(headers))) for r in rows]
    return "\n".join([header_row, sep] + data_rows)
