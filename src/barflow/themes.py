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

import random as _random

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
# Neon / synthwave / vapor
# ---------------------------------------------------------------------------

def vaporwave():
    """80s mall aesthetic: hot pink + electric purple + cyan, triangle wedges."""
    return [
        c.SpinnerColumn(name="wedges", style="bold #ff71ce"), " ",
        c.DescriptionColumn(style="bold #b967ff"), " ",
        c.BarColumn(width=35, style="bold #ff71ce", glyphs="synthwave"), " ",
        c.PercentColumn(style="bold #01cdfe"), "  ",
        c.RateColumn(style="italic #05ffa1"),
    ]


def synthwave():
    """Sunset gradient feel: magenta + orange on deep purple."""
    return [
        c.SpinnerColumn(name="diamond", style="bold #ff2975"), " ",
        c.DescriptionColumn(style="bold #f6019d"), " ",
        c.BarColumn(width=35, style="bold #ff2975", glyphs="diamond"), " ",
        c.PercentColumn(style="bold #ffd319"), "  ",
        c.EtaColumn(style="dim #f6019d"),
    ]


def lightning():
    """Neon yellow zaps on dim gray. Looks alive even when slow."""
    return [
        c.SpinnerColumn(name="thunder", style="bold #fff200"), " ",
        c.DescriptionColumn(style="bold #fff200"), " ",
        c.BarColumn(width=30, style="bold #fff200", glyphs="lightning"), " ",
        c.PercentColumn(style="bold bright_white"), "  ",
        c.RateColumn(style="dim #fff200"),
    ]


def plasma():
    """Hot magenta plasma squares with cyan accents."""
    return [
        c.SpinnerColumn(name="square", style="bold #ff00aa"), " ",
        c.DescriptionColumn(style="bold #ff00aa"), " ",
        c.BarColumn(width=35, style="bold #ff00aa", glyphs="plasma"), " ",
        c.PercentColumn(style="bold #00f0ff"),
    ]


def acid():
    """Toxic acid green on black. Hacker terminal vibe."""
    return [
        c.SpinnerColumn(name="glitch", style="bold #39ff14"), " ",
        c.DescriptionColumn(style="bold #39ff14"), " ",
        c.BarColumn(width=35, style="bold #39ff14", glyphs="bricks"), " ",
        c.PercentColumn(style="bold #adff2f"), " ",
        c.RateColumn(style="dim #39ff14"),
    ]


def midnight():
    """Deep indigo + electric blue. Calm but glows."""
    return [
        c.SpinnerColumn(name="pulse", style="bold #6a5acd"), " ",
        c.DescriptionColumn(style="bold #00bfff"), " ",
        c.BarColumn(width=35, style="bold #1e90ff", glyphs="bubble"), " ",
        c.PercentColumn(style="bold #87cefa"), "  ",
        c.EtaColumn(style="dim #6a5acd"),
    ]


def ember():
    """Dim red glow with orange edges — old furnace."""
    return [
        c.SpinnerColumn(name="pulse", style="bold #cc3300"), " ",
        c.DescriptionColumn(style="dim #ff6600"), " ",
        c.BarColumn(width=35, style="bold #ff4500", glyphs="vapor"), " ",
        c.PercentColumn(style="bold #ffaa00"), " ",
        c.ElapsedColumn(style="dim #cc3300"),
    ]


def amber_crt():
    """Amber-on-black CRT terminal — DEC VT220 vibe."""
    return [
        c.DescriptionColumn(style="bold #ffb000"), " ",
        c.BarColumn(width=35, style="bold #ffb000", glyphs="terminal"), " ",
        c.PercentColumn(style="bold #ffb000"), " ",
        c.CountColumn(style="#ff8c00"),
    ]


def miami():
    """Miami Vice: teal + hot pink, art deco brick."""
    return [
        c.DescriptionColumn(style="bold #ff6ec7"), " ",
        c.BarColumn(width=35, style="bold #00f5d4", glyphs="bricks"), " ",
        c.PercentColumn(style="bold #ff6ec7"), "  ",
        c.RateColumn(style="dim #00f5d4"),
    ]


