"""Render the pipeline diagram as an SVG in the MulitaMiner brand style.

Unlike the decision tree, the pipeline is a fixed sequence, so the stages are
listed here rather than derived from code. Regenerate after a stage change:

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

# (title, module/sub-caption). A real ordered sequence, so the stages are numbered.
STAGES = [
    ("PDF", "input"),
    ("Extract text", "pdf_reader"),
    ("Split blocks", "scanner_engine"),
    ("LLM extract", "block-anchored"),
    ("Consolidate", "pair · dedup"),
    ("results.json", "primary output"),
    ("Exports", "sarif · csaf · …"),
]

W = 1300
MARGIN = 28
GAP = 30
CARD_W = (W - 2 * MARGIN - (len(STAGES) - 1) * GAP) / len(STAGES)
CARD_Y = 70
CARD_H = 118
MIDY = CARD_Y + CARD_H / 2


def esc(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def text(x, y, s, size, fill=INK, weight="normal", font=SANS, spacing=None):
    ls = f"letter-spacing='{spacing}' " if spacing else ""
    return (f"<text x='{x}' y='{y}' font-size='{size}' fill='{fill}' "
            f"font-weight='{weight}' text-anchor='middle' {ls}{font} "
            f"dominant-baseline='middle'>{esc(s)}</text>")


def build() -> str:
    height = CARD_Y + CARD_H + 60
    p = [f"<svg xmlns='http://www.w3.org/2000/svg' width='{W}' height='{height}' "
         f"viewBox='0 0 {W} {height}'>",
         f"<rect width='{W}' height='{height}' fill='{BG}'/>",
         (f"<text x='{MARGIN + 4}' y='34' font-size='13' fill='{ORANGE}' "
          f"font-weight='bold' text-anchor='start' letter-spacing='2' {MONO} "
          f"dominant-baseline='middle'>PIPELINE</text>")]

    for i, (title, sub) in enumerate(STAGES):
        x = MARGIN + i * (CARD_W + GAP)
        cx = x + CARD_W / 2
        last = i == len(STAGES) - 1
        # Outputs (last two) get an orange-tinted card to read as results.
        fill = "#f6e2cf" if i >= len(STAGES) - 2 else CARD
        p.append(f"<rect x='{x}' y='{CARD_Y}' width='{CARD_W}' height='{CARD_H}' "
                 f"rx='16' fill='{fill}' stroke='{CARD_LINE}' stroke-width='1.5'/>")
        # Number chip straddling the top edge.
        p.append(f"<circle cx='{cx}' cy='{CARD_Y}' r='16' fill='{ORANGE}'/>")
        p.append(text(cx, CARD_Y, str(i + 1), 14, "#fff", "bold", MONO))
        p.append(text(cx, CARD_Y + 52, title, 16, INK, "bold"))
        p.append(text(cx, CARD_Y + 78, sub, 12, MUTED, "normal", MONO))
        # Arrow to the next card.
        if not last:
            ax = x + CARD_W
            bx = ax + GAP
            p.append(f"<line x1='{ax + 4}' y1='{MIDY}' x2='{bx - 8}' y2='{MIDY}' "
                     f"stroke='{ORANGE}' stroke-width='2.2'/>")
            p.append(f"<path d='M {bx - 9} {MIDY - 5} L {bx - 2} {MIDY} "
                     f"L {bx - 9} {MIDY + 5} Z' fill='{ORANGE}'/>")

    p.append(text(W / 2, height - 26,
                  "Everything between stages stays in memory.", 12.5, MUTED, "normal", MONO))
    p.append("</svg>")
    return "\n".join(p)


def main() -> None:
    out = Path("docs/imgs/pipeline.svg")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(), encoding="utf-8")
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
