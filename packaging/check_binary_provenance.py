"""Reject binaries PyInstaller resolved from unrelated PATH tools.

The exact source paths come from PyInstaller's Analysis-00.toc. This check is
about build provenance, not a substitute for a third-party license audit.
"""
from __future__ import annotations

import ast
from pathlib import Path
import sys


def main(args: list[str]) -> int:
    if len(args) not in (4, 5):
        print("usage: check_binary_provenance.py ANALYSIS VENV PYTHON_BASE [MPV_DLL]", file=sys.stderr)
        return 2
    analysis = Path(args[1]).resolve()
    roots = [Path(args[2]).resolve(), Path(args[3]).resolve(),
             Path(__import__("os").environ["SystemRoot"]).resolve()]
    mpv_dll = Path(args[4]).resolve() if len(args) == 5 else None
    data = ast.literal_eval(analysis.read_text(encoding="utf-8"))
    binaries: list[tuple[str, Path]] = []

    def walk(value):
        if isinstance(value, (tuple, list)):
            if (len(value) == 3 and value[2] == "BINARY"
                    and isinstance(value[0], str) and isinstance(value[1], str)):
                binaries.append((value[0], Path(value[1]).resolve()))
            else:
                for child in value:
                    walk(child)

    walk(data)
    if not binaries:
        raise RuntimeError("No PyInstaller binary entries found; analysis format changed")
    unexpected = [(name, source) for name, source in binaries
                  if not any(source.is_relative_to(root) for root in roots)
                  and source != mpv_dll]
    if unexpected:
        for name, source in unexpected:
            print(f"Unexpected binary source: {name} <- {source}", file=sys.stderr)
        return 1
    print(f"Verified {len(binaries)} binary source paths")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