def gold_rush():
    """Bright gold gem bar."""
    return [
        c.SpinnerColumn(name="diamond", style="bold #ffd700"), " ",
        c.DescriptionColumn(style="bold #ffd700"), " ",
        c.BarColumn(width=30, style="bold #ffd700", glyphs="gem"), " ",
        c.PercentColumn(style="bold #fffacd"),
    ]


def alien():
    """Acidic green + magenta sparkles."""
    return [
        c.SpinnerColumn(name="spark", style="bold #00ff66"), " ",
        c.DescriptionColumn(style="bold #ff00ff"), " ",
        c.BarColumn(width=35, style="bold #00ff66", glyphs="sparkle"), " ",
        c.PercentColumn(style="bold #ff00ff"), " ",
        c.EtaColumn(style="dim #00ff66"),
    ]


def deep_sea():
    """Navy + teal + glow bubbles."""
    return [
        c.SpinnerColumn(name="moon_text", style="bold #1e3a5f"), " ",
        c.DescriptionColumn(style="bold #2e8b8b"), " ",
        c.BarColumn(width=35, style="bold #20b2aa", glyphs="glow"), " ",
        c.PercentColumn(style="bold #afeeee"), " ",
        c.EtaColumn(style="dim #2e8b8b"),
    ]


def magma():
    """Bright orange flow over dim red — high energy."""
    return [
        c.SpinnerColumn(name="pulse", style="bold #ff4500"), " ",
        c.DescriptionColumn(style="bold #ff8c00"), " ",
        c.BarColumn(width=35, style="bold #ff4500", glyphs="vapor"), " ",
        c.PercentColumn(style="bold #ffd700"), "  ",
        c.RateColumn(style="#ff8c00"),
    ]


def void():
    """Black hole vibe: dim purple + bright magenta accents."""
    return [
        c.SpinnerColumn(name="pulse", style="dim #6a0dad"), " ",
        c.DescriptionColumn(style="bold #b300b3"), " ",
        c.BarColumn(width=35, style="bold #b300b3", glyphs="bubble"), " ",
        c.PercentColumn(style="bold #ff66ff"),
    ]


def chevron():
    """Cyan chevrons march right — directional motion."""
    return [
        c.SpinnerColumn(name="caret", style="bold bright_cyan"), " ",
        c.DescriptionColumn(style="bold bright_cyan"), " ",
        c.BarColumn(width=35, style="bold bright_cyan", glyphs="chevron"), " ",
        c.PercentColumn(style="bold #00ffff"), " ",
        c.RateColumn(style="dim cyan"),
    ]


def rail_neon():
    """Neon rail: bright fill segments on dotted track."""
    return [
        c.DescriptionColumn(style="bold #00ffff"), " ",
        c.BarColumn(width=40, style="bold #00ffff", glyphs="rail"), " ",
        c.PercentColumn(style="bold #ff00ff"), " ",
        c.EtaColumn(style="dim #00ffff"),
    ]


def slash_neon():
    """Pink slashes on dim dots."""
    return [
        c.SpinnerColumn(name="slash", style="bold #ff2fbf"), " ",
        c.DescriptionColumn(style="bold #ff2fbf"), " ",
        c.BarColumn(width=35, style="bold #ff2fbf", glyphs="slash"), " ",
        c.PercentColumn(style="bold bright_white"),
    ]


# ---------------------------------------------------------------------------
# ASCII art / unique text-only themes
# ---------------------------------------------------------------------------

def hacker():
    """Green-on-black hacker terminal: `[>>>>....] 42%`."""
    return [
        c.TextColumn("$ ", style="bold bright_green"),
        c.DescriptionColumn(style="bold bright_green"), " ",
        c.BarColumn(width=30, style="bold bright_green", glyphs="terminal"), " ",
        c.PercentColumn(style="bold bright_green"), " ",
        c.RateColumn(style="dim green"),
    ]


def binary():
    """Binary rain: `1111110000`. Bright green digits."""
    return [
        c.DescriptionColumn(style="bold bright_green"), " ",
        c.BarColumn(width=40, style="bright_green", glyphs="binary"), " ",
        c.PercentColumn(style="bold bright_green"),
    ]


