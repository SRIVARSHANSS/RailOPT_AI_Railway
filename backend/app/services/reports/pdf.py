"""PDF building blocks for the reports (reportlab).

All text is set in DejaVu Sans, the font that ships with matplotlib, registered once so arrows,
dashes and other non-ASCII characters in the explanations render (the reportlab base fonts
cover Latin-1 only). Every page carries the data label of its content in the footer: a
LabelMark flowable switches the label from that point on (the model report has a SIMULATED
part and a REAL part).
"""
from __future__ import annotations

import io
import re
from pathlib import Path
from xml.sax.saxutils import escape

import matplotlib
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, Flowable, Frame, Image, KeepTogether, PageBreak, PageTemplate,
                                Paragraph, Preformatted, Spacer, Table, TableStyle)

FONT = "DejaVuSans"
FONT_BOLD = "DejaVuSans-Bold"
FONT_MONO = "DejaVuSansMono"
INK = colors.HexColor("#1b2430")
MUTED = colors.HexColor("#5b6675")
RULE = colors.HexColor("#c9d1db")
HEAD_BG = colors.HexColor("#eef2f6")
NOTE_BG = colors.HexColor("#fff6e5")
NOTE_EDGE = colors.HexColor("#d99a1e")
CONCLUSION_BG = colors.HexColor("#f1ecfb")
CONCLUSION_EDGE = colors.HexColor("#7a5cc4")

_registered = False


def font_dir() -> Path:
    return Path(matplotlib.get_data_path()) / "fonts" / "ttf"


def register_fonts() -> None:
    """Register matplotlib's DejaVu Sans (regular, bold, oblique, bold oblique, mono) once."""
    global _registered
    if _registered:
        return
    d = font_dir()
    for name, file in ((FONT, "DejaVuSans.ttf"), (FONT_BOLD, "DejaVuSans-Bold.ttf"),
                       ("DejaVuSans-Oblique", "DejaVuSans-Oblique.ttf"),
                       ("DejaVuSans-BoldOblique", "DejaVuSans-BoldOblique.ttf"),
                       (FONT_MONO, "DejaVuSansMono.ttf")):
        pdfmetrics.registerFont(TTFont(name, str(d / file)))
    pdfmetrics.registerFontFamily(FONT, normal=FONT, bold=FONT_BOLD, italic="DejaVuSans-Oblique",
                                  boldItalic="DejaVuSans-BoldOblique")
    _registered = True


def styles() -> dict[str, ParagraphStyle]:
    register_fonts()
    base = ParagraphStyle("body", fontName=FONT, fontSize=9, leading=12.5, textColor=INK, alignment=TA_LEFT,
                          bulletFontName=FONT)
    return {
        "body": base,
        "small": ParagraphStyle("small", parent=base, fontSize=7.5, leading=10, textColor=MUTED),
        "cell": ParagraphStyle("cell", parent=base, fontSize=7.5, leading=9.5),
        "cellb": ParagraphStyle("cellb", parent=base, fontName=FONT_BOLD, fontSize=7.5, leading=9.5),
        "title": ParagraphStyle("title", parent=base, fontName=FONT_BOLD, fontSize=17, leading=21, spaceAfter=4),
        "h1": ParagraphStyle("h1", parent=base, fontName=FONT_BOLD, fontSize=12.5, leading=16, spaceBefore=10, spaceAfter=4),
        "h2": ParagraphStyle("h2", parent=base, fontName=FONT_BOLD, fontSize=10.5, leading=14, spaceBefore=8, spaceAfter=3),
        "h3": ParagraphStyle("h3", parent=base, fontName=FONT_BOLD, fontSize=9.5, leading=13, spaceBefore=6, spaceAfter=2),
        "mono": ParagraphStyle("mono", parent=base, fontName=FONT_MONO, fontSize=7.2, leading=9.2),
        "bullet": ParagraphStyle("bullet", parent=base, leftIndent=10, bulletIndent=2),
    }


def p(text, style: str = "body", st: dict | None = None) -> Paragraph:
    """Paragraph from plain text (escaped; **bold** and `code` from the markdown cards kept)."""
    st = st or styles()
    return Paragraph(inline(str(text)), st[style])


def inline(text: str) -> str:
    out = escape(text)
    out = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", out)
    out = re.sub(r"`([^`]+)`", rf'<font face="{FONT_MONO}">\1</font>', out)
    return out.replace("\n", "<br/>")


class LabelMark(Flowable):
    """Zero-size flowable: from here on the footer shows `label`."""

    def __init__(self, label: str):
        super().__init__()
        self.label = label
        self.width = self.height = 0

    def draw(self):
        self.canv._railopt_label = self.label


def table(rows: list[list], widths: list[float] | None = None, header: bool = True, st: dict | None = None,
          zebra: bool = False) -> Table:
    st = st or styles()
    data = [[c if isinstance(c, Flowable) else Paragraph(inline("" if c is None else str(c)),
                                                          st["cellb" if header and i == 0 else "cell"])
             for c in r] for i, r in enumerate(rows)]
    t = Table(data, colWidths=widths, repeatRows=1 if header else 0, hAlign="LEFT")
    cmds = [("FONTNAME", (0, 0), (-1, -1), FONT), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.3, RULE),
            ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
    if header:
        cmds.append(("BACKGROUND", (0, 0), (-1, 0), HEAD_BG))
    t.setStyle(TableStyle(cmds))
    return t


