"""Render the SSVC decision tree as an SVG, driven by the actual code tree.

Reads _TREE from mulitaminer.prioritization, so the diagram is correct by
construction and cannot drift from the logic. Regenerate after any tree change:

    uv run python tools/render_decision_tree.py

Writes docs/imgs/decision_tree.svg. The style matches the MulitaMiner brand
(warm cream background, orange accent, charcoal text, monospace labels).
"""
from pathlib import Path

from mulitaminer.prioritization import _TREE

# --- MulitaMiner palette ---
BG = "#fbf6ef"
INK = "#2c2a27"
MUTED = "#9b8e7d"
ORANGE = "#e0572a"
CARD = "#f4e9db"
CARD_LINE = "#e6d6c1"
LINK = "#d8c4ac"

# Action (urgency) colors, warm-compatible.
COL = {"Act": "#cf4a34", "Attend": "#e08a2b", "Track*": "#4c86a6", "Track": "#a3917c"}
# Exploitation accents.
EXPL_C = {"active": "#cf4a34", "likely": "#e08a2b", "none": "#a3917c"}
# Severity tint (small chips).
SEV_C = {"high": "#cf4a34", "medium": "#e08a2b", "low": "#b09a80"}

EXPL_LABEL = {"active": ("Active", "known"), "likely": ("Likely", "unknown"),
              "none": ("None", "no evidence")}
SEV_SHORT = {"high": "H", "medium": "M", "low": "L"}

X = {"finding": 44, "expl": 300, "expo": 566, "sev": 826, "act": 1120}
W = {"node": 150, "small": 96, "leaf": 150}
ROW_H = 46
TOP = 118
SANS = ("font-family='ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,"
        "sans-serif'")
MONO = "font-family='ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rrect(x, y, w, h, fill, stroke, rx=12, sw=1.5):
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' stroke='{stroke}' stroke-width='{sw}'/>")


def text(x, y, s, size=15, fill=INK, weight="normal", anchor="middle", font=SANS,
         spacing=None):
    ls = f"letter-spacing='{spacing}' " if spacing else ""
    return (f"<text x='{x}' y='{y}' font-size='{size}' fill='{fill}' "
            f"font-weight='{weight}' text-anchor='{anchor}' {ls}{font} "
            f"dominant-baseline='middle'>{esc(s)}</text>")


def elbow(x1, y1, x2, y2, color, width=1.6):
    mx = (x1 + x2) / 2
    return (f"<path d='M {x1} {y1} H {mx} V {y2} H {x2}' fill='none' "
            f"stroke='{color}' stroke-width='{width}'/>")


