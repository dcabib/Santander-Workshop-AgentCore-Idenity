"""Diagramas ilustrados do workshop, em SVG/PNG, sem chamadas a serviços.

Renderização PNG: rsvg-convert (librsvg). O SVG é a fonte editável.
O conteúdo é intencionalmente desenhado; não depende de layouts automáticos.
"""

import argparse
import base64
import html
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "diagramas"
WIDTH, HEIGHT = 1600, 1000
C = {
    "ink": "#172B46",
    "muted": "#52657C",
    "line": "#8595AB",
    "border": "#DAE3EE",
    "bg": "#F4F7FB",
    "red": "#D52E3F",
    "identity": "#2469DD",
    "policy": "#7546C7",
    "gateway": "#BD650F",
    "registry": "#087F82",
    "allow": "#14795C",
    "local": "#415571",
    "azure": "#2169B0",
}
TINT = {
    "identity": "#ECF3FF",
    "policy": "#F2EDFB",
    "gateway": "#FFF3E5",
    "registry": "#E8F7F5",
    "red": "#FFF0F1",
    "allow": "#EAF7F0",
    "local": "#EDF1F7",
    "azure": "#EDF5FC",
}

PAGES = [
    {
        "id": "00_preflight",
        "pillar": "Visão geral",
        "title": "Antes de começar: dois ambientes",
        "subtitle": "O que você já consegue executar e o que ainda precisa validar nos serviços.",
        "status": "MAPA DO LABORATÓRIO",
        "takeaway": "A simulação valida a lógica. O ensaio AWS valida as integrações.",
        "description": "Compare a bancada local com o ambiente AWS. Tokens de teste e Cedar rodam localmente; os serviços gerenciados exigem configuração e ensaio.",
        "result": "Saber exatamente qual ambiente está sendo usado e o que seu resultado comprova.",
        "notes": [
            "Local: nenhuma conta AWS é utilizada.",
            "AWS: preflight lê o estado dos recursos; não os cria.",
            "Dados de negócio são sintéticos em ambas as trilhas.",
        ],
    },
    {
        "id": "01_gateway_targets",
        "pillar": "Gateway",
        "title": "Uma entrada para ferramentas diferentes",
        "subtitle": "O Gateway expõe Lambda e um especialista MCP pelo mesmo contrato de ferramentas.",
        "status": "ARQUITETURA AWS PREVISTA",
        "takeaway": "O cliente usa tools/list e tools/call; o Gateway conecta os destinos.",
        "description": "O supervisor acessa Riscos/K2 em Lambda e Fraude em um servidor MCP. O Gateway autentica, aplica Policy e usa a credencial adequada a cada target.",
        "result": "Encontrar os nomes reais das tools e executar uma chamada pelo caminho autorizado.",
        "notes": [
            "Riscos/K2: chamada Lambda com IAM.",
            "Fraude: target MCP com OAuth/OBO.",
            "Local: protocolo MCP por stdio; roteamento AWS ainda depende de ensaio.",
        ],
    },
    {
        "id": "02_identity_entra_obo",
        "pillar": "Identity",
        "title": "O usuário continua sendo o usuário",
        "subtitle": "Duas trocas OBO mudam a audiência do token sem substituir o principal humano.",
        "status": "FLUXO ENTRA / AWS A VALIDAR",
        "takeaway": "A prova de delegação é o destino reconhecer o usuário esperado.",
        "description": "O usuário entra pelo frontend Entra. O agente confidencial obtém um token para o Gateway; o AgentCore Identity participa da troca para o Microsoft Graph.",
        "result": "Comparar o ID devolvido por Graph /me com o OID esperado de dois usuários de teste.",
        "notes": [
            "Primeiro OBO: helper MSAL no host do instrutor.",
            "Segundo OBO: integração Gateway + AgentCore Identity.",
            "Somente Graph /me; tokens e perfis completos não entram nas evidências.",
        ],
    },
    {
        "id": "03_identity_agente_mcp",
        "pillar": "Identity",
        "title": "A pessoa é a mesma. O agente mudou.",
        "subtitle": "A decisão considera quem é o usuário e qual aplicação está agindo por ele.",
        "status": "LÓGICA LOCAL · AWS A VALIDAR",
        "takeaway": "Permissão do usuário e permissão do agente precisam ser satisfeitas.",
        "description": "Com o mesmo usuário habilitado a Riscos e Fraude, o supervisor pode consultar Fraude, mas o agente de Riscos recebe uma negativa.",
        "result": "Mostrar uma mudança de decisão alterando apenas a identidade técnica do chamador.",
        "notes": [
            "tid + oid: identidade humana no tenant.",
            "azp, no fluxo Entra v2: aplicação confidencial.",
            "O Runtime Fraude também valida audiência, aplicação do Gateway e workload.",
        ],
    },
    {
        "id": "04_policy_cedar",
        "pillar": "Policy",
        "title": "A autorização acontece antes da ferramenta",
        "subtitle": "Cedar combina identidade, ação, recurso e parâmetros em uma única decisão.",
        "status": "CEDAR LOCAL · AWS A VALIDAR",
        "takeaway": "50 registros podem passar. 51 devem parar antes de executar o backend.",
        "description": "A regra exige simultaneamente usuário, aplicação, delegação, ação, Gateway e limite de entrada corretos. Uma condição falsa impede a execução.",
        "result": "Reproduzir a matriz P-SAN-01 a P-SAN-06 e distinguir negação de Policy de outros erros.",
        "notes": [
            "ENFORCE no Gateway previsto por IaC.",
            "Contador local verifica que negativas não executam o backend.",
            "A prova equivalente em AWS exige correlacionar decisão, chamada e logs.",
        ],
    },
    {
        "id": "05_policy_autoria",
        "pillar": "Policy",
        "title": "Da intenção à política revisada",
        "subtitle": "Gerar Cedar é uma etapa de autoria. Publicar exige revisão, testes e mudança por IaC.",
        "status": "AUTORIA LOCAL · SERVIÇO A VALIDAR",
        "takeaway": "Um rascunho gerado não se transforma automaticamente em permissão.",
        "description": "Uma intenção em linguagem natural pode gerar um rascunho por um stack separado. O notebook lê Cedar e findings; a promoção ocorre pelo pipeline revisado.",
        "result": "Conferir se o Cedar representa a intenção e se os casos permitidos e negados continuam corretos.",
        "notes": [
            "Provider de rascunho não recebe CreatePolicy.",
            "Findings precisam ser revisados, sem IGNORE_ALL_FINDINGS.",
            "O histórico de geração é retido; ele não concede acesso.",
        ],
    },
    {
        "id": "06_registry_governanca",
        "pillar": "Registry",
        "title": "Publicar, aprovar e consumir são papéis distintos",
        "subtitle": "Um catálogo governado separa o ciclo do registro da autorização para executar uma tool.",
        "status": "MODELO LOCAL · IAM A VALIDAR",
        "takeaway": "O publisher submete. O approver decide. O consumer encontra aprovados.",
        "description": "Os registros percorrem DRAFT, PENDING_APPROVAL e APPROVED ou REJECTED. Os papéis AWS usam sessões temporárias e permissões distintas.",
        "result": "Verificar a separação de papéis e observar todos os estados preparados para o workshop.",
        "notes": [
            "autoApproval = false.",
            "Busca desta implementação usa AWS_IAM e STS.",
            "No modo AWS, o notebook lê estados preparados pelo IaC.",
        ],
    },
    {
        "id": "07_registry_descoberta_execucao",
        "pillar": "Registry",
        "title": "Encontrar uma capacidade não libera seu uso",
        "subtitle": "O supervisor descobre no Registry, valida o endpoint e invoca pelo Gateway.",
        "status": "FLUXO LOCAL · AWS A VALIDAR",
        "takeaway": "Registry responde “o que existe”; Policy decide “o que este chamador pode fazer”.",
        "description": "O catálogo devolve capacidades aprovadas. O supervisor valida metadados antes de enviar o token; o Gateway continua sendo o ponto de autorização.",
        "result": "Encontrar Fraude para dois perfis e observar que só o perfil autorizado consegue executá-la.",
        "notes": [
            "Busca AWS semântica; busca local lexical.",
            "Somente o endpoint exato configurado recebe bearer.",
            "Aprovação no Registry não substitui a decisão Cedar.",
        ],
    },
    {
        "id": "08_santander_multi_conta",
        "pillar": "Arquitetura integrada",
        "title": "Três contas. Fronteiras explícitas.",
        "subtitle": "O supervisor está na origem; governança fica no hub; Fraude pertence a outro domínio.",
        "status": "ARQUITETURA AWS A VALIDAR",
        "takeaway": "A chamada deve preservar o usuário e respeitar a autorização em cada fronteira.",
        "description": "Conta A hospeda o supervisor; conta C concentra Registry, Gateway, Identity e Policy; conta B hospeda o especialista de Fraude.",
        "result": "Executar A → C → B de verdade e reunir evidências nos três lados da chamada.",
        "notes": [
            "A → Registry C: IAM com AssumeRole.",
            "A → Gateway C: JWT delegado.",
            "C → Fraude B: OBO e restrição ao workload do Gateway.",
        ],
    },
    {
        "id": "09_databricks_e_evidencias",
        "pillar": "Fonte de dados",
        "title": "A fonte de dados precisa reconhecer a pessoa",
        "subtitle": "A extensão Databricks verifica identidade efetiva e grants, com uma tabela canário.",
        "status": "EXTENSÃO AZURE A VALIDAR",
        "takeaway": "Sem token delegado válido, a consulta para. Não há fallback para credencial compartilhada.",
        "description": "O adapter de extensão troca um JWT Entra por um token Databricks e consulta o SQL Warehouse. A identidade e a permissão da fonte são verificadas separadamente.",
        "result": "Provar current_user() exato e acesso distinto para dois usuários na mesma tabela sintética.",
        "notes": [
            "Caminho de extensão separado do Gateway nesta entrega.",
            "Unity Catalog governa o acesso aos dados.",
            "Graph /me não comprova delegação no Databricks Azure.",
        ],
    },
]


