"""Bar glyph sets — visual styles for `BarColumn(glyphs=...)`.

Each entry is a dict with five keys:

    fill      str — the glyph for a completely filled bar cell
    empty     str — the glyph for a completely empty cell
    partials  list[str] — ordered intermediate glyphs for fractional
              cells (empty → full). Can be []; the C core falls back
              to rounding when no partials are provided.
    left      str — left border glyph (can be "")
    right     str — right border glyph (can be "")

Consumers: `BarColumn(glyphs="smooth")` or `BarColumn(glyphs=<dict>)`,
and the theme preset functions in `barflow/themes.py`.

The C core packs these into `Column.fill/empty_ch/partials/
left_border/right_border` and renders without any Python round-trip
on the render thread.
"""

from __future__ import annotations


BAR_STYLES: dict[str, dict] = {
    # The default: 8-level smooth Unicode block bar `|██████▉     |`.
    "smooth": {
        "fill":     "\u2588",  # █
        "empty":    " ",
        "partials": ["\u258f", "\u258e", "\u258d", "\u258c",
                     "\u258b", "\u258a", "\u2589"],
        "left":     "|",
        "right":    "|",
    },

    # Full blocks against a light shade background: `████░░░░`.
    "blocks": {
        "fill":     "\u2588",  # █
        "empty":    "\u2591",  # ░
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # 4-level shade gradient: `█▓▒░░░`.
    "shade": {
        "fill":     "\u2588",  # █
        "empty":    "\u2591",  # ░
        "partials": ["\u2592", "\u2593"],  # ▒ ▓
        "left":     "",
        "right":    "",
    },

    # ASCII-only, brackets: `[####----]`.
    "ascii": {
        "fill":     "#",
        "empty":    "-",
        "partials": [],
        "left":     "[",
        "right":    "]",
    },

    # Classic equals: `[====    ]`.
    "equals": {
        "fill":     "=",
        "empty":    " ",
        "partials": [],
        "left":     "[",
        "right":    "]",
    },

    # Thin line: `━━━━──────`.
    "line": {
        "fill":     "\u2501",  # ━
        "empty":    "\u2500",  # ─
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Double line frame: `║████     ║`.
    "double": {
        "fill":     "\u2588",  # █
        "empty":    " ",
        "partials": ["\u258c"],  # ▌
        "left":     "\u2551",  # ║
        "right":    "\u2551",  # ║
    },

    # Round brackets, equals: `(====    )`.
    "round": {
        "fill":     "=",
        "empty":    " ",
        "partials": [],
        "left":     "(",
        "right":    ")",
    },

    # Dots: `●●●●○○○○`.
    "dots": {
        "fill":     "\u25cf",  # ●
        "empty":    "\u25cb",  # ○
        "partials": [],
        "left":     " ",
        "right":    " ",
    },

    # Braille — very dense, looks great with color.
    "braille": {
        "fill":     "\u28ff",  # ⣿
        "empty":    "\u2800",  # ⠀
        "partials": ["\u2840", "\u2844", "\u2846", "\u2847",
                     "\u28c7", "\u28e7", "\u28f7"],
        "left":     "",
        "right":    "",
    },

    # Arrows marching right: `→→→→    `.
    "arrows": {
        "fill":     "\u2192",  # →
        "empty":    " ",
        "partials": [],
        "left":     " ",
        "right":    " ",
    },

    # Sharp triangle tips: `▶▶▶▶▷▷▷▷`.
    "sharp": {
        "fill":     "\u25b6",  # ▶
        "empty":    "\u25b7",  # ▷
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Stars: `★★★★☆☆☆☆`.
    "stars": {
        "fill":     "\u2605",  # ★
        "empty":    "\u2606",  # ☆
        "partials": [],
        "left":     " ",
        "right":    " ",
    },

    # Hearts: `♥♥♥♥♡♡♡♡`.
    "hearts": {
        "fill":     "\u2665",  # ♥
        "empty":    "\u2661",  # ♡
        "partials": [],
        "left":     " ",
        "right":    " ",
    },

    # Horizontal bar feel with "o" fill: `[oooo    ]`.
    "pipes": {
        "fill":     "o",
        "empty":    ".",
        "partials": [],
        "left":     "[",
        "right":    "]",
    },

    # Pipe fill: `|||||    `.
    "pipe": {
        "fill":     "|",
        "empty":    " ",
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # ---- Neon / unique glyph sets ---------------------------------------

    # Lightning bolts marching: `⚡⚡⚡⚡····`.
    "lightning": {
        "fill":     "⚡",  # ⚡
        "empty":    "·",  # ·
        "partials": [],
        "left":     " ",
        "right":    " ",
    },

    # Diamonds: `◆◆◆◆◇◇◇◇`.
    "diamond": {
        "fill":     "◆",  # ◆
        "empty":    "◇",  # ◇
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Pixel cells: `▮▮▮▮▯▯▯▯`.
    "pixel": {
        "fill":     "▮",  # ▮
        "empty":    "▯",  # ▯
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Triangle wedges (synthwave): `◤◤◤◤◢◢◢◢`.
    "synthwave": {
        "fill":     "◤",  # ◤
        "empty":    "◢",  # ◢
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Bricks: `▰▰▰▰▱▱▱▱`.
    "bricks": {
        "fill":     "▰",  # ▰
        "empty":    "▱",  # ▱
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Sparkles: `✦✦✦✦✧✧✧✧`.
    "sparkle": {
        "fill":     "✦",  # ✦
        "empty":    "✧",  # ✧
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Bubbles: `◉◉◉◉◌◌◌◌`.
    "bubble": {
        "fill":     "◉",  # ◉
        "empty":    "◌",  # ◌
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Gems: `❖❖❖❖◇◇◇◇`.
    "gem": {
        "fill":     "❖",  # ❖
        "empty":    "◇",  # ◇
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Chevrons in cyan-bracket frame: `❯❯❯❯❮❮❮❮`.
    "chevron": {
        "fill":     "❯",  # ❯
        "empty":    "❮",  # ❮
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Rail: `▰▰▰▰┄┄┄┄`.
    "rail": {
        "fill":     "▰",  # ▰
        "empty":    "┄",  # ┄
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Slashes: `////····`.
    "slash": {
        "fill":     "╱",  # ╱
        "empty":    "·",  # ·
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Glow: `◎◎◎◎○○○○`.
    "glow": {
        "fill":     "◎",  # ◎
        "empty":    "○",  # ○
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Plasma squares: `▣▣▣▣▢▢▢▢`.
    "plasma": {
        "fill":     "▣",  # ▣
        "empty":    "▢",  # ▢
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # ASCII terminal-prompt feel: `[>>>>....]`.
    "terminal": {
        "fill":     ">",
        "empty":    ".",
        "partials": [],
        "left":     "[",
        "right":    "]",
    },

    # ASCII tilde wave: `~~~~....`.
    "wave_ascii": {
        "fill":     "~",
        "empty":    ".",
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # ASCII binary: `1111110000`.
    "binary": {
        "fill":     "1",
        "empty":    "0",
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # ASCII hash with curly braces: `{####....}`.
    "curly": {
        "fill":     "#",
        "empty":    ".",
        "partials": [],
        "left":     "{",
        "right":    "}",
    },

    # ASCII chevron march: `>>>>>....`.
    "march": {
        "fill":     ">",
        "empty":    "-",
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # ASCII railroad: `=+=+=+----`.
    "rail_ascii": {
        "fill":     "+",
        "empty":    "-",
        "partials": ["="],
        "left":     "|",
        "right":    "|",
    },

    # 8-shade vapor gradient (denser than `shade`): `█▓▒░·`.
    "vapor": {
        "fill":     "█",  # █
        "empty":    "·",  # ·
        "partials": ["░", "▒", "▓"],  # ░ ▒ ▓
        "left":     "",
        "right":    "",
    },

    # Pac-Man devouring a row of pellets: ` ᗧ•••••`. The eaten path behind
    # is blank, pellets `•` lie ahead, and the chomping mouth animates at the
    # leading edge via the `pacman` tip below. Single-cell glyphs throughout.
    "pacman": {
        "fill":     " ",       # eaten — blank path behind Pac-Man
        "empty":    "•",  # • pellet not yet eaten
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # ---- Emoji glyph sets (2-cell wide; pair only with 2-cell partners) -

    # Fire emoji: `🔥🔥🔥🔥⬛⬛⬛⬛`.
    "emoji_fire": {
        "fill":     "\U0001f525",  # 🔥
        "empty":    "⬛",      # ⬛
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Rocket trail: `🚀🚀🚀🚀🌑🌑🌑🌑`.
    "emoji_rocket": {
        "fill":     "\U0001f680",  # 🚀
        "empty":    "\U0001f311",  # 🌑
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Sakura petals: `🌸🌸🌸🌸⬜⬜⬜⬜`.
    "emoji_sakura": {
        "fill":     "\U0001f338",  # 🌸
        "empty":    "⬜",      # ⬜
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Lightning storm: `⚡⚡⚡⚡☁️ ...` simplified to ⚡/cloud-cell.
    "emoji_storm": {
        "fill":     "⚡️",  # ⚡️
        "empty":    "☁️",  # ☁️
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Sparkles emoji: `✨✨✨✨▫️▫️▫️▫️`.
    "emoji_sparkle": {
        "fill":     "✨",        # ✨
        "empty":    "▫️",  # ▫️
        "partials": [],
        "left":     "",
        "right":    "",
    },

    # Heartbeat: `❤️❤️❤️❤️🖤🖤🖤🖤`.
    "emoji_heart": {
        "fill":     "❤️",  # ❤️
        "empty":    "\U0001f5a4",    # 🖤
        "partials": [],
        "left":     "",
        "right":    "",
    },
}


# ---------------------------------------------------------------------------
# Animated leading-edge "tips"
# ---------------------------------------------------------------------------
#
# A tip is a list of single-cell frames cycled at the bar's boundary cell by
# the C core (indexed by frame_tick) whenever the bar is incomplete — the
# alive-progress-style motion that keeps a determinate bar alive even while
# its fill fraction is stalled. Attached here so every theme that selects one
# of these glyph sets animates with zero theme-side wiring; `BarColumn` reads
# it back via `tip_for`. Each frame must match its style's cell width (1 cell
# for these — emoji styles are intentionally left tip-less).
#
# Kept OUT of the registry literal (and off "smooth"/"ascii"/"equals") so an
# explicit `BarColumn(glyphs="smooth")` keeps its precise static 8-level fill
# and explicit-column render tests stay deterministic. (The C core's built-in
# default columns — used when no columns are passed at all — carry their own
# copy of the smooth comet tip; see install_default_columns.)
_TIPS: dict[str, list[str]] = {
    "blocks":  ["▒", "▓", "█", "▓"],                 # ▒▓█▓
    "shade":   ["░", "▒", "▓", "█", "▓", "▒"],  # ░▒▓█▓▒
    "vapor":   ["·", "░", "▒", "▓", "█", "▓", "▒", "░"],
    "braille": ["⡀", "⡄", "⡆", "⡇", "⣇", "⣧", "⣷", "⣿"],
    "dots":    ["○", "◔", "◑", "◕", "●", "◕", "◑", "◔"],
    "bubble":  ["◌", "○", "◎", "◉", "◎", "○"],   # ◌○◎◉◎○
    "glow":    ["○", "◎", "●", "◎"],                  # ○◎●◎
    "plasma":  ["▢", "▤", "▥", "▦", "▧", "▨", "▩", "▣"],
    "bricks":  ["▱", "▮", "▰"],                            # ▱▮▰
    "rail":    ["┄", "╌", "─", "▰"],                  # ┄╌─▰
    "pixel":   ["▯", "▭", "▬", "▮"],                  # ▯▭▬▮
    "diamond": ["◇", "◈", "◆", "◈"],                  # ◇◈◆◈
    "sharp":   ["▷", "▸", "▶"],                            # ▷▸▶
    "gem":     ["◇", "◈", "❖"],                            # ◇◈❖
    "sparkle": ["✧", "✦", "✶", "✦"],                  # ✧✦✶✦
    "pacman":  ["ᗧ", "●"],                               # ᗧ open → ● snap shut
}
for _name, _frames in _TIPS.items():
    BAR_STYLES[_name]["tip"] = _frames


def tip_for(spec) -> list[str]:
    """Animated-tip frames for a style name or dict, or `[]` if it has none.

    A fresh copy each call so callers can mutate without corrupting the
    registry. Unknown names return `[]` rather than raising — a missing tip
    is a no-op (static edge), not an error.
    """
    if isinstance(spec, str):
        s = BAR_STYLES.get(spec)
        return list(s.get("tip", [])) if s else []
    if isinstance(spec, dict):
        return list(spec.get("tip", []))
    return []


def get(name: str) -> dict:
    """Look up a bar style by name, with a helpful error on miss."""
    spec = BAR_STYLES.get(name)
    if spec is None:
        raise ValueError(
            f"unknown bar style: {name!r} "
            f"(available: {sorted(BAR_STYLES)})"
        )
    return spec


def to_tuple(spec) -> tuple:
    """Convert a style spec (name or dict) to the C core's 5-tuple."""
    if isinstance(spec, str):
        spec = get(spec)
    elif isinstance(spec, dict):
        # Merge with smooth defaults so partial specs work.
        base = BAR_STYLES["smooth"]
        spec = {**base, **spec}
    else:
        raise TypeError(f"bar glyphs must be a name or dict, got {type(spec).__name__}")
    return (
        spec["fill"],
        spec["empty"],
        list(spec["partials"]),
        spec["left"],
        spec["right"],
    )


__all__ = ["BAR_STYLES", "get", "to_tuple", "tip_for"]
