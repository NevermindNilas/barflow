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

# Type names `List` and `Sequence` used in signatures are deferred by
# `from __future__ import annotations` above, so importing them at runtime
# is unnecessary. Keeping this module's cold import tight.

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
}


# ---- Compositional factories -------------------------------------------

def frame(*frames: str) -> List[str]:
    """Raw sequential frames. Shape-match for alive-progress's `frame_spinner_factory`."""
    return list(frames)


def scrolling(chars: str, length: int = 6, pad: str = " ") -> List[str]:
    """Slide `chars` through a window of `length`, pad outside."""
    if length <= 0:
        raise ValueError("length must be positive")
    padded = pad * length + chars + pad * length
    frames: list[str] = []
    for start in range(len(padded) - length + 1):
        frames.append(padded[start:start + length])
    return frames


def bouncing(chars: str, length: int = 6, pad: str = " ") -> List[str]:
    """Scroll `chars` across a window, then reverse."""
    forward = scrolling(chars, length=length, pad=pad)
    backward = list(reversed(forward[1:-1]))
    return forward + backward


def sequential(*specs: Sequence[str]) -> List[str]:
    """Concatenate several frame lists end-to-end."""
    out: list[str] = []
    for spec in specs:
        out.extend(spec)
    return out


def alongside(*specs: Sequence[str], sep: str = "") -> List[str]:
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
