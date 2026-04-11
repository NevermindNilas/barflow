#!/usr/bin/env python3
"""Print the CHANGELOG.md section for a given version tag.

Usage: extract_changelog.py <tag>

The tag may be prefixed with 'v' (e.g. 'v0.2.1'); the leading 'v' is
stripped before matching. A matching section is one whose heading
looks like `## [0.2.1]` (Keep a Changelog format). Output is written
to stdout with the heading stripped so it can be used directly as a
GitHub release body.
"""

import pathlib
import re
import sys


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if len(sys.argv) != 2:
        print("usage: extract_changelog.py <tag>", file=sys.stderr)
        return 2

    tag = sys.argv[1].lstrip("v").strip()
    path = pathlib.Path("CHANGELOG.md")
    if not path.is_file():
        print("CHANGELOG.md not found", file=sys.stderr)
        return 1

    text = path.read_text(encoding="utf-8")
    pattern = re.compile(
        rf"^##\s*\[{re.escape(tag)}\][^\n]*\n(.*?)(?=^##\s*\[|\Z)",
        re.MULTILINE | re.DOTALL,
    )
    m = pattern.search(text)
    if not m:
        print(f"no changelog section for {tag}", file=sys.stderr)
        return 1

    sys.stdout.write(m.group(1).strip() + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