def build() -> str:
    combos = [(e, x, s) for e in ("active", "likely", "none")
              for x in ("exposed", "internal") for s in ("high", "medium", "low")]
    leaf_y = {c: TOP + i * ROW_H for i, c in enumerate(combos)}
    height = TOP + len(combos) * ROW_H + 44

    p = [f"<svg xmlns='http://www.w3.org/2000/svg' width='1300' height='{height}' "
         f"viewBox='0 0 1300 {height}'>",
         f"<rect width='1300' height='{height}' fill='{BG}'/>"]

    # Column headers (monospace, orange, spaced — the deck's caption style).
    for label, cx in (("1 · EXPLOITATION", X["expl"] + W["node"] / 2),
                      ("2 · EXPOSURE", X["expo"] + W["small"] / 2),
                      ("3 · SEVERITY", X["sev"] + W["small"] / 2),
                      ("4 · ACTION", X["act"] + W["leaf"] / 2)):
        p.append(text(cx, 54, label, size=13, fill=ORANGE, weight="bold",
                      font=MONO, spacing="1.5"))

    # Root.
    fy = TOP + (len(combos) - 1) * ROW_H / 2
    p.append(rrect(X["finding"], fy - 24, W["node"], 48, CARD, CARD_LINE, rx=24))
    p.append(text(X["finding"] + W["node"] / 2, fy, "Finding", size=16, weight="bold"))

    # Exploitation.
    expl_y = {}
    for e in ("active", "likely", "none"):
        rows = [c for c in combos if c[0] == e]
        cy = (leaf_y[rows[0]] + leaf_y[rows[-1]]) / 2
        expl_y[e] = cy
        p.append(elbow(X["finding"] + W["node"], fy, X["expl"], cy, LINK))
        p.append(rrect(X["expl"], cy - 25, W["node"], 50, CARD, CARD_LINE))
        p.append(f"<rect x='{X['expl']}' y='{cy - 25}' width='5' height='50' "
                 f"rx='2' fill='{EXPL_C[e]}'/>")
        name, sub = EXPL_LABEL[e]
        p.append(text(X["expl"] + W["node"] / 2 + 4, cy - 7, name, size=16, weight="bold"))
        p.append(text(X["expl"] + W["node"] / 2 + 4, cy + 11, sub, size=11.5, fill=MUTED,
                      font=MONO))

    # Exposure.
    expo_y = {}
    for e in ("active", "likely", "none"):
        for x in ("exposed", "internal"):
            rows = [c for c in combos if c[0] == e and c[1] == x]
            cy = (leaf_y[rows[0]] + leaf_y[rows[-1]]) / 2
            expo_y[(e, x)] = cy
            p.append(elbow(X["expl"] + W["node"], expl_y[e], X["expo"], cy, LINK))
            p.append(rrect(X["expo"], cy - 21, W["small"], 42, CARD, CARD_LINE))
            p.append(text(X["expo"] + W["small"] / 2, cy, x, size=13.5, weight="bold"))

    # Severity chips -> actions.
    for c in combos:
        e, x, s = c
        y = leaf_y[c]
        p.append(elbow(X["expo"] + W["small"], expo_y[(e, x)], X["sev"], y, LINK))
        p.append(rrect(X["sev"], y - 17, W["small"], 34, CARD, CARD_LINE, rx=9))
        p.append(f"<circle cx='{X['sev'] + 20}' cy='{y}' r='9' fill='{SEV_C[s]}'/>")
        p.append(text(X["sev"] + 20, y, SEV_SHORT[s], size=12, fill="#fff", weight="bold"))
        p.append(text(X["sev"] + 40, y, s, size=12, fill=MUTED, anchor="start", font=MONO))

    # Action nodes: four fixed-size chips, evenly spaced. Categories are not
    # contiguous in the leaf order, so each chip sits at its own slot and the
    # leaf edges converge to it.
    cats = ("Act", "Attend", "Track*", "Track")
    span = (len(combos) - 1) * ROW_H
    chip_h = 56
    act_y = {cat: TOP + span * (i + 0.5) / len(cats) for i, cat in enumerate(cats)}
    for cat in cats:
        cy = act_y[cat]
        for c in [c for c in combos if _TREE[c] == cat]:
            p.append(elbow(X["sev"] + W["small"], leaf_y[c], X["act"], cy, COL[cat], 1.6))
    for cat in cats:  # draw chips last so edges tuck under them
        cy = act_y[cat]
        p.append(rrect(X["act"], cy - chip_h / 2, W["leaf"], chip_h, COL[cat], COL[cat], rx=14))
        p.append(text(X["act"] + W["leaf"] / 2, cy, cat, size=18, fill="#fff", weight="bold"))

    p.append(text(X["finding"], height - 22,
                  "unknown (no CVE) follows the same branch as likely — absence of a "
                  "CVE is not evidence of safety.",
                  size=12, fill=MUTED, anchor="start", font=MONO))
    p.append("</svg>")
    return "\n".join(p)


def main() -> None:
    for e in ("active", "likely", "none"):
        for x in ("exposed", "internal"):
            for s in ("high", "medium", "low"):
                _TREE[(e, x, s)]  # coverage sanity
    out = Path("docs/imgs/decision_tree.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