def esc(value):
    return html.escape(str(value), quote=True)


class Diagram:
    def __init__(self, page):
        self.p = page
        self.parts = [
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-labelledby="title desc">',
            f'<title id="title">{esc(page["title"])}</title><desc id="desc">{esc(page["description"])}</desc>',
            """<defs>
            <filter id="shadow" x="-20%" y="-20%" width="140%" height="150%">
              <feDropShadow dx="0" dy="5" stdDeviation="8" flood-color="#172B46" flood-opacity=".06"/>
            </filter>
            <pattern id="dots" width="24" height="24" patternUnits="userSpaceOnUse">
              <circle cx="2" cy="2" r="1" fill="#DDE5EF"/>
            </pattern>
            </defs>""",
        ]
        self.rect(0, 0, WIDTH, HEIGHT, C["bg"], radius=0)
        self.parts.append(
            '<rect x="0" y="190" width="1600" height="650" fill="url(#dots)" opacity=".5"/>'
        )
        self.rect(0, 0, WIDTH, 190, "#FFFFFF", radius=0)
        self.rect(64, 41, 6, 28, C["red"], radius=3)
        self.text(
            86,
            61,
            f"WORKSHOP SANTANDER  /  AGENTCORE  /  {page['id'][:2]}",
            16,
            C["muted"],
            weight=700,
            spacing=1.8,
        )
        self.text(64, 122, page["title"], 42, C["ink"], weight=700)
        self.text(64, 163, page["subtitle"], 23, C["muted"])
        self.tag(1120, 39, 416, page["status"], "local", height=34, size=13)
        self.rect(64, 850, 1472, 96, C["ink"], radius=20)
        self.icon(88, 875, "bulb", "#FFFFFF", size=44)
        self.text(153, 881, "O QUE ESTE NOTEBOOK ENSINA", 13, "#AFBED2", weight=700, spacing=1.4)
        self.text(153, 918, page["takeaway"], 25, "#FFFFFF", weight=600)
        self.text(
            64, 978, "Santander  ·  Amazon Bedrock AgentCore  ·  Dados sintéticos", 16, C["muted"]
        )
        self.text(1536, 978, f"{page['id'][:2]} / 09", 16, C["muted"], anchor="end")

    def raw(self, text):
        self.parts.append(text)

    def rect(self, x, y, w, h, fill="#FFFFFF", stroke=None, radius=18, dash=False, shadow=False):
        self.parts.append(
            f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{radius}" fill="{fill}"'
            + (f' stroke="{stroke}" stroke-width="1.6"' if stroke else "")
            + (' stroke-dasharray="8 6"' if dash else "")
            + (' filter="url(#shadow)"' if shadow else "")
            + "/>"
        )

    def text(
        self, x, y, content, size=22, fill=None, weight=400, anchor="start", spacing=None, cls=""
    ):
        lines = content if isinstance(content, list) else [content]
        self.parts.append(
            f'<text class="{cls}" x="{x}" y="{y}" fill="{fill or C["ink"]}" font-family="Arial,Helvetica,sans-serif"'
            f' font-size="{size}" font-weight="{weight}" text-anchor="{anchor}"'
            + (f' letter-spacing="{spacing}"' if spacing is not None else "")
            + ">"
        )
        for i, line in enumerate(lines):
            self.parts.append(
                f'<tspan x="{x}" dy="{0 if i == 0 else round(size * 1.38, 1)}">{esc(line)}</tspan>'
            )
        self.parts.append("</text>")

    def tag(self, x, y, w, text, tone="local", height=38, size=16):
        self.rect(x, y, w, height, TINT[tone], radius=height / 2)
        self.text(x + w / 2, y + height / 2 + size * 0.35, text, size, C[tone], 700, "middle")

    def label(self, x, y, text, tone="local", size=17):
        w = len(text) * size * 0.53 + 28
        self.rect(x - w / 2, y - size + 1, w, size + 13, "#FFFFFF", radius=8)
        self.text(x, y + 2, text, size, C[tone], weight=600, anchor="middle")

    def icon(self, x, y, name, color, size=48):
        self.raw(
            f'<g transform="translate({x} {y}) scale({size / 48})" fill="none" stroke="{color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">'
        )
        icons = {
            "user": '<circle cx="24" cy="14" r="8"/><path d="M8 42v-4c0-9 7-15 16-15s16 6 16 15v4"/><path d="M15 37h18"/>',
            "agent": '<rect x="6" y="12" width="36" height="29" rx="8"/><path d="M24 12V5m-4 0h8M2 23v9m44-9v9"/><circle cx="16" cy="24" r="2.5"/><circle cx="32" cy="24" r="2.5"/><path d="M17 33h14"/>',
            "laptop": '<rect x="7" y="6" width="34" height="27" rx="3"/><path d="M3 40h42l-4-7H7zM18 17l-5 4 5 4m12-8 5 4-5 4"/>',
            "gateway": '<path d="M17 7h14v34H17zM3 24h14m14 0h14M8 19l5 5-5 5m28-10 5 5-5 5"/><path d="M23 14h2m-2 20h2"/>',
            "shield": '<path d="M24 3l17 7v13c0 10-8 18-17 23C15 41 7 33 7 23V10z"/><path d="M15 23l6 6 12-13"/>',
            "key": '<circle cx="16" cy="18" r="10"/><circle cx="14" cy="16" r="2"/><path d="M23 25l17 17m-6-6 5-5m-11-1 5-5"/>',
            "catalog": '<rect x="7" y="5" width="29" height="38" rx="4"/><path d="M14 5v38m8-28h8m-8 8h8m-8 8h5M36 10h5v28"/>',
            "lambda": '<path d="M10 6h10l19 36H28L15 17M17 21L6 42h11l6-11"/>',
            "database": '<ellipse cx="24" cy="10" rx="17" ry="7"/><path d="M7 10v27c0 9 34 9 34 0V10M7 23c0 9 34 9 34 0"/>',
            "cloud": '<path d="M12 38h24c14 0 13-20 1-21C35 2 14 2 12 18 1 17-3 36 12 38z"/>',
            "graph": '<circle cx="10" cy="11" r="5"/><circle cx="37" cy="11" r="5"/><circle cx="24" cy="38" r="6"/><path d="M15 11h17M12 16l9 17m14-17-8 17"/>',
            "code": '<rect x="3" y="7" width="42" height="34" rx="5"/><path d="M3 16h42M9 11h1m5 0h1m5 0h1M16 23l-5 5 5 5m16-10 5 5-5 5m-6-12-5 14"/>',
            "document": '<path d="M10 3h19l10 10v32H10zM29 3v11h10M17 23h15m-15 7h15m-15 7h10"/>',
            "check": '<circle cx="24" cy="24" r="19"/><path d="M13 24l8 8 15-17"/>',
            "stop": '<path d="M15 4h18l12 12v17L33 45H15L3 33V16zM17 17l14 14m0-14L17 31"/>',
            "search": '<circle cx="20" cy="20" r="14"/><path d="M31 31l13 13M14 20h12m-6-6v12"/>',
            "deploy": '<path d="M7 33v11h34V33M24 34V4M13 15 24 4l11 11"/>',
            "review": '<path d="M28 43H7V5h24v12M14 14h10m-10 8h8m-8 8h5"/><circle cx="33" cy="29" r="9"/><path d="M40 36l6 7m-17-14 3 3 5-6"/>',
            "lock": '<rect x="8" y="21" width="32" height="23" rx="5"/><path d="M15 21V12a9 9 0 0 1 18 0v9M24 30v6"/>',
            "bulb": '<path d="M15 29c-11-11-4-25 9-25s20 14 9 25l-3 6H18zM18 40h12m-9 5h6M24 12v10m-5-5h10"/>',
            "token": '<rect x="3" y="10" width="42" height="28" rx="5"/><circle cx="15" cy="22" r="5"/><path d="M8 33c1-7 13-7 14 0M28 20h10m-10 7h7"/>',
            "layers": '<path d="M24 3 3 14l21 11 21-11zM3 25l21 11 21-11M3 36l21 11 21-11"/>',
        }
        self.raw(icons[name])
        self.raw("</g>")

    def node(
        self, x, y, w, h, title, body=(), tone="local", icon="agent", vertical=False, kicker=None
    ):
        self.raw(f'<g class="node" data-x="{x}" data-y="{y}" data-w="{w}" data-h="{h}">')
        self.rect(x, y, w, h, "#FFFFFF", C["border"], shadow=True)
        if vertical:
            self.rect(x + w / 2 - 32, y + 22, 64, 64, TINT[tone], radius=18)
            self.icon(x + w / 2 - 22, y + 32, icon, C[tone], 44)
            titles = title if isinstance(title, list) else [title]
            self.text(x + w / 2, y + 122, titles, 23, weight=700, anchor="middle", cls="node-text")
            by = y + 122 + (len(titles) - 1) * 31.74 + 42
            if body:
                self.text(
                    x + w / 2, by, list(body), 19, C["muted"], anchor="middle", cls="node-text"
                )
        else:
            self.rect(x + 20, y + 20, 56, 56, TINT[tone], radius=16)
            self.icon(x + 29, y + 29, icon, C[tone], 38)
            if kicker:
                self.text(x + 94, y + 34, kicker, 12, C[tone], 700, spacing=1)
                ty = y + 63
            else:
                ty = y + 54
            self.text(x + 94, ty, title, 23, weight=700, cls="node-text")
            if body:
                self.text(x + 24, y + 112, list(body), 21, C["muted"], cls="node-text")
        self.raw("</g>")

    def arrow(self, points, tone="local", dashed=False, width=3, end=True, start=False):
        color = C[tone]
        path = "M " + " L ".join(f"{x} {y}" for x, y in points)
        self.raw(
            f'<path d="{path}" stroke="{color}" fill="none" stroke-width="{width}" stroke-linejoin="round" stroke-linecap="round"'
            + (' stroke-dasharray="7 7"' if dashed else "")
            + "/>"
        )
        if end:
            self.head(points[-2], points[-1], color)
        if start:
            self.head(points[1], points[0], color)

    def head(self, before, tip, color):
        import math

        dx, dy = tip[0] - before[0], tip[1] - before[1]
        length = math.hypot(dx, dy)
        ux, uy = dx / length, dy / length
        bx, by = tip[0] - ux * 11, tip[1] - uy * 11
        points = [(tip[0], tip[1]), (bx - uy * 5.5, by + ux * 5.5), (bx + uy * 5.5, by - ux * 5.5)]
        self.raw(f'<polygon points="{" ".join(f"{a},{b}" for a, b in points)}" fill="{color}"/>')

    def panel(self, x, y, w, h, title, subtitle, tone="local"):
        self.rect(x, y, w, h, TINT[tone], C["border"], radius=22)
        self.text(x + 26, y + 38, title, 22, C[tone], 700)
        if subtitle:
            self.text(x + 26, y + 68, subtitle, 18, C["muted"])

    def finish(self):
        return "\n".join(self.parts + ["</svg>"])


