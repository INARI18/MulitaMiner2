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
CARD = "#f4e9db"
CARD_LINE = "#e6d6c1"

SANS = ("font-family='ui-sans-serif,-apple-system,Segoe UI,Helvetica,Arial,"
        "sans-serif'")
MONO = "font-family='ui-monospace,SFMono-Regular,Menlo,Consolas,monospace'"

# (title, sub-caption, icon). A real ordered sequence, so stages are numbered.
STAGES = [
    ("PDF", "input", "page"),
    ("Extract text", "pdf_reader", "search"),
    ("Split blocks", "scanner_engine", "blocks"),
    ("Pack chunks", "chunking", "chunk"),
    ("LLM extract", "block-anchored", "spark"),
    ("Consolidate", "pair · dedup", "merge"),
    ("results.json", "primary output", "braces"),
    ("Exports", "sarif · csaf · …", "files"),
]
IN_MEMORY = range(1, 6)  # Extract text .. Consolidate run in memory
RETRY = (3, 4)  # LLM extract (4) loops failed blocks back to Pack chunks (3)

W = 1320
MARGIN = 30
GAP = 32
N = len(STAGES)
CARD_W = (W - 2 * MARGIN - (N - 1) * GAP) / N
CARD_Y = 96
CARD_H = 150
MIDY = CARD_Y + CARD_H / 2


def esc(s):
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size, fill=INK, weight="normal", font=SANS, anchor="middle", spacing=None):
    ls = f"letter-spacing='{spacing}' " if spacing else ""
    return (f"<text x='{x}' y='{y}' font-size='{size}' fill='{fill}' font-weight='{weight}' "
            f"text-anchor='{anchor}' {ls}{font} dominant-baseline='middle'>{esc(s)}</text>")


def icon(kind, cx, cy):
    """Simple orange line icon centered at (cx, cy), ~34px."""
    o = ORANGE
    s = f"stroke='{o}' stroke-width='2' fill='none' stroke-linecap='round' stroke-linejoin='round'"
    g = [f"<g {s}>"]
    if kind == "page":
        g += [f"<path d='M {cx-13} {cy-16} h 18 l 8 8 v 24 h -26 z'/>",
              f"<path d='M {cx+5} {cy-16} v 8 h 8'/>",
              f"<path d='M {cx-8} {cy-2} h 12 M {cx-8} {cy+5} h 16 M {cx-8} {cy+12} h 16'/>"]
    elif kind == "search":
        g += [f"<path d='M {cx-14} {cy-16} h 16 l 7 7 v 22 h -23 z'/>",
              f"<path d='M {cx-9} {cy-4} h 10 M {cx-9} {cy+3} h 13'/>",
              f"<circle cx='{cx+9}' cy='{cy+9}' r='7'/>",
              f"<path d='M {cx+14} {cy+14} l 6 6'/>"]
    elif kind == "blocks":
        g += [f"<rect x='{cx-15}' y='{cy-15}' width='20' height='9' rx='2'/>",
              f"<rect x='{cx-9}' y='{cy-3}' width='24' height='9' rx='2'/>",
              f"<rect x='{cx-15}' y='{cy+9}' width='20' height='9' rx='2'/>"]
    elif kind == "spark":
        g += [f"<path d='M {cx} {cy-17} C {cx+4} {cy-4} {cx+4} {cy-4} {cx+17} {cy} "
              f"C {cx+4} {cy+4} {cx+4} {cy+4} {cx} {cy+17} "
              f"C {cx-4} {cy+4} {cx-4} {cy+4} {cx-17} {cy} "
              f"C {cx-4} {cy-4} {cx-4} {cy-4} {cx} {cy-17} Z'/>",
              f"<path d='M {cx+12} {cy-15} l 2 5 l 5 2 l -5 2 l -2 5 l -2 -5 l -5 -2 l 5 -2 z' "
              f"fill='{o}'/>"]
    elif kind == "merge":
        g += [f"<path d='M {cx-16} {cy-13} h 8 c 8 0 8 13 16 13'/>",
              f"<path d='M {cx-16} {cy+13} h 8 c 8 0 8 -13 16 -13'/>",
              f"<path d='M {cx+16} {cy} h 6'/>",
              f"<path d='M {cx+16} {cy-5} l 6 5 l -6 5' fill='{o}'/>"]
    elif kind == "braces":
        g += [f"<path d='M {cx-7} {cy-16} c -5 0 -2 7 -6 8 c 4 1 1 8 6 8'/>",
              f"<path d='M {cx+7} {cy-16} c 5 0 2 7 6 8 c -4 1 -1 8 -6 8'/>",
              f"<circle cx='{cx}' cy='{cy}' r='1.8' fill='{o}'/>"]
    elif kind == "chunk":
        g += [f"<path d='M {cx-10} {cy-15} h -5 v 30 h 5'/>",
              f"<path d='M {cx+10} {cy-15} h 5 v 30 h -5'/>",
              f"<rect x='{cx-7}' y='{cy-10}' width='14' height='8' rx='2'/>",
              f"<rect x='{cx-7}' y='{cy+2}' width='14' height='8' rx='2'/>"]
    elif kind == "files":
        g += [f"<path d='M {cx-4} {cy-16} h 12 l 6 6 v 20 h -18 z'/>",
              f"<path d='M {cx-12} {cy-10} h 12 l 6 6 v 20 h -18 z' fill='{BG}'/>",
              f"<path d='M {cx-12} {cy-10} h 12 l 6 6 v 20 h -18 z'/>"]
    g.append("</g>")
    return "".join(g)


