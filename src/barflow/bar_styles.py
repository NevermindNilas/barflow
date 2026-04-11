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
}


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


__all__ = ["BAR_STYLES", "get", "to_tuple"]
