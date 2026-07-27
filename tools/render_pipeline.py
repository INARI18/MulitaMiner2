"""Render the pipeline diagram as an SVG in the MulitaMiner brand style.

The pipeline is a fixed sequence, so stages are listed here (not derived from
code). Regenerate after a stage change:

    uv run python tools/render_pipeline.py

Writes docs/imgs/pipeline.svg.
"""
from pathlib import Path

BG = "#fbf6ef"
INK = "#2c2a27"
MUTED = "#9b8e7d"
ORANGE = "#e0572a"
CARD = "#fffdfa"
CARD_LINE = "#e8dccb"
RULE = "#e8dccb"
RULE_SOFT = "#dccdb7"
BRANCH_LINE = "#d6c6b0"
BRANCH_LABEL = "#a2937f"
DARK = "#2c2a27"
DARK_TITLE = "#fbf6ef"
DARK_SUB = "#f19267"
DARK_NOTE = "#a79c8e"

SANS = ("font-family='Helvetica,ui-sans-serif,-apple-system,Segoe UI,Arial,"
        "sans-serif'")
MONO = "font-family='ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'"

# (title, mono caption, note, icon)
STAGES = [
    ("PDF", "input", "Scanner report goes in.", "page"),
    ("Extract text", "pdf_reader", "Clean text out of the PDF.", "search"),
    ("Split blocks", "block-anchored", "One block per finding, fixed count.", "blocks"),
    ("Pack chunks", "chunking", "Whole blocks, token budgeted.", "chunk"),
    ("LLM extract", "fills fields", "Model fills each block's fields.", "spark"),
    ("Consolidate", "pair · dedup", "Pair, normalize, merge duplicates.", "merge"),
    ("results.json", "primary output", "Structured records, main artifact.", "braces"),
    ("Exports", "optional", "SARIF, CSAF, CSV, XLSX.", "files"),
]

PHASES = [  # (label, first stage index, last stage index, accented?)
    ("01 · INGEST", 0, 0, False),
    ("02 · IN MEMORY", 1, 5, True),
    ("03 · PERSIST", 6, 7, False),
]

DARK_CARD = 6        # results.json is the persisted artifact
BRANCH_FROM = 6      # optional evaluation branch hangs off results.json
BRANCH_LABEL_TEXT = "EVALUATION"
BRANCH_NOTE = ("Scores results.json against a ground-truth baseline: "
               "coverage + per-field metrics.")
IN_MEMORY = (1, 5)   # cards drawn with the accent border
RETRY = (4, 3)       # LLM extract loops failed blocks back to Pack chunks
RETRY_LABEL_TEXT = "↻ RETRY 5 → 4"
RETRY_NOTE = ("Failed blocks are re-packed into smaller chunks and "
              "extracted again.")

W = 1320
PAD_X = 40
PAD_TOP = 44
PAD_BOTTOM = 40
GAP = 26
N = len(STAGES)
CARD_W = (W - 2 * PAD_X - (N - 1) * GAP) / N
CARD_H = 156
PITCH = CARD_W + GAP

METRICS = [("8", "STAGES"), ("3", "PHASES"), ("1", "RETRY PATH")]

