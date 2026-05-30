"""Spinner frame library + a small compositional DSL.

Frames are materialized into plain lists of UTF-8 strings so the C core
can pick them up via `next_frame = frames[tick % len(frames)]` — no
Python per-frame cost on the render thread (which runs at most ~20 Hz).

The factories below mirror alive-progress's compositional API
(`alive_progress/animations/spinners.py`) in shape, so users can port
their animations over with a rename. We keep it simple: every factory
returns a `list[str]`, which becomes the `frames` field of a
`SpinnerColumn`.
"""

from __future__ import annotations

from collections.abc import Sequence

# Signatures use the built-in `list[str]` generic and `Sequence` from
# collections.abc — both resolvable at runtime, so `typing.get_type_hints`
# (and doc/validation tooling) won't choke. `Sequence` is a cheap import.

# ---- Built-in spinners -------------------------------------------------

SPINNERS: dict[str, list[str]] = {
    "dots":      ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"],
    "line":      ["-", "\\", "|", "/"],
    "arrow":     ["←", "↖", "↑", "↗", "→", "↘", "↓", "↙"],
    "classic":   ["|", "/", "-", "\\"],
    "triangle":  ["◢", "◣", "◤", "◥"],
    "circle":    ["◜", "◠", "◝", "◞", "◡", "◟"],
    "earth":     ["🌍", "🌎", "🌏"],
    "clock":     ["🕐","🕑","🕒","🕓","🕔","🕕","🕖","🕗","🕘","🕙","🕚","🕛"],
    "dots2":     ["⣾","⣽","⣻","⢿","⡿","⣟","⣯","⣷"],
    "bouncing_ball": ["⠁","⠂","⠄","⡀","⢀","⠠","⠐","⠈"],
    "hamburger": ["☱","☲","☴"],
    "grow_vertical": ["▁","▃","▄","▅","▆","▇","▆","▅","▄","▃"],
    "grow_horizontal": ["▏","▎","▍","▌","▋","▊","▉","▊","▋","▌","▍","▎"],

    # ---- Neon / unique spinner sets -------------------------------------

    # Neon pulse — bubble swelling and shrinking.
    "pulse":      ["·","∘","○","◯","○","∘","·"," "],

    # Spark / flicker.
    "spark":      ["·","✦","★","✦","·"," "],

    # Thunder strike.
    "thunder":    ["⚡"," ","⚡","⚡⚡"," ","⚡"],

    # Diamond rotate.
    "diamond":    ["◇","◈","◆","◈"],

    # Sharp arrowhead spin (synthwave triangles).
    "wedges":     ["◢","◣","◤","◥"],

    # Hexagon roll.
    "hex":        ["⬡","⬢","⬡","⬢"],

    # Half-circle moon (text-only, 1-wide compatible).
    "moon_text":  ["◐","◓","◑","◒"],

    # Emoji moon phases (2-wide).
    "moon":       ["\U0001f311","\U0001f312","\U0001f313","\U0001f314","\U0001f315","\U0001f316","\U0001f317","\U0001f318"],

    # Weather rotation.
    "weather":    ["☀️","\U0001f324","⛅","\U0001f325","☁️","\U0001f326","\U0001f327","⛈️","\U0001f329"],

    # Rocket countdown.
    "rocket":     ["3","2","1","\U0001f680","✨","✨"],

    # Heartbeat.
    "heartbeat":  ["♡","♥","\U0001f497","♥","♡"],

    # Glitch noise.
    "glitch":     ["▓","▒","░","▒","▓","█","▓","▒"],

    # Loading dots growing.
    "loading":    [".  ", ".. ", "...", " ..", "  .", "   "],

    # ASCII spinner using slashes.
    "slash":      ["╱","─","╲","│"],

    # Caret march.
    "caret":      [">  ", " > ", "  >", "   ", "  <", " < ", "<  "],

    # Squares cycling fill.
    "square":     ["◰","◳","◲","◱"],

    # Pong ball bouncing inside brackets.
    "pong":       ["[●    ]","[ ●   ]","[  ●  ]","[   ● ]","[    ●]","[   ● ]","[  ●  ]","[ ●   ]"],
}


# ---- Compositional factories -------------------------------------------

def frame(*frames: str) -> list[str]:
    """Raw sequential frames. Shape-match for alive-progress's `frame_spinner_factory`."""
    return list(frames)


def scrolling(chars: str, length: int = 6, pad: str = " ") -> list[str]:
    """Slide `chars` through a window of `length`, pad outside."""
    if length <= 0:
        raise ValueError("length must be positive")
    padded = pad * length + chars + pad * length
    frames: list[str] = []
    for start in range(len(padded) - length + 1):
        frames.append(padded[start:start + length])
    return frames


def bouncing(chars: str, length: int = 6, pad: str = " ") -> list[str]:
    """Scroll `chars` across a window, then reverse."""
    forward = scrolling(chars, length=length, pad=pad)
    backward = list(reversed(forward[1:-1]))
    return forward + backward


def sequential(*specs: Sequence[str]) -> list[str]:
    """Concatenate several frame lists end-to-end."""
    out: list[str] = []
    for spec in specs:
        out.extend(spec)
    return out


def alongside(*specs: Sequence[str], sep: str = "") -> list[str]:
    """Run several animations side-by-side, stepping them together."""
    if not specs:
        return []
    n = max(len(s) for s in specs)
    frames: list[str] = []
    for i in range(n):
        frames.append(sep.join(s[i % len(s)] for s in specs))
    return frames


__all__ = [
    "SPINNERS", "frame", "scrolling", "bouncing", "sequential", "alongside",
]
