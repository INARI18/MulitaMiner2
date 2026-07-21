"""Render the SSVC decision tree as an SVG, driven by the actual code tree.

Reads _TREE from mulitaminer.prioritization, so the diagram is correct by
construction and cannot drift from the logic. Regenerate after any tree change:

    uv run python tools/render_decision_tree.py

Writes docs/imgs/decision_tree.svg.
"""
from pathlib import Path

from mulitaminer.prioritization import _TREE

# Palette (dark theme, matches a security dashboard look).
BG = "#0d1117"
INK = "#e6edf3"
MUTED = "#8b949e"
COL = {"Act": "#d13438", "Attend": "#f0a020", "Track*": "#3a96dd", "Track": "#6e7681"}
EXPL = {"active": "#8957e5", "likely": "#388bfd", "none": "#484f58"}
EXPO = {"exposed": "#2ea043", "internal": "#1f6feb"}
SEV = {"high": "#d13438", "medium": "#f0a020", "low": "#bb8009"}

EXPL_LABEL = {"active": ("Active", "known"), "likely": ("Likely", "unknown"),
              "none": ("None", "no evidence")}
SEV_SHORT = {"high": "H", "medium": "M", "low": "L"}

# Layout grid.
X = {"finding": 40, "expl": 300, "expo": 560, "sev": 820, "act": 1120}
W = {"node": 150, "small": 92, "leaf": 150}
ROW_H = 46          # vertical spacing between severity leaves
TOP = 110
FONT = "font-family='Segoe UI, Helvetica, Arial, sans-serif'"


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def rrect(x, y, w, h, fill, stroke, rx=10, opacity=1.0):
    return (f"<rect x='{x}' y='{y}' width='{w}' height='{h}' rx='{rx}' "
            f"fill='{fill}' fill-opacity='{opacity}' stroke='{stroke}' stroke-width='1.5'/>")


def text(x, y, s, size=15, fill=INK, weight="normal", anchor="middle"):
    return (f"<text x='{x}' y='{y}' font-size='{size}' fill='{fill}' "
            f"font-weight='{weight}' text-anchor='{anchor}' {FONT} "
            f"dominant-baseline='middle'>{esc(s)}</text>")


def elbow(x1, y1, x2, y2, color):
    """Orthogonal connector: horizontal, vertical at the midpoint, horizontal."""
    mx = (x1 + x2) / 2
    return (f"<path d='M {x1} {y1} H {mx} V {y2} H {x2}' fill='none' "
            f"stroke='{color}' stroke-width='2' stroke-opacity='0.8'/>")


def build() -> str:
    # One severity leaf per (exploitation, exposure, severity), grouped so the
    # six (expl, expo) branches stack top to bottom, 3 severities each.
    combos = [(e, x, s) for e in ("active", "likely", "none")
              for x in ("exposed", "internal") for s in ("high", "medium", "low")]
    leaf_y = {c: TOP + i * ROW_H for i, c in enumerate(combos)}
    height = TOP + len(combos) * ROW_H + 40

    parts = [f"<svg xmlns='http://www.w3.org/2000/svg' width='1320' height='{height}' "
             f"viewBox='0 0 1320 {height}'>",
             f"<rect width='1320' height='{height}' fill='{BG}'/>"]

    # Column headers.
    for label, cx in (("1. Exploitation", X["expl"] + W["node"] / 2),
                      ("2. Exposure", X["expo"] + W["small"] / 2),
                      ("3. Severity", X["sev"] + W["small"] / 2),
                      ("4. Action", X["act"] + W["leaf"] / 2)):
        parts.append(text(cx, 60, label, size=17, fill="#a371f7", weight="bold"))

    # Finding root.
    fy = TOP + (len(combos) - 1) * ROW_H / 2
    parts.append(rrect(X["finding"], fy - 26, W["node"], 52, "#161b22", "#6e7681", rx=26))
    parts.append(text(X["finding"] + W["node"] / 2, fy, "Finding", size=17, weight="bold"))

    # Exploitation nodes (3), centered over their two exposure groups.
    expl_y = {}
    for e in ("active", "likely", "none"):
        rows = [c for c in combos if c[0] == e]
        cy = (leaf_y[rows[0]] + leaf_y[rows[-1]]) / 2
        expl_y[e] = cy
        parts.append(elbow(X["finding"] + W["node"], fy, X["expl"], cy, MUTED))
        parts.append(rrect(X["expl"], cy - 26, W["node"], 52, EXPL[e], EXPL[e], opacity=0.22))
        name, sub = EXPL_LABEL[e]
        parts.append(text(X["expl"] + W["node"] / 2, cy - 7, name, size=16, weight="bold"))
        parts.append(text(X["expl"] + W["node"] / 2, cy + 12, f"({sub})", size=12, fill=MUTED))

    # Exposure nodes (6).
    expo_y = {}
    for e in ("active", "likely", "none"):
        for x in ("exposed", "internal"):
            rows = [c for c in combos if c[0] == e and c[1] == x]
            cy = (leaf_y[rows[0]] + leaf_y[rows[-1]]) / 2
            expo_y[(e, x)] = cy
            parts.append(elbow(X["expl"] + W["node"], expl_y[e], X["expo"], cy, EXPL[e]))
            parts.append(rrect(X["expo"], cy - 22, W["small"], 44, EXPO[x], EXPO[x], opacity=0.28))
            parts.append(text(X["expo"] + W["small"] / 2, cy, x, size=14, weight="bold"))

    # Severity leaves (18) -> action nodes.
    for c in combos:
        e, x, s = c
        y = leaf_y[c]
        parts.append(elbow(X["expo"] + W["small"], expo_y[(e, x)], X["sev"], y, EXPO[x]))
        parts.append(rrect(X["sev"], y - 18, W["small"], 36, SEV[s], SEV[s], opacity=0.30))
        parts.append(text(X["sev"] + 22, y, SEV_SHORT[s], size=15, weight="bold"))
        parts.append(text(X["sev"] + 60, y, s, size=12, fill=MUTED))

    # Action nodes (4), centered over the leaves that point to them.
    for cat in ("Act", "Attend", "Track*", "Track"):
        members = [c for c in combos if _TREE[(_norm(c[0]), c[1], c[2])] == cat]
        ys = [leaf_y[c] for c in members]
        cy = sum(ys) / len(ys)
        for c in members:
            parts.append(elbow(X["sev"] + W["small"], leaf_y[c], X["act"], cy, SEV[c[2]]))
        top, bot = min(ys) - 22, max(ys) + 22
        parts.append(rrect(X["act"], top, W["leaf"], bot - top, COL[cat], COL[cat], opacity=0.9))
        parts.append(text(X["act"] + W["leaf"] / 2, (top + bot) / 2, cat, size=18,
                          fill="#ffffff", weight="bold"))

    # Legend.
    parts.append(text(60, height - 24,
                      "Diamonds are decisions; colored nodes are the SSVC action. "
                      "unknown (no CVE) follows the same branch as likely.",
                      size=12, fill=MUTED, anchor="start"))
    parts.append("</svg>")
    return "\n".join(parts)


def _norm(expl: str) -> str:
    # The tree keys use "active/likely/none/unknown"; the diagram merges
    # unknown into likely, so combos only ever pass those three.
    return expl


def main() -> None:
    # Sanity: the tree must cover every combo we draw.
    for e in ("active", "likely", "none"):
        for x in ("exposed", "internal"):
            for s in ("high", "medium", "low"):
                _TREE[(e, x, s)]
    out = Path("docs/imgs/decision_tree.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