ICONS = {
    "page": [("path", "M6 3h8l4 4v14H6z"), ("path", "M14 3v4h4"),
             ("path", "M9 12h6M9 16h6")],
    "search": [("path", "M5 3h7l3 3v6"), ("path", "M5 3v18h5"),
               ("path", "M7 8h5M7 12h4"),
               ("circle", "cx='16' cy='16' r='4'"), ("path", "M19 19l3 3")],
    "blocks": [("rect", "x='3' y='4' width='12' height='5' rx='1.5'"),
               ("rect", "x='7' y='11' width='14' height='5' rx='1.5'"),
               ("rect", "x='3' y='18' width='12' height='3' rx='1.5'")],
    "chunk": [("path", "M6 4H3v16h3"), ("path", "M18 4h3v16h-3"),
              ("rect", "x='8' y='7' width='8' height='4' rx='1.2'"),
              ("rect", "x='8' y='13' width='8' height='4' rx='1.2'")],
    "spark": [("path", "M10 3c1.6 5.2 1.8 5.4 7 7-5.2 1.6-5.4 1.8-7 7"
                       "-1.6-5.2-1.8-5.4-7-7 5.2-1.6 5.4-1.8 7-7z"),
              ("fillpath", "M18.5 14.5l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1"
                           "-2.1-.9 2.1-.9z")],
    "merge": [("path", "M3 6h3c5 0 5 6 10 6"), ("path", "M3 18h3c5 0 5-6 10-6"),
              ("path", "M17 9l3 3-3 3")],
    "braces": [("path", "M9 4c-3 0-1 7-4 8 3 1 1 8 4 8"),
               ("path", "M15 4c3 0 1 7 4 8-3 1-1 8-4 8"),
               ("fillcircle", "cx='12' cy='12' r='1.3'")],
    "files": [("path", "M11 3h6l3 3v11h-9z"),
              ("bgpath", "M4 7h6l3 3v11H4z"), ("path", "M4 7h6l3 3v11H4z")],
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


def icon(kind, x, y, stroke=ORANGE, box_fill=CARD, size=26):
    """24x24 line icon, top-left at (x, y), scaled to `size`."""
    k = size / 24
    out = [f"<g transform='translate({x:g},{y:g}) scale({k:g})' stroke='{stroke}' "
           f"stroke-width='1.7' fill='none' stroke-linecap='round' "
           f"stroke-linejoin='round'>"]
    for kind_, d in ICONS[kind]:
        if kind_ == "path":
            out.append(f"<path d='{d}'/>")
        elif kind_ == "fillpath":
            out.append(f"<path d='{d}' fill='{stroke}'/>")
        elif kind_ == "bgpath":
            out.append(f"<path d='{d}' fill='{box_fill}'/>")
        elif kind_ == "rect":
            out.append(f"<rect {d}/>")
        elif kind_ == "circle":
            out.append(f"<circle {d}/>")
        elif kind_ == "fillcircle":
            out.append(f"<circle {d} fill='{stroke}'/>")
    out.append("</g>")
    return "".join(out)


def wrap(s, max_chars):
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


def build():
    p = [None]  # svg opening tag is filled in once the height is known

    # Header ---------------------------------------------------------------
    title_y = PAD_TOP + 16
    p.append(text(PAD_X, title_y, "PIPELINE", 26, ORANGE, "bold", MONO,
                  spacing="5"))

    mx = W - PAD_X
    for value, label in reversed(METRICS):
        label_w = len(label) * 7.6
        p.append(text(mx, title_y + 20, label, 11.5, MUTED, "normal", MONO,
                      "end", "1.1"))
        p.append(text(mx, title_y - 2, value, 15, INK, "bold", MONO, "end"))
        mx -= label_w + 34

    rule_y = PAD_TOP + 48
    p.append(f"<line x1='{PAD_X}' y1='{rule_y}' x2='{W - PAD_X}' y2='{rule_y}' "
             f"stroke='{RULE}' stroke-width='1'/>")

    xs = [PAD_X + i * PITCH for i in range(N)]

    # Phase bands ----------------------------------------------------------
    band_y = rule_y + 26
    for label, first, last, accent in PHASES:
        x0, x1 = xs[first], xs[last] + CARD_W
        col = ORANGE if accent else RULE_SOFT
        p.append(f"<line x1='{x0:g}' y1='{band_y}' x2='{x1:g}' y2='{band_y}' "
                 f"stroke='{col}' stroke-width='1'/>")
        p.append(text(x0, band_y + 14, label, 10.5,
                      ORANGE if accent else MUTED,
                      "bold" if accent else "normal", MONO, spacing="1.7"))

    # Cards ----------------------------------------------------------------
    card_y = band_y + 36
    cb = card_y + CARD_H
    for i, (title, sub, note, ic) in enumerate(STAGES):
        x = xs[i]
        dark = i == DARK_CARD
        fill = DARK if dark else CARD
        stroke = DARK if dark else (
            ORANGE if IN_MEMORY[0] <= i <= IN_MEMORY[1] else CARD_LINE)
        p.append(f"<rect x='{x:g}' y='{card_y}' width='{CARD_W:g}' "
                 f"height='{CARD_H}' rx='14' fill='{fill}' stroke='{stroke}' "
                 f"stroke-width='1'/>")
        p.append(f"<circle cx='{x + 28:g}' cy='{card_y + 28}' r='12' "
                 f"fill='{ORANGE}'/>")
        p.append(text(x + 28, card_y + 28, str(i + 1), 12, "#fff", "bold",
                      MONO, "middle"))
        p.append(icon(ic, x + CARD_W - 16 - 26, card_y + 16,
                      DARK_SUB if dark else ORANGE, fill))

        lines = wrap(note, int((CARD_W - 32) / 6.1))
        bottom = card_y + CARD_H - 18
        for j, line in enumerate(reversed(lines)):
            p.append(text(x + 16, bottom - 8 - j * 17, line, 12,
                          DARK_NOTE if dark else MUTED, "normal", SANS))
        sub_y = bottom - 17 * len(lines) - 8
        p.append(text(x + 16, sub_y, sub, 11, DARK_SUB if dark else ORANGE,
                      "normal", MONO))
        p.append(text(x + 16, sub_y - 24, title, 16.5,
                      DARK_TITLE if dark else INK, "bold", SANS))

        if i < N - 1:
            ax, mid = x + CARD_W, card_y + CARD_H / 2
            p.append(f"<path d='M {ax + 8:g} {mid - 4.5:g} L {ax + 14.5:g} "
                     f"{mid:g} L {ax + 8:g} {mid + 4.5:g}' fill='none' "
                     f"stroke='{ORANGE}' stroke-width='2' "
                     f"stroke-linecap='round' stroke-linejoin='round'/>")

    # Annotation band: retry and evaluation boxes share one level under the
    # cards, so the space below stages 1-6 is not left empty.
    box_top = cb + 26

    def ann_box(x0, x1, label, note, line_col, label_col, box_h):
        p.append(f"<rect x='{x0:g}' y='{box_top}' width='{x1 - x0:g}' "
                 f"height='{box_h}' rx='12' fill='none' stroke='{line_col}' "
                 f"stroke-width='1' stroke-dasharray='4 4'/>")
        p.append(text(x0 + 16, box_top + 12 + 6, label, 10,
                      label_col, "bold" if label_col == ORANGE else "normal",
                      MONO, spacing="1.6"))
        for j, line in enumerate(wrap(note, int((x1 - x0 - 32) / 6.4))):
            p.append(text(x0 + 16, box_top + 12 + 13 + 6 + 8 + j * 17, line,
                          12.5, MUTED, "normal", SANS))

    rx0, rx1 = xs[RETRY[1]], xs[RETRY[0]] + CARD_W
    bx0, bx1 = xs[BRANCH_FROM], xs[N - 1] + CARD_W
    r_lines = wrap(RETRY_NOTE, int((rx1 - rx0 - 32) / 6.4))
    b_lines = wrap(BRANCH_NOTE, int((bx1 - bx0 - 32) / 6.4))
    box_h = 12 + 13 + 6 + 17 * max(len(r_lines), len(b_lines)) + 12

    # Retry: failed blocks leave LLM extract (5) and re-enter Pack chunks (4).
    xf = xs[RETRY[0]] + CARD_W / 2
    xt = xs[RETRY[1]] + CARD_W / 2
    p.append(f"<line x1='{xf:g}' y1='{cb}' x2='{xf:g}' y2='{box_top}' "
             f"stroke='{ORANGE}' stroke-width='2' stroke-dasharray='4 4'/>")
    p.append(f"<line x1='{xt:g}' y1='{box_top}' x2='{xt:g}' y2='{cb + 2}' "
             f"stroke='{ORANGE}' stroke-width='2' stroke-dasharray='4 4'/>")
    p.append(f"<path d='M {xt - 5:g} {cb + 9} L {xt:g} {cb + 2} "
             f"L {xt + 5:g} {cb + 9} Z' fill='{ORANGE}'/>")
    ann_box(rx0, rx1, RETRY_LABEL_TEXT, RETRY_NOTE, ORANGE, ORANGE, box_h)

    # Evaluation: optional branch off results.json, outside the extraction path.
    p.append(f"<line x1='{bx0 + CARD_W / 2:g}' y1='{cb}' "
             f"x2='{bx0 + CARD_W / 2:g}' y2='{box_top}' "
             f"stroke='{BRANCH_LINE}' stroke-width='1' stroke-dasharray='4 4'/>")
    ann_box(bx0, bx1, BRANCH_LABEL_TEXT, BRANCH_NOTE, BRANCH_LINE,
            BRANCH_LABEL, box_h)

    height = int(box_top + box_h + PAD_BOTTOM)
    p[0] = (f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' "
            f"height='{height}' viewBox='0 0 {W} {height}'>"
            f"<rect width='{W}' height='{height}' fill='{BG}'/>")
    p.append("</svg>")
    return "\n".join(p)


def main():
    out = Path("docs/imgs/pipeline.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
