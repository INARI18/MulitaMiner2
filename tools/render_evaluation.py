"""Generate docs/imgs/evaluation.svg: how an extraction is scored against a baseline."""

from pathlib import Path

BG = "#fbf6ef"
INK = "#2c2a27"
MUTED = "#9b8e7d"
BODY = "#6e655b"
ORANGE = "#e0572a"
CARD = "#fffdfa"
CARD_LINE = "#e8dccb"
RULE = "#e8dccb"
RULE_SOFT = "#dccdb7"
DARK = "#2c2a27"
DARK_TITLE = "#fbf6ef"
DARK_SUB = "#f19267"
CHIP_S = "#f4e9db"
CHIP_T = "#fbebe1"
GROUP = "#a2937f"

SANS = ("font-family='Helvetica,ui-sans-serif,-apple-system,Segoe UI,Arial,"
        "sans-serif'")
MONO = "font-family='ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'"

W = 1320
PAD_X = 40
PAD_TOP = 44
PAD_BOTTOM = 40
GAP = 26

# 1fr 1fr 1fr 1.15fr
FR = [1, 1, 1, 1.15]
UNIT = (W - 2 * PAD_X - 3 * GAP) / sum(FR)
COL_W = [f * UNIT for f in FR]
COL_X = []
_x = PAD_X
for _w in COL_W:
    COL_X.append(_x)
    _x += _w + GAP

PHASES = ["01 · INPUT", "02 · ALIGN", "03 · OUTCOME", "04 · SCORE"]
ACCENT_PHASE = 1

METRICS = [("1:1", "PAIRING"), ("0.70", "MATCH CUTOFF")]

STRUCTURAL = ["exact", "set_f1", "set_f1_ids", "structural"]
TEXT_METRICS = ["token_f1", "rouge_l", "bertscore", "nli"]

FOOT = ("recall = matched / baseline rows · precision = matched / extracted "
        "records. Alignment fidelity, not invention: the finding count is fixed "
        "before any LLM call.")

ICONS = {
    "braces": ["M9 4c-3 0-1 7-4 8 3 1 1 8 4 8", "M15 4c3 0 1 7 4 8-3 1-1 8-4 8",
               "@circle cx='12' cy='12' r='1.3'"],
    "sheet": ["@rect x='3' y='4' width='18' height='16' rx='2'", "M3 9h18M9 9v11"],
    "merge": ["M3 6h3c5 0 5 6 10 6", "M3 18h3c5 0 5-6 10-6", "M17 9l3 3-3 3"],
    "pairs": ["M4 7h6M4 17h6", "M14 7h6M14 17h6", "M10 7c2 0 2 10 4 10",
              "M10 17c2 0 2-10 4-10"],
    "fp": ["@rect x='3' y='4' width='12' height='14' rx='2'", "M17 9h4v11H9",
           "M6 9l6 6M12 9l-6 6"],
    "fn": ["@rect x='3' y='4' width='18' height='16' rx='2'", "M3 9h18", "M8 14h8"],
    "bars": ["M4 20V10M10 20V4M16 20v-7M22 20H2"],
}


def esc(s):
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
             .replace("'", "&#39;"))


def text(x, y, s, size, fill=INK, weight="normal", font=SANS, anchor="start",
         spacing=None):
    ls = f"letter-spacing='{spacing}' " if spacing else ""
    return (f"<text x='{x:g}' y='{y:g}' font-size='{size}' fill='{fill}' "
            f"font-weight='{weight}' text-anchor='{anchor}' {ls}{font} "
            f"dominant-baseline='middle'>{esc(s)}</text>")


def icon(kind, x, y, stroke=ORANGE, size=24):
    k = size / 24
    out = [f"<g transform='translate({x:g},{y:g}) scale({k:g})' stroke='{stroke}' "
           f"stroke-width='1.7' fill='none' stroke-linecap='round' "
           f"stroke-linejoin='round'>"]
    for d in ICONS[kind]:
        if d.startswith("@circle"):
            out.append(f"<circle {d[7:]} fill='{stroke}'/>")
        elif d.startswith("@rect"):
            out.append(f"<rect {d[5:]}/>")
        else:
            out.append(f"<path d='{d}'/>")
    out.append("</g>")
    return "".join(out)


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