def curly():
    """ASCII hash with curly braces: `{####....}`."""
    return [
        c.DescriptionColumn(style="bold yellow"), " ",
        c.BarColumn(width=30, style="bold yellow", glyphs="curly"), " ",
        c.PercentColumn(style="yellow"), " ",
        c.CountColumn(style="dim"),
    ]


def march():
    """Chevron march: `>>>>>----`."""
    return [
        c.DescriptionColumn(style="bold cyan"), " ",
        c.BarColumn(width=35, style="bold bright_cyan", glyphs="march"), " ",
        c.PercentColumn(style="bold"),
    ]


def wave_ascii():
    """Tilde wave: `~~~~....`."""
    return [
        c.DescriptionColumn(style="bold #00bfff"), " ",
        c.BarColumn(width=35, style="bold #00bfff", glyphs="wave_ascii"), " ",
        c.PercentColumn(style="bold #87cefa"),
    ]


def rail_ascii():
    """ASCII railroad: `|=+=+=+----|`."""
    return [
        c.DescriptionColumn(style="bold yellow"), " ",
        c.BarColumn(width=30, style="bold yellow", glyphs="rail_ascii"), " ",
        c.PercentColumn(style="bold yellow"),
    ]


# ---------------------------------------------------------------------------
# Emoji themes (2-cell glyphs — terminal must render emoji width)
# ---------------------------------------------------------------------------

def fire_emoji():
    """🔥 fire bar with bright orange text."""
    return [
        c.DescriptionColumn(style="bold #ff4500"), " ",
        c.BarColumn(width=15, style="", glyphs="emoji_fire"), " ",
        c.PercentColumn(style="bold #ffaa00"), " ",
        c.RateColumn(style="dim #ff4500"),
    ]


def rocket_emoji():
    """🚀 rocket through space."""
    return [
        c.SpinnerColumn(name="rocket", style="bold #ff6600"), " ",
        c.DescriptionColumn(style="bold #00bfff"), " ",
        c.BarColumn(width=15, style="", glyphs="emoji_rocket"), " ",
        c.PercentColumn(style="bold bright_white"), " ",
        c.EtaColumn(style="dim #00bfff"),
    ]


def sakura_emoji():
    """🌸 cherry blossom petals."""
    return [
        c.DescriptionColumn(style="bold #ffb7c5"), " ",
        c.BarColumn(width=15, style="", glyphs="emoji_sakura"), " ",
        c.PercentColumn(style="bold #ff69b4"),
    ]


def storm_emoji():
    """⚡ thunder over ☁️ clouds."""
    return [
        c.SpinnerColumn(name="thunder", style="bold #fff200"), " ",
        c.DescriptionColumn(style="bold bright_white"), " ",
        c.BarColumn(width=15, style="", glyphs="emoji_storm"), " ",
        c.PercentColumn(style="bold #fff200"),
    ]


def sparkle_emoji():
    """✨ sparkle bar."""
    return [
        c.SpinnerColumn(name="spark", style="bold #ffd700"), " ",
        c.DescriptionColumn(style="bold #ffd700"), " ",
        c.BarColumn(width=15, style="", glyphs="emoji_sparkle"), " ",
        c.PercentColumn(style="bold #fffacd"),
    ]


def pacman_emoji():
    """🟡 pacman munching pellets."""
    return [
        c.DescriptionColumn(style="bold #ffeb3b"), " ",
        c.BarColumn(width=15, style="", glyphs="emoji_pacman"), " ",
        c.PercentColumn(style="bold #ffeb3b"), " ",
        c.RateColumn(style="dim yellow"),
    ]


def heart_emoji():
    """❤️ heartbeat bar."""
    return [
        c.SpinnerColumn(name="heartbeat", style="bold #ff1744"), " ",
        c.DescriptionColumn(style="bold #ff1744"), " ",
        c.BarColumn(width=15, style="", glyphs="emoji_heart"), " ",
        c.PercentColumn(style="bold #ff80ab"),
    ]


def moon_emoji():
    """🌑→🌕 moon phases as a spinner with ocean bar."""
    return [
        c.SpinnerColumn(name="moon", style=""), " ",
        c.DescriptionColumn(style="bold #87ceeb"), " ",
        c.BarColumn(width=30, style="bold #4682b4", glyphs="bubble"), " ",
        c.PercentColumn(style="bold bright_white"),
    ]


