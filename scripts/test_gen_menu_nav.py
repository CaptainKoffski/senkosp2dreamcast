#!/usr/bin/env python3
"""Self-check for gen_menu_assets.edit_nav(): the CUSTOM editor's spatial
cursor table (UP/DOWN/LEFT/RIGHT -> neighbouring chip, derived from the
chip anchors; no wrap). Run from repo root:
    python3 scripts/test_gen_menu_nav.py
"""
import os
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "scripts"))
import gen_menu_assets as g    # noqa: E402
import menu_def as M           # noqa: E402

UP, DOWN, LEFT, RIGHT = range(4)


def test_real_pad_page():
    # Pad page (build/preview_pad_*.png): L trigger alone in the left column,
    # the right column top-to-bottom R trigger, Y, B, A, X. MOVE/START carry
    # no chip. DOWN on L must NOT jump to the right column.
    nav = g.edit_nav(M.PAD_ANCHORS, M.PAD_BUTTONS)
    b = M.PAD_BUTTONS.index
    want = {
        "LTRIG": [None, None, None, b("RTRIG")],
        "RTRIG": [None, b("Y"), b("LTRIG"), None],
        "Y":     [b("RTRIG"), b("B"), b("LTRIG"), None],
        "B":     [b("Y"), b("A"), b("LTRIG"), None],
        "A":     [b("B"), b("X"), b("LTRIG"), None],
        "X":     [b("A"), None, b("LTRIG"), None],
    }
    for name, row in want.items():
        assert nav[b(name)] == row, f"{name}: {nav[b(name)]} != {row}"


def test_nearest_not_first():
    # Two chips to the right at the same x: pick the one on the same row.
    anchors = {"L": (0, 100), "R1": (500, 0), "R2": (500, 100)}
    nav = g.edit_nav(anchors, ["L", "R1", "R2"])
    assert nav[0][RIGHT] == 2
    assert nav[1][DOWN] == 2 and nav[2][UP] == 1
    assert nav[1][LEFT] == 0 and nav[2][LEFT] == 0


if __name__ == "__main__":
    test_real_pad_page()
    test_nearest_not_first()
    print("test_gen_menu_nav: PASS")