def draw_00(d):
    d.panel(64, 225, 704, 575, "01  ·  BANCADA LOCAL", "Já executável no seu computador", "local")
    d.panel(
        800,
        225,
        736,
        575,
        "02  ·  AMBIENTE AWS",
        "Recursos preparados por IaC; ensaio ainda pendente",
        "identity",
    )
    d.node(
        95,
        334,
        640,
        162,
        "Seu notebook / terminal",
        ["uv run santander-demo demo", "Cliente fictício: SANT-DEMO-001"],
        icon="laptop",
    )
    for x, title, icon, tone in [
        (100, "JWT de teste", "token", "identity"),
        (318, "Cedar real", "shield", "policy"),
        (536, "Tools locais", "lambda", "gateway"),
    ]:
        d.node(x, 547, 194, 154, title, tone=tone, icon=icon, vertical=True)
    d.arrow([(416, 496), (416, 529), (198, 529), (198, 546)], tone="identity")
    d.arrow([(416, 529), (416, 546)], tone="policy")
    d.arrow([(416, 529), (633, 529), (633, 546)], tone="gateway")
    d.tag(156, 735, 520, "Lógica verificada · serviços simulados", "allow", height=40)
    d.node(
        835,
        334,
        666,
        130,
        "Entra ID + configuração do sandbox",
        ["Tenant, contas, região e identidades de teste"],
        "identity",
        "key",
    )
    services = [
        ("Gateway", "gateway", "gateway"),
        ("Identity", "identity", "key"),
        ("Policy", "policy", "shield"),
        ("Registry", "registry", "catalog"),
    ]
    for i, (title, tone, icon) in enumerate(services):
        x = 842 + i * 164
        d.node(x, 535, 150, 148, title, tone=tone, icon=icon, vertical=True)
    d.arrow([(1168, 464), (1168, 510)], tone="identity")
    d.text(
        1168,
        722,
        "Preflight: READY · ENFORCE · autoApproval=false",
        19,
        C["muted"],
        anchor="middle",
    )
    d.tag(
        880,
        746,
        576,
        "OBO, IAM e integrações precisam de prova real",
        "identity",
        height=36,
        size=16,
    )


