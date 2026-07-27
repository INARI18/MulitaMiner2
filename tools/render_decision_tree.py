"""Render the prioritization scoring card as an SVG, validated against the code.

The SSVC tree in mulitaminer.prioritization is equivalent to a points sum:

    exploitation (active 3 / likely,unknown 2 / none 1)
  + exposure     (exposed 1 / internal 0)
  + severity     (high 2 / medium 1 / low 0)

This script asserts that equivalence against the real _TREE and derives the
total -> category bands from it, so it cannot drift from the code: if anyone
edits the tree so that a total maps to two different categories, rendering
fails instead of drawing a lie.

    uv run python tools/render_decision_tree.py

Writes docs/imgs/priorization.svg.
"""
from pathlib import Path

from mulitaminer.prioritization import _TREE

BG = "#fbf6ef"
INK = "#2c2a27"
MUTED = "#9b8e7d"
BODY = "#6e655b"
ORANGE = "#e0572a"
CARD = "#fffdfa"
CARD_LINE = "#e8dccb"
RULE = "#e8dccb"
DARK = "#2c2a27"
DARK_TEXT = "#fbf6ef"
DARK_NOTE = "#a79c8e"
ON_ORANGE = "#fbddce"

SANS = ("font-family='Helvetica,ui-sans-serif,-apple-system,Segoe UI,Arial,"
        "sans-serif'")
MONO = "font-family='ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'"

W = 1320
PAD_X = 40
PAD_TOP = 44
PAD_BOTTOM = 40
GAP = 26

POINTS = {
    "exploitation": {"active": 3, "likely": 2, "unknown": 2, "none": 1},
    "exposure": {"exposed": 1, "internal": 0},
    "severity": {"high": 2, "medium": 1, "low": 0},
}

# (label, mono caption, [(value label, points, description)], extra note)
SIGNALS = [
    ("Exploitation", "kev · epss", [
        ("active", 3, "a CVE is in the KEV catalog"),
        ("likely · unknown", 2, "EPSS ≥ 0.10, or no CVE at all"),
        ("none", 1, "has a CVE, no evidence either way"),
    ], None),
    ("Exposure", "host", [
        ("exposed", 1, "anything not provably private"),
        ("internal", 0, "private IP, single-label or .local name"),
    ], "The heuristic can only move a finding to internal, never downgrade a "
       "public asset."),
    ("Severity", "cvss", [
        ("high", 2, "CVSS ≥ 7"),
        ("medium", 1, "CVSS ≥ 4"),
        ("low", 0, "CVSS below 4"),
    ], "Without a numeric CVSS the scanner label picks the band; unknown "
       "labels rank low and are reported."),
]

CATEGORY_NOTE = {
    "Act": "remediate now",
    "Attend": "supervised action soon",
    "Track*": "monitor, act if it worsens",
    "Track": "no action for now",
}

HEAD_NOTE = ("Add up one point value from each card below, then read the total "
             "on the scale: that is the finding's remediation category.")
EXAMPLE = ("active on an internal host, medium severity = 3 + 0 + 1 = 4, so "
           "Attend.")
ORDER = ("Category first, then EPSS descending, then CVSS descending. No CVE "
         "scores like likely: absence of a CVE is not evidence of safety.")
METRICS = [("3", "SIGNALS"), ("4", "CATEGORIES")]


def total_of(combo):
    expl, expo, sev = combo
    return (POINTS["exploitation"][expl] + POINTS["exposure"][expo]
            + POINTS["severity"][sev])


def bands_from_tree():
    """total -> category, asserted consistent with the real decision table."""
    by_total = {}
    for combo, category in _TREE.items():
        t = total_of(combo)
        if by_total.setdefault(t, category) != category:
            raise SystemExit(
                f"points model broke: total {t} maps to both "
                f"{by_total[t]} and {category} ({combo}). The tree changed; "
                f"update POINTS or drop this diagram.")
    return dict(sorted(by_total.items()))


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("'", "&#39;"))


