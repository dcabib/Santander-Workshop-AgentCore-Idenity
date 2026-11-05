"""Primitivas SVG para arquiteturas AWS com posições e rotas revisáveis."""

import base64
import html
import textwrap
from pathlib import Path

ICONS = Path(__file__).resolve().parents[1] / "docs/diagramas/icons"
INK = "#232F3E"
MUTED = "#52606D"
ORANGE = "#ED7100"
PURPLE = "#7B42BC"
TEAL = "#168C78"
RED = "#C92545"
BLUE = "#147EB4"


class Diagram:
    def __init__(self, number, title, *, height=790, legacy=False, subtitle=""):
        self.width, self.height = 1440, height
        self.nodes = {}
        self.parts = [
            '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="1440" height="{height}" viewBox="0 0 1440 {height}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{html.escape(number + " — " + title)}</title>',
            f'<desc id="desc">{html.escape(subtitle)}</desc>',
            "<defs>",
            *[
                f'<marker id="arrow-{key}" viewBox="0 0 10 10" refX="9" refY="5" '
                f'markerWidth="8" markerHeight="8" orient="auto-start-reverse">'
                f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{color}"/></marker>'
                for key, color in [
                    ("call", INK),
                    ("config", MUTED),
                    ("deny", RED),
                    ("step", ORANGE),
                ]
            ],
            '</defs><rect width="1440" height="100%" fill="white"/>',
            '<g font-family="Arial, Helvetica, sans-serif">',
        ]
        self.text(32, 35, f"{number}  /  {title}", size=27, weight="bold")
        self.text(32, 65, subtitle, size=17, color=MUTED)
        if legacy:
            self.text(
                32,
                height - 23,
                "REQUER 4 CONTAS AWS DISTINTAS  ·  Legado fora da jornada de conta única",
                size=16,
                color=RED,
            )
        else:
            self.text(
                32,
                height - 23,
                "AWS  ·  Recursos criados e inspecionados pelas células do notebook",
                size=16,
                color=MUTED,
            )
        self.line([(980, height - 28), (1020, height - 28)], arrow=False)
        self.text(1030, height - 23, "chamada", size=15, color=MUTED)
        self.line([(1140, height - 28), (1180, height - 28)], kind="config", arrow=False)
        self.text(1190, height - 23, "configuração / apoio", size=15, color=MUTED)

    def text(
        self, x, y, text, *, size=18, color=INK, weight="normal", anchor="start", leading=None
    ):
        lines = text.split("\n") if isinstance(text, str) else text
        for i, line in enumerate(lines):
            self.parts.append(
                f'<text x="{x}" y="{y + i * (leading or size * 1.3)}" text-anchor="{anchor}" '
                f'font-size="{size}" font-weight="{weight}" fill="{color}">{html.escape(str(line))}</text>'
            )

    def rect(self, x, y, w, h, *, stroke=INK, fill="white", width=1.7, dash=None, radius=0):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" '
            f'fill="{fill}" stroke="{stroke}" stroke-width="{width}"'
            + (f' stroke-dasharray="{dash}"' if dash else "")
            + "/>"
        )

    def icon(self, key, x, y, size=58):
        data = base64.b64encode((ICONS / f"{key}.svg").read_bytes()).decode()
        self.parts.append(
            f'<image x="{x}" y="{y}" width="{size}" height="{size}" '
            f'xlink:href="data:image/svg+xml;base64,{data}"/>'
        )

    def cloud(
        self, x=30, y=100, w=1380, h=None, *, title="AWS Cloud  /  conta do workshop", dashed=False
    ):
        h = h or self.height - y - 65
        self.rect(x, y, w, h, stroke=INK, dash="7 5" if dashed else None)
        self.icon("cloud", x, y, 36)
        self.text(x + 49, y + 26, title, size=19, weight="bold")

    def group(self, key, x, y, w, h, title, *, icon="agentcore", color=TEAL, rows=()):
        self.rect(x, y, w, h, stroke=color, width=2.2)
        self.icon(icon, x + 16, y + 16, 43)
        names = textwrap.wrap(title, width=max(17, int((w - 92) / 10)), break_long_words=False)
        self.text(x + 72, y + 34, names, size=20, weight="bold", leading=23)
        start = y + (90 if len(names) > 1 else 78)
        for i, row in enumerate(rows):
            self.rect(x + 17, start + i * 43, w - 34, 33, stroke=color, width=1.1, dash="4 3")
            self.text(x + 29, start + i * 43 + 22, row, size=17)
        self.nodes[key] = {
            "L": (x, y + h / 2),
            "R": (x + w, y + h / 2),
            "T": (x + w / 2, y),
            "B": (x + w / 2, y + h),
        }
        return self

    def service(self, key, cx, y, icon, title, detail="", *, size=62):
        self.icon(icon, cx - size / 2, y, size)
        self.text(cx, y + size + 26, title, size=19, weight="bold", anchor="middle", leading=23)
        lines = len(title.split("\n"))
        if detail:
            self.text(
                cx,
                y + size + 30 + lines * 23,
                detail,
                size=16,
                color=MUTED,
                anchor="middle",
                leading=20,
            )
        self.nodes[key] = {
            "L": (cx - 55, y + size / 2),
            "R": (cx + 55, y + size / 2),
            "T": (cx, y - 7),
            "B": (cx, y + size + 42 + lines * 23 + (20 if detail else 0)),
        }
        return self

    def note(self, x, y, w, text, *, title=None, color=MUTED):
        lines = text.split("\n")
        self.parts.append(
            f'<path d="M{x},{y} V{y + len(lines) * 22 + (28 if title else 0)}" stroke="{color}" stroke-width="3"/>'
        )
        if title:
            self.text(x + 13, y + 17, title, size=17, color=color, weight="bold")
        self.text(x + 13, y + (44 if title else 17), lines, size=17, color=color, leading=22)

    def badge(self, x, y, label, *, color=ORANGE):
        self.rect(x, y, max(50, len(label) * 9 + 28), 32, stroke=color, width=2, radius=5)
        self.text(x + 14, y + 22, label, size=17, weight="bold")

    def label(self, x, y, label, *, color=INK, size=17, anchor="middle"):
        lines = label.split("\n")
        w = max(map(len, lines)) * size * 0.56 + 16
        x0 = x - w / 2 if anchor == "middle" else x - 8
        self.rect(x0, y - size, w, len(lines) * (size + 4) + 3, stroke="none", fill="white")
        self.text(x, y, lines, size=size, color=color, anchor=anchor, leading=size + 4)

    def line(self, points, *, label="", at=None, kind="call", arrow=True, both=False):
        color = {"call": INK, "config": MUTED, "deny": RED, "step": ORANGE}[kind]
        self.parts.append(
            '<polyline points="'
            + " ".join(f"{x},{y}" for x, y in points)
            + f'" fill="none" stroke="{color}" stroke-width="2" stroke-linejoin="round"'
            + (' stroke-dasharray="7 5"' if kind in {"config", "deny"} else "")
            + (f' marker-end="url(#arrow-{kind})"' if arrow else "")
            + (f' marker-start="url(#arrow-{kind})"' if both else "")
            + "/>"
        )
        if label:
            x, y = at or (
                (points[0][0] + points[-1][0]) / 2,
                (points[0][1] + points[-1][1]) / 2 - 12,
            )
            self.label(x, y, label, color=color)

    def connect(self, source, target, *, start="R", end="L", via=(), **kwargs):
        self.line([self.nodes[source][start], *via, self.nodes[target][end]], **kwargs)

    def finish(self):
        return "\n".join([*self.parts, "</g></svg>"]) + "\n"