def weather_emoji():
    """Weather rotation: ☀️ → ☁️ → ⛈️."""
    return [
        c.SpinnerColumn(name="weather", style=""), " ",
        c.DescriptionColumn(style="bold #87ceeb"), " ",
        c.BarColumn(width=30, style="#87ceeb", glyphs="glow"), " ",
        c.PercentColumn(style="bold"),
    ]


# ---------------------------------------------------------------------------
# Brand-flavored / utility templates
# ---------------------------------------------------------------------------

def github_dark():
    """Github dark UI palette: subtle green accent, neutral text."""
    return [
        c.DescriptionColumn(style="bold #c9d1d9"), " ",
        c.BarColumn(width=35, style="#3fb950", glyphs="smooth"), " ",
        c.PercentColumn(style="#c9d1d9"), " ",
        c.RateColumn(style="dim #8b949e"),
    ]


def discord():
    """Discord palette: blurple + grey background feel."""
    return [
        c.SpinnerColumn(name="dots", style="bold #5865f2"), " ",
        c.DescriptionColumn(style="bold #ffffff"), " ",
        c.BarColumn(width=35, style="bold #5865f2", glyphs="smooth"), " ",
        c.PercentColumn(style="bold #ffffff"), " ",
        c.EtaColumn(style="dim #b9bbbe"),
    ]


def dracula():
    """Dracula theme palette: pink + purple + green."""
    return [
        c.SpinnerColumn(name="pulse", style="bold #ff79c6"), " ",
        c.DescriptionColumn(style="bold #bd93f9"), " ",
        c.BarColumn(width=35, style="bold #50fa7b", glyphs="smooth"), " ",
        c.PercentColumn(style="bold #f1fa8c"), " ",
        c.EtaColumn(style="dim #6272a4"),
    ]


def solarized():
    """Solarized dark palette: cyan + base accents."""
    return [
        c.DescriptionColumn(style="bold #93a1a1"), " ",
        c.BarColumn(width=35, style="bold #2aa198", glyphs="smooth"), " ",
        c.PercentColumn(style="bold #b58900"), " ",
        c.RateColumn(style="dim #586e75"),
    ]


def nord():
    """Nord palette: cool frost + polar night."""
    return [
        c.DescriptionColumn(style="bold #88c0d0"), " ",
        c.BarColumn(width=35, style="bold #81a1c1", glyphs="smooth"), " ",
        c.PercentColumn(style="bold #eceff4"), " ",
        c.EtaColumn(style="dim #4c566a"),
    ]


def gruvbox():
    """Gruvbox warm palette: orange + green + cream."""
    return [
        c.DescriptionColumn(style="bold #fabd2f"), " ",
        c.BarColumn(width=35, style="bold #b8bb26", glyphs="blocks"), " ",
        c.PercentColumn(style="bold #fe8019"), " ",
        c.RateColumn(style="dim #d65d0e"),
    ]


# ---------------------------------------------------------------------------
# Compact / specialized templates
# ---------------------------------------------------------------------------

def tiny():
    """Single-line minimal: spinner + 10-cell bar + percent."""
    return [
        c.SpinnerColumn(name="dots", style="cyan"), " ",
        c.BarColumn(width=10, style="cyan", glyphs="blocks"), " ",
        c.PercentColumn(),
    ]


def detailed():
    """Verbose: every available column for debugging long jobs."""
    return [
        c.SpinnerColumn(name="dots", style="bold #00ffff"), " ",
        c.DescriptionColumn(style="bold"), " ",
        c.BarColumn(width=30, style="cyan"), " ",
        c.PercentColumn(style="bold"), "  ",
        c.CountColumn(), "  ",
        c.RateColumn(style="dim"), "  [",
        c.ElapsedColumn(style="dim"), "<", c.EtaColumn(style="dim"), "]",
    ]


def downloading():
    """Download-flavored: rate + count + eta, blue smooth bar."""
    return [
        c.TextColumn("⬇ ", style="bold #00bfff"),
        c.DescriptionColumn(style="bold #00bfff"), "  ",
        c.BarColumn(width=30, style="bold #00bfff"), " ",
        c.PercentColumn(style="bold"), "  ",
        c.CountColumn(style="dim"), "  ",
        c.RateColumn(style="bold #00bfff"), "  eta ",
        c.EtaColumn(style="dim"),
    ]


