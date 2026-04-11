"""ANSI style parser for BarFlow columns.

Grammar (whitespace-separated tokens in a single string):

    Named fg color:     red, green, cyan, bright_red, gray, ...
    Hex fg color:       #rgb or #rrggbb           (truecolor SGR)
    256-color fg:       color(180)                (8-bit palette)
    Background:         on <color>  or  on_<color>  or  on #rrggbb
    Text styles:        bold, dim, italic, underline, blink, reverse, strike

Examples:

    style("cyan")                  → "\\x1b[36m"
    style("bold #ff8800")          → "\\x1b[1;38;2;255;136;0m"
    style("bold white on_blue")    → "\\x1b[1;37;44m"
    style("dim italic #88ccff")    → "\\x1b[2;3;38;2;136;204;255m"
    style("underline color(214)")  → "\\x1b[4;38;5;214m"

Pass the *same spec* to any column factory via `style=` (or `color=` —
backward-compat alias): `BarColumn(style="bold bright_cyan")`.

The returned string is the SGR escape that *starts* the style; the
C core appends `\\x1b[0m` (reset) after each styled column.

A raw ANSI escape (starting with `\\x1b`) is passed through unchanged
so users can hand-craft sequences we don't know about (e.g., italic
on a specific terminal).
"""

from __future__ import annotations


# Foreground 30–37 / 90–97
_NAMED_FG: dict[str, int] = {
    "black":   30, "red":          31, "green":          32, "yellow":         33,
    "blue":    34, "magenta":      35, "cyan":           36, "white":          37,
    "default": 39,
    "bright_black":   90, "bright_red":     91, "bright_green":   92,
    "bright_yellow":  93, "bright_blue":    94, "bright_magenta": 95,
    "bright_cyan":    96, "bright_white":   97,
    "gray":           90, "grey":           90,
}

# Background = fg + 10
_NAMED_BG: dict[str, int] = {k: (v + 10) for k, v in _NAMED_FG.items()}

_STYLES: dict[str, int] = {
    "bold":       1,
    "dim":        2,
    "italic":     3,
    "underline":  4,
    "blink":      5,
    "reverse":    7,
    "strike":     9,
    "reset":      0,
}


def _parse_hex(h: str) -> tuple[int, int, int]:
    s = h.lstrip("#")
    if len(s) == 3:
        s = "".join(c * 2 for c in s)
    if len(s) != 6 or not all(c in "0123456789abcdefABCDEF" for c in s):
        raise ValueError(f"invalid hex color: {h!r}")
    return int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16)


def _parse_color256(tok: str, is_bg: bool) -> str | None:
    """`color(N)` → 8-bit palette SGR component, or None if not that shape."""
    if not (tok.startswith("color(") and tok.endswith(")")):
        return None
    try:
        idx = int(tok[6:-1])
    except ValueError:
        return None
    if not 0 <= idx <= 255:
        raise ValueError(f"color index out of range: {tok}")
    return f"{48 if is_bg else 38};5;{idx}"


def style(spec: str | None) -> str:
    """Parse a style spec into an ANSI SGR escape sequence. Empty → empty."""
    if not spec:
        return ""
    # Raw escape passthrough.
    if spec.startswith("\x1b"):
        return spec

    parts = spec.split()
    codes: list[str] = []
    i = 0
    saw_fg = False

    while i < len(parts):
        tok = parts[i]
        low = tok.lower()

        if low in _STYLES:
            codes.append(str(_STYLES[low]))
            i += 1
            continue

        # "on <color>"
        if low == "on" and i + 1 < len(parts):
            bg = parts[i + 1]
            low_bg = bg.lower()
            if bg.startswith("#"):
                r, g, b = _parse_hex(bg)
                codes.append(f"48;2;{r};{g};{b}")
            elif (c256 := _parse_color256(low_bg, is_bg=True)) is not None:
                codes.append(c256)
            elif low_bg in _NAMED_BG:
                codes.append(str(_NAMED_BG[low_bg]))
            else:
                raise ValueError(f"unknown background color: {bg!r}")
            i += 2
            continue

        # "on_<color>"
        if low.startswith("on_"):
            name = low[3:]
            if name in _NAMED_BG:
                codes.append(str(_NAMED_BG[name]))
            else:
                raise ValueError(f"unknown background color: {name!r}")
            i += 1
            continue

        # Hex fg
        if tok.startswith("#"):
            r, g, b = _parse_hex(tok)
            codes.append(f"38;2;{r};{g};{b}")
            saw_fg = True
            i += 1
            continue

        # 256-color fg
        c256 = _parse_color256(low, is_bg=False)
        if c256 is not None:
            codes.append(c256)
            saw_fg = True
            i += 1
            continue

        # Named fg
        if low in _NAMED_FG:
            codes.append(str(_NAMED_FG[low]))
            saw_fg = True
            i += 1
            continue

        raise ValueError(f"unknown style token: {tok!r}")

    if not codes:
        return ""
    return "\x1b[" + ";".join(codes) + "m"


RESET = "\x1b[0m"


__all__ = ["style", "RESET"]