def text(x, y, s, size, fill=INK, weight="normal", font=SANS, anchor="start",
         spacing=None):
    ls = f"letter-spacing='{spacing}' " if spacing else ""
    return (f"<text x='{x:g}' y='{y:g}' font-size='{size}' fill='{fill}' "
            f"font-weight='{weight}' text-anchor='{anchor}' {ls}{font} "
            f"dominant-baseline='middle'>{esc(s)}</text>")


def wrap(s, width_px, per_char=6.4):
    max_chars = max(8, int(width_px / per_char))
    lines, cur = [], ""
    for word in s.split():
        cand = f"{cur} {word}".strip()
        if len(cand) > max_chars and cur:
            lines.append(cur)
            cur = word
        else:
            cur = cand
    if cur:
        lines.append(cur)
    return lines


def chip_style(points, values):
    """Dark for the top value, outline for the bottom one, orange between."""
    if points == max(values):
        return DARK, DARK, DARK_TEXT
    if points == min(values):
        return CARD, CARD_LINE, BODY
    return ORANGE, ORANGE, "#ffffff"


def build():
    bands = bands_from_tree()
    p = [None]

    title_y = PAD_TOP + 16
    p.append(text(PAD_X, title_y, "PRIORITIZATION", 26, ORANGE, "bold", MONO,
                  spacing="5"))
    note_lines = wrap(HEAD_NOTE, 820, 7.0)
    for i, line in enumerate(note_lines):
        p.append(text(PAD_X, title_y + 30 + i * 19, line, 13.5, BODY, "normal",
                      SANS))
    head_bottom = title_y + 30 + 19 * len(note_lines)

    mx = W - PAD_X
    for value, label in reversed(METRICS):
        p.append(text(mx, head_bottom - 24, label, 11.5, MUTED, "normal", MONO,
                      "end", "1.1"))
        p.append(text(mx, head_bottom - 46, value, 15, INK, "bold", MONO, "end"))
        mx -= len(label) * 7.6 + 34

    rule_y = head_bottom + 8
    p.append(f"<line x1='{PAD_X}' y1='{rule_y}' x2='{W - PAD_X}' y2='{rule_y}' "
             f"stroke='{RULE}' stroke-width='1'/>")

    col_w = (W - 2 * PAD_X - 2 * GAP) / 3
    col_x = [PAD_X + i * (col_w + GAP) for i in range(3)]

    band_y = rule_y + 26
    for i, (label, _, _, _) in enumerate(SIGNALS):
        p.append(f"<line x1='{col_x[i]:g}' y1='{band_y}' "
                 f"x2='{col_x[i] + col_w:g}' y2='{band_y}' stroke='{ORANGE}' "
                 f"stroke-width='1'/>")
        p.append(text(col_x[i], band_y + 14, f"0{i + 1} · {label.upper()}",
                      10.5, ORANGE, "bold", MONO, spacing="1.7"))

    # Cards, all the same height ------------------------------------------
    pad = 18
    heights = []
    notes = []
    for _, _, rows, extra in SIGNALS:
        lines = wrap(extra, col_w - 2 * pad) if extra else []
        notes.append(lines)
        heights.append(2 * pad + 24 + 14 + len(rows) * 34 + (len(rows) - 1) * 8
                       + (14 + 17 * len(lines) if lines else 0))
    card_h = max(heights)
    card_y = band_y + 36

    for i, (label, caption, rows, _) in enumerate(SIGNALS):
        x = col_x[i]
        p.append(f"<rect x='{x:g}' y='{card_y}' width='{col_w:g}' "
                 f"height='{card_h}' rx='14' fill='{CARD}' "
                 f"stroke='{CARD_LINE}' stroke-width='1'/>")
        p.append(text(x + pad, card_y + pad + 12, label, 16.5, INK, "bold", SANS))
        p.append(text(x + col_w - pad, card_y + pad + 12, caption, 11, ORANGE,
                      "normal", MONO, "end"))
        values = [pts for _, pts, _ in rows]
        ry = card_y + pad + 24 + 14
        for value_label, pts, desc in rows:
            fill, stroke, fg = chip_style(pts, values)
            p.append(f"<rect x='{x + pad:g}' y='{ry:g}' width='34' height='34' "
                     f"rx='10' fill='{fill}' stroke='{stroke}' "
                     f"stroke-width='1'/>")
            p.append(text(x + pad + 17, ry + 17, str(pts), 15, fg, "bold", MONO,
                          "middle"))
            p.append(text(x + pad + 46, ry + 10, value_label, 14, INK, "bold",
                          SANS))
            p.append(text(x + pad + 46, ry + 26, desc, 12, MUTED, "normal", SANS))
            ry += 34 + 8
        for j, line in enumerate(notes[i]):
            p.append(text(x + pad, ry + 6 + j * 17, line, 12, MUTED, "normal",
                          SANS))

    # Total scale ----------------------------------------------------------
    label_w, scale_gap = 150, 12
    totals = list(bands)
    n = len(totals)
    slot_w = (W - 2 * PAD_X - label_w - n * scale_gap) / n
    slot_x = [PAD_X + label_w + scale_gap + i * (slot_w + scale_gap)
              for i in range(n)]

    scale_y = card_y + card_h + 34
    p.append(text(PAD_X, scale_y, "04 · TOTAL", 10.5, ORANGE, "bold", MONO,
                  spacing="1.7"))
    for i, t in enumerate(totals):
        p.append(text(slot_x[i] + slot_w / 2, scale_y, str(t), 18, INK, "bold",
                      MONO, "middle"))

    chip_y = scale_y + 20
    chip_h = 62
    p.append(text(PAD_X, chip_y + chip_h / 2, "signals summed", 12.5, MUTED,
                  "normal", SANS))
    i = 0
    while i < n:
        j = i
        while j + 1 < n and bands[totals[j + 1]] == bands[totals[i]]:
            j += 1
        category = bands[totals[i]]
        x0 = slot_x[i]
        x1 = slot_x[j] + slot_w
        if category == "Act":
            fill, stroke, fg, sub = DARK, DARK, DARK_TEXT, DARK_NOTE
        elif category == "Attend":
            fill, stroke, fg, sub = ORANGE, ORANGE, "#ffffff", ON_ORANGE
        elif category == "Track*":
            fill, stroke, fg, sub = CARD, ORANGE, ORANGE, MUTED
        else:
            fill, stroke, fg, sub = CARD, CARD_LINE, BODY, MUTED
        p.append(f"<rect x='{x0:g}' y='{chip_y}' width='{x1 - x0:g}' "
                 f"height='{chip_h}' rx='12' fill='{fill}' stroke='{stroke}' "
                 f"stroke-width='1'/>")
        p.append(text(x0 + 18, chip_y + 22, category, 17, fg, "bold", SANS))
        p.append(text(x0 + 18, chip_y + 42, CATEGORY_NOTE[category], 12.5, sub,
                      "normal", SANS))
        i = j + 1

    # Footnotes ------------------------------------------------------------
    foot_rule = chip_y + chip_h + 26
    p.append(f"<line x1='{PAD_X}' y1='{foot_rule}' x2='{W - PAD_X}' "
             f"y2='{foot_rule}' stroke='{RULE}' stroke-width='1'/>")
    y = foot_rule + 21
    for label, body in (("EXAMPLE", EXAMPLE), ("ORDER", ORDER)):
        p.append(text(PAD_X, y, label, 10.5, ORANGE, "bold", MONO,
                      spacing="1.7"))
        p.append(text(PAD_X + 100, y, body, 12.5, BODY, "normal", SANS))
        y += 22

    height = int(y + PAD_BOTTOM)
    p[0] = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' "
            f"height='{height}' viewBox='0 0 {W} {height}'>"
            f"<rect width='{W}' height='{height}' fill='{BG}'/>")
    p.append("</svg>")
    return "\n".join(p)


def main():
    out = Path("docs/imgs/priorization.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