def chevron(x, y, out):
    out.append(f"<path d='M {x:g} {y - 4.5:g} L {x + 6.5:g} {y:g} "
               f"L {x:g} {y + 4.5:g}' fill='none' stroke='{ORANGE}' "
               f"stroke-width='2' stroke-linecap='round' "
               f"stroke-linejoin='round'/>")


def card(out, x, y, w, title, sub, notes, ic, dark=False, pad=16, gap=7,
         accent=False):
    """Draw a card; returns its height."""
    body = wrap(notes, w - 2 * pad) if notes else []
    h = 2 * pad + 24 + gap + 14 + (gap + 17 * len(body) if body else 0)
    fill = DARK if dark else CARD
    stroke = DARK if dark else (ORANGE if accent else CARD_LINE)
    out.append(f"<rect x='{x:g}' y='{y:g}' width='{w:g}' height='{h:g}' rx='14' "
               f"fill='{fill}' stroke='{stroke}' stroke-width='1'/>")
    out.append(text(x + pad, y + pad + 12, title, 16.5,
                    DARK_TITLE if dark else INK, "bold", SANS))
    out.append(icon(ic, x + w - pad - 24, y + pad,
                    DARK_SUB if dark else ORANGE))
    sy = y + pad + 24 + gap + 7
    out.append(text(x + pad, sy, sub, 11, DARK_SUB if dark else ORANGE,
                    "normal", MONO))
    for j, line in enumerate(body):
        out.append(text(x + pad, sy + 7 + gap + 8 + j * 17, line, 12.5, MUTED,
                        "normal", SANS))
    return h


def chips(out, x, y, items, bg):
    """Row of mono chips; returns height."""
    cx = x
    for it in items:
        cw = len(it) * 6.7 + 16
        out.append(f"<rect x='{cx:g}' y='{y:g}' width='{cw:g}' height='22' "
                   f"rx='6' fill='{bg}'/>")
        out.append(text(cx + 8, y + 11, it, 11, BODY, "normal", MONO))
        cx += cw + 6
    return 22