def draw_01(d):
    d.panel(
        455,
        226,
        549,
        556,
        "AMAZON BEDROCK AGENTCORE",
        "Entrada comum e autorização antes da execução",
        "gateway",
    )
    d.node(
        64,
        396,
        326,
        202,
        ["Cliente /", "supervisor"],
        ["JWT destinado ao Gateway", "tools/list → tools/call"],
        "local",
        "agent",
    )
    d.node(
        494,
        366,
        470,
        193,
        "Gateway MCP",
        ["Descobre e encaminha ferramentas", "Nomes: target___tool"],
        "gateway",
        "gateway",
    )
    d.node(
        1118,
        250,
        418,
        194,
        "AWS Lambda",
        ["consultar_risco", "consultar_conhecimento_k2"],
        "gateway",
        "lambda",
    )
    d.node(
        1118,
        540,
        418,
        206,
        "Runtime Fraude",
        ["Servidor MCP", "consultar_fraude"],
        "identity",
        "agent",
    )
    d.node(
        515, 630, 428, 115, "Policy · ENFORCE", [], "policy", "shield", kicker="AUTORIZAÇÃO CEDAR"
    )
    d.arrow([(390, 480), (494, 480)], "identity")
    d.label(442, 457, "JWT", "identity")
    d.arrow([(964, 414), (1055, 414), (1055, 347), (1118, 347)], "gateway")
    d.label(1056, 315, "IAM", "gateway")
    d.arrow([(964, 512), (1055, 512), (1055, 632), (1118, 632)], "identity")
    d.label(1060, 673, "OAuth / OBO", "identity")
    d.arrow([(729, 630), (729, 559)], "policy", dashed=True)
    d.text(
        64,
        692,
        ["Uma chamada MCP.", "Destinos com protocolos", "e credenciais diferentes."],
        23,
        C["muted"],
    )


