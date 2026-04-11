"""Named column presets — pick a theme by name, get a complete bar.

Usage:

    import barflow
    with barflow.Progress(theme="neon", total=1000) as p:
        ...

    # or as a starting point to customize:
    cols = barflow.themes.get("fire")
    cols.append("  [custom]")
    with barflow.Progress(*cols, total=1000) as p:
        ...

Every theme is a callable returning a fresh list of column factory
tuples. Strings inside the list become literal text columns. Themes
mix-and-match colours (from `barflow.style`) and bar glyphs (from
`barflow.bar_styles`) so users can skim `THEMES` and pick one that
matches their app's visual identity.
"""

from __future__ import annotations

from . import columns as c


# ---------------------------------------------------------------------------
# Utilitarian themes (minimal visual noise)
# ---------------------------------------------------------------------------

def classic():
    """tqdm-style: desc, percent, bar, count, elapsed<eta, rate."""
    return [
        c.DescriptionColumn(), ": ",
        c.PercentColumn(), " ",
        c.BarColumn(width=40, style="cyan"), " ",
        c.CountColumn(), " [",
        c.ElapsedColumn(), "<", c.EtaColumn(), ", ",
        c.RateColumn(), "]",
    ]


def minimal():
    """Just a bar and a percentage."""
    return [
        c.BarColumn(width=30, style="green"), " ",
        c.PercentColumn(style="bold"),
    ]


def rich_like():
    """Shape-compatible with rich.progress's default columns."""
    return [
        c.DescriptionColumn(), " ",
        c.BarColumn(width=40, style="magenta"), " ",
        c.PercentColumn(), " • ",
        c.EtaColumn(),
    ]


def spinner():
    """Spinner + description + rate — for unknown-total iterables."""
    return [
        c.SpinnerColumn(name="dots", style="cyan"), " ",
        c.DescriptionColumn(), "  ",
        c.CountColumn(), " ",
        c.RateColumn(),
    ]


def mono():
    """Monochrome — white on default background, no embellishment."""
    return [
        c.DescriptionColumn(style="bold"), " ",
        c.BarColumn(width=40, style="white"), " ",
        c.PercentColumn(), "  ",
        c.RateColumn(style="dim"),
    ]


def ghost():
    """Low-contrast dim gray — useful when you want the bar to fade back."""
    return [
        c.DescriptionColumn(style="dim"), " ",
        c.BarColumn(width=40, style="dim", glyphs="shade"), " ",
        c.PercentColumn(style="dim"), " ",
        c.ElapsedColumn(style="dim"),
    ]


# ---------------------------------------------------------------------------
# ASCII-safe themes (work on any terminal, any code page)
# ---------------------------------------------------------------------------

def ascii():
    """ASCII-only: `[####----]`. Compatible with legacy terminals."""
    return [
        c.DescriptionColumn(), ": ",
        c.PercentColumn(), " ",
        c.BarColumn(width=30, style="", glyphs="ascii"), " ",
        c.CountColumn(),
    ]


def equals():
    """Old-school: `download [====    ] 40%`."""
    return [
        c.DescriptionColumn(style="bold"), " ",
        c.BarColumn(width=30, style="yellow", glyphs="equals"), " ",
        c.PercentColumn(style="bold yellow"),
    ]


def brackets():
    """ASCII brackets with classic coloring."""
    return [
        c.DescriptionColumn(style="cyan"), " ",
        c.BarColumn(width=30, style="bold green", glyphs="ascii"), " ",
        c.PercentColumn(), " ",
        c.CountColumn(style="dim"),
    ]


# ---------------------------------------------------------------------------
# Colorful / bold themes
# ---------------------------------------------------------------------------

def neon():
    """Hot pink, cyan, bright yellow — unmissable."""
    return [
        c.SpinnerColumn(name="dots2", style="bold #ff2fbf"), " ",
        c.DescriptionColumn(style="bold #00ffff"), " ",
        c.BarColumn(width=35, style="bold #ff2fbf"), " ",
        c.PercentColumn(style="bold #ffff00"), "  ",
        c.RateColumn(style="bold #00ffff"),
    ]