def build():
    p = [None]

    title_y = PAD_TOP + 16
    p.append(text(PAD_X, title_y, "EVALUATION", 26, ORANGE, "bold", MONO,
                  spacing="5"))
    mx = W - PAD_X
    for value, label in reversed(METRICS):
        p.append(text(mx, title_y + 20, label, 11.5, MUTED, "normal", MONO,
                      "end", "1.1"))
        p.append(text(mx, title_y - 2, value, 15, INK, "bold", MONO, "end"))
        mx -= len(label) * 7.6 + 34

    rule_y = PAD_TOP + 48
    p.append(f"<line x1='{PAD_X}' y1='{rule_y}' x2='{W - PAD_X}' y2='{rule_y}' "
             f"stroke='{RULE}' stroke-width='1'/>")

    band_y = rule_y + 26
    for i, label in enumerate(PHASES):
        accent = i == ACCENT_PHASE
        p.append(f"<line x1='{COL_X[i]:g}' y1='{band_y}' "
                 f"x2='{COL_X[i] + COL_W[i]:g}' y2='{band_y}' "
                 f"stroke='{ORANGE if accent else RULE_SOFT}' stroke-width='1'/>")
        p.append(text(COL_X[i], band_y + 14, label, 10.5,
                      ORANGE if accent else MUTED,
                      "bold" if accent else "normal", MONO, spacing="1.7"))

    top = band_y + 36
    bottoms = []

    # 01 inputs -----------------------------------------------------------
    y = top
    h1 = card(p, COL_X[0], y, COL_W[0], "Extraction", "results.json",
              "One record per finding block.", "braces")
    y2 = y + h1 + 14
    h2 = card(p, COL_X[0], y2, COL_W[0], "Baseline", "baseline.xlsx",
              "Gold standard, one row per finding.", "sheet")
    col1_bottom = y2 + h2
    bottoms.append(col1_bottom)
    chevron(COL_X[0] + COL_W[0] + 9, (top + col1_bottom) / 2, p)

    # 02 alignment --------------------------------------------------------
    x, w, pad = COL_X[1], COL_W[1], 16
    blocks = [
        ("Hungarian 1-to-1 assignment over the score matrix.", BODY),
        ("Pairs below 0.70 are cut.", BODY),
        ("Conflicting keys penalize the name score, so two findings on "
         "different ports do not pair by accident.", MUTED),
    ]
    wrapped = [(wrap(t, w - 2 * pad), c) for t, c in blocks]
    body_h = sum(17 * len(ls) for ls, _ in wrapped) + 8 * (len(wrapped) - 1)
    h = 2 * pad + 24 + 12 + 14 + 12 + body_h
    p.append(f"<rect x='{x:g}' y='{top}' width='{w:g}' height='{h:g}' rx='14' "
             f"fill='{CARD}' stroke='{ORANGE}' stroke-width='1'/>")
    p.append(text(x + pad, top + pad + 12, "Alignment", 16.5, INK, "bold", SANS))
    p.append(icon("merge", x + w - pad - 24, top + pad))
    p.append(text(x + pad, top + pad + 24 + 12 + 7, "composite key + fuzzy name",
                  11, ORANGE, "normal", MONO))
    ty = top + pad + 24 + 12 + 14 + 12 + 8
    for lines, col in wrapped:
        for line in lines:
            p.append(text(x + pad, ty, line, 12.5, col, "normal", SANS))
            ty += 17
        ty += 8
    bottoms.append(top + h)
    chevron(x + w + 9, top + h / 2, p)

    # 03 outcomes ---------------------------------------------------------
    x, w = COL_X[2], COL_W[2]
    y = top
    hm = card(p, x, y, w, "Matched pairs", "scored per field", None, "pairs",
              dark=True, pad=14, gap=6)
    matched_mid = y + hm / 2
    y += hm + 12
    y += card(p, x, y, w, "False positives", "invention · duplicate",
              "Closest baseline row kept for context.", "fp", pad=14, gap=6) + 12
    y += card(p, x, y, w, "False negatives", "unrecovered",
              "Baseline rows with no extracted match.", "fn", pad=14, gap=6)
    bottoms.append(y)
    chevron(x + w + 9, matched_mid, p)

    # 04 per-field metrics -------------------------------------------------
    x, w, pad = COL_X[3], COL_W[3], 16
    note = wrap("Only matched pairs are scored. Metric follows the field type.",
                w - 2 * pad)
    h = 2 * pad + 24 + 14 + (13 + 8 + 22) + 14 + (13 + 8 + 22) + 14 + 17 * len(note)
    p.append(f"<rect x='{x:g}' y='{top}' width='{w:g}' height='{h:g}' rx='14' "
             f"fill='{CARD}' stroke='{CARD_LINE}' stroke-width='1'/>")
    p.append(text(x + pad, top + pad + 12, "Per-field metrics", 16.5, INK,
                  "bold", SANS))
    p.append(icon("bars", x + w - pad - 24, top + pad))
    gy = top + pad + 24 + 14
    for label, items, bg in (("STRUCTURAL", STRUCTURAL, CHIP_S),
                             ("TEXT", TEXT_METRICS, CHIP_T)):
        p.append(text(x + pad, gy + 6, label, 10, GROUP, "normal", MONO,
                      spacing="1.6"))
        chips(p, x + pad, gy + 13 + 8, items, bg)
        gy += 13 + 8 + 22 + 14
    for j, line in enumerate(note):
        p.append(text(x + pad, gy + 8 + j * 17, line, 12.5, MUTED, "normal", SANS))
    bottoms.append(top + h)

    # Footer ---------------------------------------------------------------
    foot_rule = max(bottoms) + 26
    p.append(f"<line x1='{PAD_X}' y1='{foot_rule}' x2='{W - PAD_X}' "
             f"y2='{foot_rule}' stroke='{RULE}' stroke-width='1'/>")
    foot_y = foot_rule + 21
    p.append(text(PAD_X, foot_y, "COVERAGE", 10.5, ORANGE, "bold", MONO,
                  spacing="1.7"))
    p.append(text(PAD_X + 92, foot_y, FOOT, 12.5, BODY, "normal", SANS))

    height = int(foot_y + 10 + PAD_BOTTOM)
    p[0] = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' "
            f"height='{height}' viewBox='0 0 {W} {height}'>"
            f"<rect width='{W}' height='{height}' fill='{BG}'/>")
    p.append("</svg>")
    return "\n".join(p)


def main():
    out = Path("docs/imgs/evaluation.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