def draw_02(d):
    d.panel(
        64,
        225,
        1472,
        97,
        "MICROSOFT ENTRA ID",
        "Emite e troca os tokens aceitos por cada aplicação de destino.",
        "identity",
    )
    specs = [
        (64, ["Usuário", "de teste"], ["Login pelo frontend"], "user", "local"),
        (370, ["Agente", "confidencial"], ["1º OBO · helper MSAL"], "agent", "identity"),
        (676, ["AgentCore", "Gateway"], ["Valida JWT de entrada"], "gateway", "gateway"),
        (1288, ["Microsoft", "Graph"], ["GET /me"], "graph", "azure"),
    ]
    for x, title, body, icon, tone in specs:
        d.node(x, 391, 248, 246, title, body, tone, icon, vertical=True)
    for x in [312, 618]:
        d.arrow([(x, 510), (x + 58, 510)], "identity")
    d.arrow([(924, 510), (1288, 510)], "identity")
    d.label(1106, 472, "Gateway chama /me", "identity", 20)
    d.arrow([(494, 322), (494, 391)], "identity", dashed=True)
    d.node(
        851,
        679,
        414,
        130,
        "AgentCore Identity",
        ["2º OBO: credencial para o Graph"],
        "identity",
        "key",
    )
    d.arrow([(800, 637), (800, 744), (851, 744)], "identity", dashed=True, start=True)
    d.tag(64, 692, 311, "TOKEN 1 · aud: agente", "identity", height=46, size=19)
    d.tag(401, 692, 345, "TOKEN 2 · aud: Gateway", "identity", height=46, size=19)
    d.tag(1288, 692, 248, "TOKEN 3 · aud: Graph", "azure", height=46, size=17)
    d.text(64, 797, "Mesmo usuário; uma audiência para cada destino.", 22, C["muted"])


def draw_03(d):
    d.panel(64, 224, 475, 568, "MESMO USUÁRIO", "Perfil humano: Riscos + Fraude", "identity")
    d.icon(90, 325, "user", C["identity"], 70)
    d.text(183, 353, "tid + oid preservados", 26, C["identity"], 700)
    d.node(92, 416, 418, 134, "Supervisor", ["Aplicação autorizada a Fraude"], "allow", "agent")
    d.node(
        92, 613, 418, 134, "Agente de Riscos", ["Aplicação sem permissão de Fraude"], "red", "agent"
    )
    d.node(
        670,
        418,
        362,
        243,
        ["Gateway +", "Policy"],
        ["Usuário + caller + ação", "precisam ser autorizados"],
        "policy",
        "shield",
    )
    d.node(
        1170,
        418,
        366,
        243,
        "Runtime Fraude",
        ["MCP protegido", "Valida token e workload"],
        "identity",
        "agent",
    )
    d.arrow([(510, 480), (670, 480)], "allow")
    d.label(590, 451, "PERMITE", "allow", 17)
    d.arrow([(510, 680), (588, 680), (588, 598), (670, 598)], "red")
    d.label(588, 727, "NEGA", "red", 17)
    d.arrow([(1032, 508), (1170, 508)], "identity")
    d.label(1101, 479, "OBO", "identity")
    d.tag(1135, 718, 401, "Somente via workload do Gateway", "identity", height=44, size=18)
    d.text(670, 803, "No fluxo Entra v2, azp distingue as aplicações.", 20, C["muted"])