def pastel():
    """Soft desaturated palette — subtle but colorful."""
    return [
        c.DescriptionColumn(style="#b4a7d6"), " ",
        c.BarColumn(width=35, style="#a4c2f4", glyphs="shade"), " ",
        c.PercentColumn(style="#b6d7a8"), " ",
        c.ElapsedColumn(style="dim #f9cb9c"), "<",
        c.EtaColumn(style="dim #f9cb9c"),
    ]


def retro():
    """Bright green CRT terminal."""
    return [
        c.DescriptionColumn(style="bold bright_green"), " > ",
        c.BarColumn(width=35, style="bold bright_green", glyphs="blocks"), " ",
        c.PercentColumn(style="bright_green"), " ",
        c.CountColumn(style="bright_green"), " @ ",
        c.RateColumn(style="green"),
    ]


def matrix():
    """Matrix rain — green braille falling through a dark bar."""
    return [
        c.SpinnerColumn(name="dots2", style="bold bright_green"), " ",
        c.DescriptionColumn(style="bright_green"), " ",
        c.BarColumn(width=35, style="bright_green", glyphs="braille"), " ",
        c.PercentColumn(style="bold bright_green"),
    ]


def fire():
    """Warm red → orange → yellow. Good for long builds."""
    return [
        c.SpinnerColumn(name="triangle", style="bold #ff4500"), " ",
        c.DescriptionColumn(style="bold #ff6600"), " ",
        c.BarColumn(width=35, style="bold #ff3300"), " ",
        c.PercentColumn(style="bold #ffcc00"), "  ",
        c.RateColumn(style="#ff8800"),
    ]


def ocean():
    """Cool blues and cyans. Like rich's default, calmer."""
    return [
        c.SpinnerColumn(name="dots", style="bold #4488ff"), " ",
        c.DescriptionColumn(style="bold #88ccff"), " ",
        c.BarColumn(width=35, style="#0099ff"), " ",
        c.PercentColumn(style="bold #66ddff"), " ",
        c.EtaColumn(style="dim #88ccff"),
    ]


def ice():
    """Very cold: white/cyan/blue, sharp glyphs."""
    return [
        c.DescriptionColumn(style="bold bright_white"), " ",
        c.BarColumn(width=35, style="bold bright_cyan", glyphs="sharp"), " ",
        c.PercentColumn(style="bold bright_white"), " ",
        c.ElapsedColumn(style="dim bright_cyan"),
    ]


def sunset():
    """Pink → orange → coral gradient feel."""
    return [
        c.DescriptionColumn(style="bold #ff6b9d"), " ",
        c.BarColumn(width=35, style="bold #ff8c42", glyphs="shade"), " ",
        c.PercentColumn(style="bold #ffb347"), "  ",
        c.RateColumn(style="italic #ffc8a2"),
    ]


def forest():
    """Deep greens, browns, earthy feel."""
    return [
        c.SpinnerColumn(name="dots", style="#4a7c59"), " ",
        c.DescriptionColumn(style="bold #6b8e23"), " ",
        c.BarColumn(width=35, style="#2d5016", glyphs="blocks"), " ",
        c.PercentColumn(style="#8b7355"), " ",
        c.EtaColumn(style="dim #4a7c59"),
    ]


def cyberpunk():
    """High-contrast magenta + cyan + yellow; neon city vibe."""
    return [
        c.SpinnerColumn(name="dots2", style="bold #ff00ff"), " ",
        c.DescriptionColumn(style="bold #00ffff"), " ",
        c.BarColumn(width=35, style="bold #ff00ff", glyphs="sharp"), " ",
        c.PercentColumn(style="bold #ffff00 on #1a001a"), " ",
        c.RateColumn(style="#00ffff"),
    ]


# ---------------------------------------------------------------------------
# Playful / themed
# ---------------------------------------------------------------------------

def hearts():
    """Hearts glyph bar — for fun scripts and demos."""
    return [
        c.DescriptionColumn(style="bold #ff69b4"), " ",
        c.BarColumn(width=20, style="bold #ff1493", glyphs="hearts"), " ",
        c.PercentColumn(style="#ff69b4"),
    ]