def building():
    """CI/build-flavored: orange spinner, mono bar, elapsed."""
    return [
        c.SpinnerColumn(name="dots2", style="bold #ff8c00"), " ",
        c.DescriptionColumn(style="bold"), " ",
        c.BarColumn(width=30, style="bold #ff8c00", glyphs="blocks"), " ",
        c.PercentColumn(style="bold"), "  ",
        c.ElapsedColumn(style="dim"),
    ]


def training():
    """ML training: epoch-style verbose with rate/eta."""
    return [
        c.TextColumn("⚙ ", style="bold #00ff88"),
        c.DescriptionColumn(style="bold #00ff88"), "  ",
        c.BarColumn(width=25, style="bold #00ff88", glyphs="blocks"), " ",
        c.PercentColumn(style="bold"), "  ",
        c.CountColumn(), "  it/s ",
        c.RateColumn(style="bold #00ff88"), "  eta ",
        c.EtaColumn(style="dim"),
    ]


# ---------------------------------------------------------------------------
# Meta
# ---------------------------------------------------------------------------

def random_theme():
    """Pick a random theme each call and return its columns."""
    # Collapse aliases, drop self, so every pick is a distinct real theme.
    # dict.fromkeys de-dupes by identity while preserving THEMES' insertion
    # order — a plain set would iterate in a hash-randomized order, defeating
    # reproducibility under a seeded RNG.
    pool = list(dict.fromkeys(
        fn for fn in THEMES.values() if fn is not random_theme
    ))
    return _random.choice(pool)()


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

    # Neon / synthwave / vapor
    "vaporwave":    vaporwave,
    "synthwave":    synthwave,
    "lightning":    lightning,
    "plasma":       plasma,
    "acid":         acid,
    "midnight":     midnight,
    "ember":        ember,
    "amber":        amber_crt,
    "amber_crt":    amber_crt,
    "miami":        miami,
    "gold":         gold_rush,
    "gold_rush":    gold_rush,
    "alien":        alien,
    "deep_sea":     deep_sea,
    "magma":        magma,
    "void":         void,
    "chevron":      chevron,
    "rail_neon":    rail_neon,
    "slash":        slash_neon,

    # ASCII art
    "hacker":       hacker,
    "binary":       binary,
    "curly":        curly,
    "march":        march,
    "wave":         wave_ascii,
    "rail_ascii":   rail_ascii,

    # Emoji
    "fire_emoji":   fire_emoji,
    "rocket":       rocket_emoji,
    "rocket_emoji": rocket_emoji,
    "sakura":       sakura_emoji,
    "storm":        storm_emoji,
    "sparkle":      sparkle_emoji,
    "pacman":       pacman_emoji,
    "heart_emoji":  heart_emoji,
    "moon":         moon_emoji,
    "weather":      weather_emoji,

    # Brand palettes
    "github":       github_dark,
    "github_dark":  github_dark,
    "discord":      discord,
    "dracula":      dracula,
    "solarized":    solarized,
    "nord":         nord,
    "gruvbox":      gruvbox,

    # Specialized
    "tiny":         tiny,
    "detailed":     detailed,
    "downloading":  downloading,
    "building":     building,
    "training":     training,

    # Meta
    "random":       random_theme,
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
    # Neon / synthwave
    "vaporwave", "synthwave", "lightning", "plasma", "acid", "midnight",
    "ember", "amber_crt", "miami", "gold_rush", "alien", "deep_sea", "magma",
    "void", "chevron", "rail_neon", "slash_neon",
    # ASCII art
    "hacker", "binary", "curly", "march", "wave_ascii", "rail_ascii",
    # Emoji
    "fire_emoji", "rocket_emoji", "sakura_emoji", "storm_emoji",
    "sparkle_emoji", "pacman_emoji", "heart_emoji", "moon_emoji",
    "weather_emoji",
    # Brand
    "github_dark", "discord", "dracula", "solarized", "nord", "gruvbox",
    # Specialized
    "tiny", "detailed", "downloading", "building", "training",
    # Meta
    "random_theme",
]