def draw_04(d):
    d.node(
        64,
        361,
        366,
        285,
        "Pedido autenticado",
        [
            "Usuário: Riscos + Fraude",
            "Caller: supervisor",
            "Tool: consultar_risco",
            "max_registros: 50 ou 51",
        ],
        "identity",
        "token",
    )
    d.panel(
        492,
        223,
        596,
        584,
        "GATEWAY · POLICY EM ENFORCE",
        "Todas as condições precisam ser verdadeiras",
        "policy",
    )
    d.icon(536, 336, "shield", C["policy"], 66)
    d.text(630, 362, "Uma regra Cedar", 29, C["policy"], 700)
    checks = [
        ("01", "Tenant e usuário permitidos"),
        ("02", "Aplicação chamadora permitida"),
        ("03", "Contexto delegado presente"),
        ("04", "Ação e Gateway exatos"),
        ("05", "1 ≤ max_registros ≤ 50"),
    ]
    for i, (n, label) in enumerate(checks):
        y = 422 + i * 65
        d.tag(527, y - 25, 46, n, "policy", height=38, size=16)
        d.text(594, y + 2, label, 23, C["ink"])
    d.tag(649, 744, 283, "Condições ligadas por AND", "policy", height=37, size=16)
    d.node(
        1180,
        309,
        356,
        184,
        "PERMITE",
        ["50 + identidade correta", "Backend pode executar"],
        "allow",
        "check",
    )
    d.node(
        1180,
        578,
        356,
        184,
        "NEGA",
        ["51 ou identidade indevida", "Backend não deve executar"],
        "red",
        "stop",
    )
    d.arrow([(430, 502), (492, 502)], "identity")
    d.arrow([(1088, 403), (1180, 403)], "allow")
    d.arrow([(1088, 668), (1180, 668)], "red")


def draw_05(d):
    positions = [64, 441, 818, 1195]
    titles = [
        ["Intenção", "em português"],
        ["Rascunho", "Cedar"],
        ["Revisão", "e testes"],
        ["Publicação", "por IaC"],
    ]
    bodies = [
        ["Quem pode fazer o quê?", "Com qual limite?"],
        ["Código + findings", "Ainda sem conceder acesso"],
        ["Identidade e escopo", "Permissões e negativas"],
        ["Change set revisado", "Policy em ENFORCE"],
    ]
    for i, x in enumerate(positions):
        d.node(
            x,
            333,
            341,
            287,
            titles[i],
            bodies[i],
            ["local", "policy", "policy", "gateway"][i],
            ["document", "code", "review", "deploy"][i],
            vertical=True,
        )
        d.tag(
            x + 88,
            265,
            165,
            ["REQUISITO", "RASCUNHO", "VALIDAÇÃO", "POLÍTICA ATIVA"][i],
            ["local", "policy", "policy", "gateway"][i],
            height=38,
            size=14,
        )
    for x in [405, 782, 1159]:
        d.arrow([(x, 483), (x + 36, 483)], "policy")
    d.panel(
        64,
        676,
        718,
        120,
        "GERAÇÃO ASSISTIDA",
        "Stack policy-draft → notebook lê resultado e findings.",
        "policy",
    )
    d.panel(
        818,
        676,
        718,
        120,
        "BARREIRA DE PUBLICAÇÃO",
        "O provider de rascunho não possui CreatePolicy.",
        "red",
    )


def draw_06(d):
    d.node(
        64,
        235,
        422,
        161,
        "Publisher",
        ["Publica e submete", "Não aprova a própria publicação"],
        "registry",
        "document",
    )
    d.node(
        589,
        235,
        422,
        161,
        "Approver",
        ["Revisa e decide", "Não publica registros"],
        "policy",
        "review",
    )
    d.node(
        1114,
        235,
        422,
        161,
        "Consumer",
        ["Busca capacidades aprovadas", "Não publica nem aprova"],
        "identity",
        "search",
    )
    d.tag(106, 494, 330, "DRAFT", "local", height=80, size=25)
    d.tag(599, 494, 402, "PENDING_APPROVAL", "registry", height=80, size=24)
    d.tag(1170, 442, 320, "APPROVED", "allow", height=78, size=24)
    d.tag(1170, 635, 320, "REJECTED", "red", height=78, size=24)
    d.arrow([(275, 396), (275, 494)], "registry", dashed=True)
    d.arrow([(800, 396), (800, 494)], "policy", dashed=True)
    d.arrow([(1325, 442), (1325, 396)], "identity", dashed=True)
    d.arrow([(436, 534), (599, 534)], "registry")
    d.label(518, 503, "submeter", "registry")
    d.arrow([(1001, 516), (1080, 516), (1080, 481), (1170, 481)], "allow")
    d.label(1080, 452, "aprovar", "allow")
    d.arrow([(1001, 550), (1080, 550), (1080, 674), (1170, 674)], "red")
    d.label(1080, 711, "rejeitar", "red")
    d.tag(89, 674, 421, "autoApproval = false", "registry", height=50, size=23)
    d.text(64, 787, "Estados preparados por IaC", 21, C["muted"], 600)
    d.text(668, 787, "AWS_IAM + STS · sem usuários IAM ou chaves permanentes", 21, C["muted"])