def stars():
    """Star glyph bar — reward chart aesthetic."""
    return [
        c.DescriptionColumn(style="bold yellow"), " ",
        c.BarColumn(width=20, style="bold yellow", glyphs="stars"), " ",
        c.PercentColumn(style="bold bright_yellow"),
    ]


def arrows_march():
    """Arrows marching rightward."""
    return [
        c.DescriptionColumn(style="bold cyan"), " ",
        c.BarColumn(width=25, style="bold bright_cyan", glyphs="arrows"), " ",
        c.PercentColumn(style="bold"),
    ]


def pipes():
    """Unix pipe aesthetic: `|||||    `."""
    return [
        c.DescriptionColumn(style="bold green"), " ",
        c.BarColumn(width=35, style="bright_green", glyphs="pipe"), " ",
        c.PercentColumn(style="green"), " ",
        c.RateColumn(style="dim green"),
    ]


def shade_cool():
    """Shaded blocks in cool cyan."""
    return [
        c.DescriptionColumn(style="bright_cyan"), " ",
        c.BarColumn(width=35, style="bright_cyan", glyphs="shade"), " ",
        c.PercentColumn(style="bold cyan"), " ",
        c.EtaColumn(style="dim cyan"),
    ]


def line_clean():
    """Thin line bar — understated, modern."""
    return [
        c.DescriptionColumn(style="bold"), " ",
        c.BarColumn(width=40, style="bright_white", glyphs="line"), " ",
        c.PercentColumn(style="dim"),
    ]


def double_frame():
    """Double-line box frame around a solid bar."""
    return [
        c.DescriptionColumn(style="bold bright_blue"), " ",
        c.BarColumn(width=30, style="bold bright_blue", glyphs="double"), " ",
        c.PercentColumn(style="bold"),
    ]


def round_retro():
    """Parentheses around equals, soft retro feel."""
    return [
        c.DescriptionColumn(style="bold yellow"), " ",
        c.BarColumn(width=30, style="bold bright_yellow", glyphs="round"), " ",
        c.PercentColumn(style="bright_yellow"),
    ]


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

THEMES = {
    # Utilitarian
    "classic":      classic,
    "minimal":      minimal,
    "rich":         rich_like,
    "rich_like":    rich_like,
    "spinner":      spinner,
    "mono":         mono,
    "ghost":        ghost,

    # ASCII / legacy
    "ascii":        ascii,
    "equals":       equals,
    "brackets":     brackets,

    # Colorful
    "neon":         neon,
    "pastel":       pastel,
    "retro":        retro,
    "matrix":       matrix,
    "fire":         fire,
    "ocean":        ocean,
    "ice":          ice,
    "sunset":       sunset,
    "forest":       forest,
    "cyberpunk":    cyberpunk,

    # Playful / themed
    "hearts":       hearts,
    "stars":        stars,
    "arrows":       arrows_march,
    "pipes":        pipes,
    "shade":        shade_cool,
    "line":         line_clean,
    "double":       double_frame,
    "round":        round_retro,
}


def get(name: str):
    factory = THEMES.get(name)
    if factory is None:
        raise ValueError(
            f"unknown theme: {name!r} "
            f"(available: {sorted(THEMES)})"
        )
    return factory()


def names() -> list[str]:
    """Deduplicated sorted list of theme names (aliases collapsed)."""
    # Collapse aliases that point at the same function.
    seen = {}
    for name, fn in THEMES.items():
        seen.setdefault(fn, name)
    return sorted(seen.values())


__all__ = [
    "THEMES", "get", "names",
    # Utilitarian
    "classic", "minimal", "rich", "rich_like", "spinner", "mono", "ghost",
    # ASCII / legacy
    "ascii", "equals", "brackets",
    # Colorful
    "neon", "pastel", "retro", "matrix", "fire", "ocean", "ice", "sunset",
    "forest", "cyberpunk",
    # Playful / themed
    "hearts", "stars", "arrows", "pipes", "shade", "line", "double", "round",
]