def build():
    cb = CARD_Y + CARD_H       # card bottom
    loop_y = cb + 36           # retry loop level
    gy = CARD_Y - 32           # group top
    g_bottom = loop_y + 22     # group bottom (contains the retry loop)
    height = g_bottom + 18
    p = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{height}' "
         f"viewBox='0 0 {W} {height}'>",
         f"<rect width='{W}' height='{height}' fill='{BG}'/>",
         text(MARGIN + 2, 36, "PIPELINE", 13, ORANGE, "bold", MONO, "start", "2")]

    xs = [MARGIN + i * (CARD_W + GAP) for i in range(N)]

    # "In memory" group behind the processing stages.
    gx0 = xs[IN_MEMORY[0]] - 15
    gx1 = xs[IN_MEMORY[-1]] + CARD_W + 15
    p.append(f"<rect x='{gx0}' y='{gy}' width='{gx1-gx0}' height='{g_bottom-gy}' "
             f"rx='18' fill='none' stroke='{ORANGE}' stroke-width='1.5' "
             f"stroke-dasharray='6 6' opacity='0.5'/>")
    p.append(f"<rect x='{gx0+16}' y='{gy-9}' width='84' height='18' fill='{BG}'/>")
    p.append(text(gx0 + 22, gy, "IN MEMORY", 11.5, ORANGE, "bold", MONO, "start", "1.5"))

    # Retry loop: LLM extract sends failed blocks back to be re-packed smaller.
    xp = xs[RETRY[0]] + CARD_W / 2
    xl = xs[RETRY[1]] + CARD_W / 2
    p.append(f"<path d='M {xl} {cb} V {loop_y} H {xp} V {cb}' fill='none' "
             f"stroke='{ORANGE}' stroke-width='2' stroke-dasharray='4 4'/>")
    p.append(f"<path d='M {xp-5} {cb+8} L {xp} {cb} L {xp+5} {cb+8} Z' fill='{ORANGE}'/>")
    p.append(text((xp + xl) / 2, loop_y + 13,
                  "on failure, the missing blocks are re-packed into smaller chunks",
                  11, ORANGE, "bold", MONO))

    for i, (title, sub, ic) in enumerate(STAGES):
        x = xs[i]
        cx = x + CARD_W / 2
        p.append(f"<rect x='{x}' y='{CARD_Y}' width='{CARD_W}' height='{CARD_H}' rx='16' "
                 f"fill='{CARD}' stroke='{CARD_LINE}' stroke-width='1.5'/>")
        p.append(f"<circle cx='{x+22}' cy='{CARD_Y+22}' r='13' fill='{ORANGE}'/>")
        p.append(text(x + 22, CARD_Y + 22, str(i + 1), 13, "#fff", "bold", MONO))
        p.append(icon(ic, cx, CARD_Y + 62))
        p.append(text(cx, CARD_Y + 106, title, 16, INK, "bold"))
        p.append(text(cx, CARD_Y + 130, sub, 11.5, MUTED, "normal", MONO))
        if i < N - 1:
            ax, bx = x + CARD_W, x + CARD_W + GAP
            p.append(f"<line x1='{ax+5}' y1='{MIDY}' x2='{bx-9}' y2='{MIDY}' "
                     f"stroke='{ORANGE}' stroke-width='2.2'/>")
            p.append(f"<path d='M {bx-10} {MIDY-5} L {bx-3} {MIDY} L {bx-10} {MIDY+5} Z' "
                     f"fill='{ORANGE}'/>")

    p.append("</svg>")
    return "\n".join(p)


def main():
    out = Path("docs/imgs/pipeline.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