def draw_07(d):
    d.panel(64, 226, 425, 565, "SUPERVISOR", "Descobre, confere e solicita execução", "local")
    d.icon(211, 333, "agent", C["local"], 108)
    d.text(98, 494, "Antes de enviar o token:", 23, C["ink"], 700)
    for i, line in enumerate(
        ["✓ Registro APPROVED", "✓ Endpoint na allowlist", "✓ Tool e schema esperados"]
    ):
        d.text(98, 544 + i * 47, line, 22, C["muted"])
    d.node(
        737,
        243,
        425,
        190,
        "Registry",
        ["Busca semântica em AWS", "IAM com sessão STS"],
        "registry",
        "catalog",
    )
    d.node(
        737,
        559,
        425,
        193,
        "Gateway + Policy",
        ["Valida JWT e regra Cedar", "Aprovação do catálogo não basta"],
        "policy",
        "shield",
    )
    d.node(
        1281,
        559,
        255,
        193,
        "Tool de Fraude",
        ["Executa se permitida"],
        "gateway",
        "agent",
        vertical=True,
    )
    d.arrow([(489, 320), (737, 320)], "registry")
    d.label(613, 291, "1 · buscar capacidade", "registry")
    d.arrow([(737, 385), (489, 385)], "registry")
    d.label(613, 423, "2 · descriptor aprovado", "registry")
    d.arrow([(489, 677), (737, 677)], "identity")
    d.label(613, 648, "3 · tools/call + JWT", "identity")
    d.arrow([(1162, 655), (1281, 655)], "allow")
    d.label(1222, 624, "4 · permite", "allow", 16)
    d.tag(754, 466, 757, "Capacidade visível ≠ permissão para invocar", "red", height=47, size=22)


def draw_08(d):
    d.panel(64, 224, 370, 583, "CONTA A", "Domínio de origem", "local")
    d.panel(464, 224, 672, 583, "CONTA C", "Hub de serviços compartilhados", "gateway")
    d.panel(1166, 224, 370, 583, "CONTA B", "Domínio de Fraude", "identity")
    d.node(88, 328, 322, 120, "Usuário + agente", [], "identity", "token")
    d.node(
        88,
        543,
        322,
        164,
        "Supervisor",
        ["AgentCore Runtime", "Orquestração determinística"],
        "local",
        "agent",
    )
    d.node(494, 328, 292, 131, "Registry", ["Busca com IAM / STS"], "registry", "catalog")
    d.node(816, 328, 292, 131, "Policy", ["Regras Cedar"], "policy", "shield")
    d.node(494, 543, 292, 150, "Gateway", ["JWT + chamada MCP"], "gateway", "gateway")
    d.node(816, 696, 292, 86, "Identity", [], "identity", "key", kicker="CREDENCIAL OBO")
    d.node(
        1190,
        543,
        322,
        164,
        "Fraude MCP",
        ["AgentCore Runtime", "Audiência própria"],
        "identity",
        "agent",
    )
    d.rect(494, 727, 292, 55, "#FFFFFF", C["border"], radius=12)
    d.icon(510, 738, "lambda", C["gateway"], 31)
    d.text(556, 762, "Lambda Riscos / K2", 19, C["ink"])
    d.arrow([(249, 448), (249, 543)], "identity")
    d.label(249, 502, "JWT delegado", "identity", 17)
    d.arrow([(410, 574), (449, 574), (449, 394), (494, 394)], "registry")
    d.label(448, 365, "1 · busca", "registry", 15)
    d.arrow([(410, 644), (494, 644)], "identity")
    d.label(452, 685, "2 · JWT", "identity", 15)
    d.arrow([(962, 459), (962, 494), (640, 494), (640, 543)], "policy", dashed=True)
    d.arrow([(786, 605), (1190, 605)], "identity")
    d.label(986, 573, "Token para Fraude · tools/call", "identity", 18)
    d.arrow([(786, 658), (800, 658), (800, 739), (816, 739)], "identity", dashed=True, start=True)
    d.arrow([(640, 693), (640, 727)], "gateway")
    d.text(
        1191,
        374,
        ["Somente o caminho", "via workload do Gateway", "deve alcançar o Runtime."],
        22,
        C["identity"],
    )
    d.icon(1270, 441, "lock", C["identity"], 48)
    d.text(1190, 761, "Validar chamada direta negada", 20, C["muted"])


def draw_09(d):
    d.panel(
        841,
        232,
        695,
        420,
        "DATABRICKS NO AZURE",
        "A fonte controla identidade e acesso aos dados",
        "azure",
    )
    d.node(
        64,
        345,
        279,
        263,
        ["Usuário", "Entra ID"],
        ["JWT para federation"],
        "identity",
        "user",
        vertical=True,
    )
    d.node(
        412,
        345,
        359,
        263,
        ["Adapter", "de extensão"],
        ["Troca delegada RFC 8693", "Sem fallback M2M"],
        "identity",
        "key",
        vertical=True,
    )
    d.node(868, 340, 300, 155, "Token exchange", ["/oidc/v1/token"], "azure", "token")
    d.node(1208, 340, 300, 155, "Unity Catalog", ["Permissões por usuário"], "registry", "lock")
    d.node(
        868,
        525,
        640,
        125,
        "SQL Warehouse",
        ["SELECT current_user() · tabela canário"],
        "azure",
        "database",
    )
    d.arrow([(343, 456), (412, 456)], "identity")
    d.arrow([(771, 420), (868, 420)], "identity", start=True)
    d.label(820, 388, "1 · troca", "identity", 16)
    d.arrow([(771, 578), (868, 578)], "identity")
    d.label(820, 548, "2 · SQL", "identity", 16)
    d.arrow([(1358, 495), (1358, 525)], "registry", dashed=True)
    d.tag(
        64, 250, 707, "Extensão separada do Gateway nesta entrega", "identity", height=47, size=21
    )
    cards = [
        (64, "01 · Identidade exata", "current_user() == usuário esperado", "identity", "user"),
        (563, "02 · Grants distintos", "Um usuário acessa; o outro é recusado", "registry", "lock"),
        (1062, "03 · Falha fecha o acesso", "Sem troca válida, nenhuma consulta", "red", "stop"),
    ]
    for x, title, body, tone, icon in cards:
        d.node(x, 678, 474, 128, title, [body], tone, icon)