def boxed(flowables: list, bg=NOTE_BG, edge=NOTE_EDGE, width: float | None = None) -> Table:
    t = Table([[flowables]], colWidths=[width] if width else None, hAlign="LEFT")
    t.setStyle(TableStyle([("FONTNAME", (0, 0), (-1, -1), FONT), ("BACKGROUND", (0, 0), (-1, -1), bg), ("BOX", (0, 0), (-1, -1), 0.8, edge),
                           ("LEFTPADDING", (0, 0), (-1, -1), 6), ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    return t


def figure(fig, width: float) -> Image:
    """A matplotlib figure as a PNG image scaled to `width` points."""
    import matplotlib.pyplot as plt
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=170, bbox_inches="tight")
    w, h = fig.get_size_inches()
    plt.close(fig)
    buf.seek(0)
    img = Image(buf, width=width, height=width * h / w)
    img._railopt_png = buf.getvalue()           # kept for tests / debugging
    return img


def build(story: list, *, title: str, label: str, meta: str, wide: bool = False) -> bytes:
    """Render the story to PDF bytes. Footer on every page: data label (current LabelMark),
    meta (e.g. version / generated-at), page number. Header: the report title."""
    register_fonts()
    size = landscape(A4) if wide else A4
    buf = io.BytesIO()
    doc = BaseDocTemplate(buf, pagesize=size, leftMargin=14 * mm, rightMargin=14 * mm, topMargin=16 * mm,
                          bottomMargin=17 * mm, title=title, author="RailOpt AI", subject=label,
                          initialFontName=FONT, initialFontSize=9)

    def decorate(canv, d):
        lab = getattr(canv, "_railopt_label", label)
        canv.saveState()
        w, h = size
        canv.setFont(FONT, 7.5)
        canv.setFillColor(MUTED)
        canv.drawString(14 * mm, h - 10 * mm, title)
        canv.drawRightString(w - 14 * mm, h - 10 * mm, "RailOpt AI - decision support; it controls no trains or signals")
        canv.setStrokeColor(RULE)
        canv.line(14 * mm, 13 * mm, w - 14 * mm, 13 * mm)
        canv.setFont(FONT_BOLD, 8)
        canv.setFillColor(INK)
        canv.drawString(14 * mm, 8.5 * mm, f"Data: {lab}")
        canv.setFont(FONT, 7.5)
        canv.setFillColor(MUTED)
        canv.drawCentredString(w / 2, 8.5 * mm, meta)
        canv.drawRightString(w - 14 * mm, 8.5 * mm, f"page {d.page}")
        canv.restoreState()

    # drawn when the page ENDS, so a LabelMark at the top of a page already counts for its footer
    frame = Frame(doc.leftMargin, doc.bottomMargin, doc.width, doc.height, id="body")
    doc.addPageTemplates([PageTemplate(id="page", frames=[frame], onPageEnd=decorate)])
    story = [LabelMark(label)] + story
    doc.build(story)
    return buf.getvalue()


def frame_width(wide: bool = False) -> float:
    return (landscape(A4) if wide else A4)[0] - 28 * mm


def markdown(text: str, st: dict | None = None, width: float | None = None) -> list:
    """The generated markdown cards (model_card.md, model_card_real.md) as flowables:
    headings, paragraphs, bullet lists, pipe tables, code blocks. Text is kept as written."""
    st = st or styles()
    width = width or frame_width()
    out: list = []
    lines = text.splitlines()
    i = 0
    para: list[str] = []

    def flush():
        if para:
            out.append(Paragraph(inline(" ".join(s.strip() for s in para)), st["body"]))
            out.append(Spacer(1, 3))
            para.clear()

    while i < len(lines):
        line = lines[i]
        s = line.strip()
        if s.startswith("```"):
            flush()
            block = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                block.append(lines[i])
                i += 1
            out.append(Preformatted("\n".join(block), st["mono"]))
        elif s.startswith("#"):
            flush()
            level = len(s) - len(s.lstrip("#"))
            out.append(Paragraph(inline(s.lstrip("#").strip()), st["h1" if level <= 1 else "h2" if level == 2 else "h3"]))
        elif s.startswith("|"):
            flush()
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
                if not all(re.fullmatch(r":?-{2,}:?", c) for c in cells if c):
                    rows.append(cells)
                i += 1
            n = max(len(r) for r in rows)
            rows = [r + [""] * (n - len(r)) for r in rows]
            out.append(table(rows, [width / n] * n, st=st))
            out.append(Spacer(1, 4))
            continue
        elif re.match(r"^\s*([-*]|\d+\.)\s+", line):
            flush()
            m = re.match(r"^(\s*)([-*]|\d+\.)\s+(.*)$", line)
            bullet = "•" if m.group(2) in "-*" else m.group(2)
            body = [m.group(3)]
            while i + 1 < len(lines) and lines[i + 1].startswith("  ") and lines[i + 1].strip() \
                    and not re.match(r"^\s*([-*]|\d+\.)\s+", lines[i + 1]):
                i += 1
                body.append(lines[i].strip())
            indent = 10 + 8 * (len(m.group(1)) // 2)
            out.append(Paragraph(inline(" ".join(body)), ParagraphStyle("b", parent=st["bullet"], leftIndent=indent,
                                                                        bulletIndent=indent - 8), bulletText=bullet))
        elif not s:
            flush()
        else:
            para.append(s)
        i += 1
    flush()
    return out


__all__ = ["FONT", "LabelMark", "PageBreak", "KeepTogether", "Spacer", "boxed", "build", "figure",
           "frame_width", "markdown", "p", "register_fonts", "styles", "table", "CONCLUSION_BG", "CONCLUSION_EDGE"]