DRAW = [draw_00, draw_01, draw_02, draw_03, draw_04, draw_05, draw_06, draw_07, draw_08, draw_09]


def image_cell(page):
    png = OUT / "png" / f"{page['id']}.png"
    return {
        "cell_type": "markdown",
        "id": "diagram-" + page["id"][:2],
        "metadata": {"tags": ["santander_diagram"]},
        "source": [
            f"![{page['description']}](attachment:diagrama.png)\n",
            "\n",
            f"**Objetivo visual:** {page['result']}\n",
            "\n",
            f"[Abrir PNG](../docs/diagramas/png/{page['id']}.png) · "
            f"[SVG editável](../docs/diagramas/svg/{page['id']}.svg) · "
            "[Galeria dos notebooks](../docs/diagramas/index.html)",
        ],
        "attachments": {"diagrama.png": {"image/png": base64.b64encode(png.read_bytes()).decode()}},
    }


def embed_notebooks():
    for page in PAGES:
        path = ROOT / "notebooks" / (page["id"] + ".ipynb")
        notebook = json.loads(path.read_text())
        # Altera só a figura criada por este script; preserva código, outputs e edições.
        cells = [
            c
            for c in notebook["cells"]
            if "santander_diagram" not in c.get("metadata", {}).get("tags", [])
        ]
        cells.insert(1, image_cell(page))
        notebook["cells"] = cells
        path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n")


def write_gallery():
    template = (ROOT / "scripts" / "templates" / "diagrams.html").read_text()
    extras = [
        (
            "10_blog_multi_account_gateway_mcp",
            "banking",
            "Gateway",
            "Um agente, três áreas, quatro contas.",
            "Referência do artigo AWS com Strands e M2M nas ferramentas.",
            "Comparar a identidade humana na entrada e a credencial técnica nos destinos.",
        ),
        (
            "11_gateways_por_conta_identity_policy",
            "federation",
            "Policy",
            "Cada conta tem sua própria porta.",
            "Gateway, Identity OBO e Policy independentes em quatro contas.",
            "Entender a autonomia de autorização de cada domínio.",
        ),
        (
            "12_cenario_santander_integrado",
            "journey",
            "Identity",
            "Uma chamada entre áreas, até a fonte.",
            "Agentes na conta A → hub → Gateway da conta B → MCP Databricks.",
            "Distinguir agentes no hub e verificar a identidade humana na fonte.",
        ),
        (
            "13_ingestao_acl_memoria",
            "ingestao",
            "Registry",
            "Conhecimento compartilhado, acesso individual.",
            "Contrato local de ingestão, ACL, revogação e memória por usuário.",
            "Compartilhar o índice sem compartilhar todas as permissões.",
        ),
    ]
    pages = PAGES + [
        {
            "id": name,
            "pillar": pillar,
            "title": title,
            "description": description,
            "result": result,
            "notes": [
                "Leia o runbook do cenário antes de habilitar a execução cloud.",
                "Resultados locais não comprovam os serviços gerenciados.",
            ],
            "svg": f"../{folder}/arquitetura.svg",
            "png": f"../{folder}/arquitetura.png",
        }
        for name, folder, pillar, title, description, result in extras
    ]
    manifest = json.dumps(pages, ensure_ascii=False).replace("</", "<\\/")
    (OUT / "manifest.json").write_text(json.dumps(pages, ensure_ascii=False, indent=2) + "\n")
    (OUT / "index.html").write_text(template.replace("__DIAGRAM_MANIFEST__", manifest))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--svg-only", action="store_true", help="Não renderizar PNG nem incorporar imagens"
    )
    args = parser.parse_args()
    for subdir in ["svg", "png"]:
        (OUT / subdir).mkdir(parents=True, exist_ok=True)
    for page, draw in zip(PAGES, DRAW, strict=True):
        diagram = Diagram(page)
        draw(diagram)
        svg = OUT / "svg" / f"{page['id']}.svg"
        svg.write_text(diagram.finish())
        if not args.svg_only:
            renderer = shutil.which("rsvg-convert")
            if not renderer:
                raise SystemExit("Instale librsvg (rsvg-convert) ou use --svg-only.")
            subprocess.run(
                [
                    renderer,
                    "--width",
                    "2400",
                    "--height",
                    "1500",
                    "--output",
                    str(OUT / "png" / f"{page['id']}.png"),
                    str(svg),
                ],
                check=True,
            )
    write_gallery()
    if not args.svg_only:
        embed_notebooks()
    print("10 diagramas SVG" + (" + PNG incorporados aos notebooks." if not args.svg_only else "."))
    print("Galeria: docs/diagramas/index.html")


if __name__ == "__main__":
    main()
