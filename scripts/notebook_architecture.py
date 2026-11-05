"""Arquiteturas AWS: SVG com ícones oficiais e rotas explícitas; PNG para Jupyter."""

import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from santander_demo.notebook_catalog import display_number  # noqa: E402
from scripts.notebook_architecture_svg import BLUE, ORANGE, PURPLE, RED, TEAL, Diagram  # noqa: E402

ART = ROOT / "docs/diagramas/aulas"


def preflight():
    d = Diagram(
        "00",
        "Preparar a conta e a sessão",
        height=700,
        subtitle="Primeiro identificar o chamador; depois construir os serviços nas próximas aulas.",
    )
    d.cloud()
    d.service("nb", 190, 295, "client", "Notebook na AWS", "boto3 / sessão do participante")
    d.service("sts", 565, 295, "sts", "AWS STS", "GetCallerIdentity")
    d.group(
        "state",
        910,
        220,
        380,
        210,
        "Registro da execução",
        icon="client",
        color=BLUE,
        rows=("Conta + região + run_id", "IDs em .workshop/", "NEW ou RESUME"),
    )
    d.connect("nb", "sts", label="1  ·  consultar identidade", at=(380, 308))
    d.connect("sts", "state", label="2  ·  conferir conta / ARN", at=(763, 308), kind="config")
    d.note(
        125,
        515,
        500,
        "SDK conhece as APIs requeridas.\nPermissões e quotas são exercitadas nas aulas.",
        title="Verificação do SDK",
    )
    d.note(
        790,
        515,
        490,
        "Gateway · Runtime · Policy · Registry · Memory · RAG\nNenhum deles é criado pelo preflight.",
        title="O que vem depois",
    )
    return d


def gateway():
    d = Diagram(
        "01",
        "Cognito → Gateway → ferramenta Lambda",
        height=830,
        subtitle="O notebook autentica a pessoa e chama a ferramenta MCP; a função executa na AWS.",
    )
    d.cloud()
    d.service("nb", 185, 365, "client", "Notebook / MCP client")
    d.service("idp", 185, 165, "cognito", "Amazon Cognito", "User Pool + app client")
    d.group(
        "gw",
        510,
        290,
        340,
        225,
        "AgentCore Gateway",
        color=PURPLE,
        rows=("Authorizer JWT", "tools/list · tools/call", "Target Lambda"),
    )
    d.group(
        "fn",
        1075,
        305,
        280,
        195,
        "AWS Lambda",
        icon="lambda",
        color=ORANGE,
        rows=("customer_risk", "Dados sintéticos"),
    )
    d.line([(160, 365), (160, 287)], label="login", at=(121, 328))
    d.line([(210, 290), (210, 365)], label="ID token", at=(265, 329))
    d.connect("nb", "gw", via=((365, 396), (365, 402.5)), label="/mcp  ·  JWT", at=(365, 373))
    d.connect("gw", "fn", label="tools/call", at=(960, 425))
    d.badge(902, 345, "IAM role")
    d.service("secret", 185, 600, "secrets", "Secrets Manager", "Senhas sintéticas", size=48)
    d.service("role", 685, 600, "role", "IAM", "Roles Gateway e Lambda", size=48)
    d.service("logs", 1215, 600, "cloudwatch", "CloudWatch Logs", "Retenção: 7 dias", size=48)
    d.connect("secret", "nb", start="T", end="B", kind="config")
    d.connect("role", "gw", start="T", end="B", kind="config", label="permissões", at=(751, 557))
    d.connect("fn", "logs", start="B", end="T", kind="config", label="logs", at=(1255, 557))
    return d


def identity():
    d = Diagram(
        "02",
        "Identidade: emissor, audiência e assinatura",
        height=825,
        subtitle="Mesmo User Pool; três credenciais comparadas contra o mesmo authorizer.",
    )
    d.cloud()
    d.service("user", 160, 365, "user", "Analista", "Mesma pessoa / sub")
    d.group(
        "pool",
        365,
        190,
        350,
        420,
        "Amazon Cognito",
        icon="cognito",
        color=RED,
        rows=("Aplicação A · aud permitido", "Aplicação B · outro aud"),
    )
    d.note(
        389,
        460,
        295,
        "Token com aud editado;\na assinatura fica inválida.",
        title="Terceiro caso: adulteração",
        color=RED,
    )
    d.group(
        "gw",
        1000,
        235,
        345,
        300,
        "AgentCore Gateway",
        color=PURPLE,
        rows=(
            "Validar assinatura",
            "Conferir issuer",
            "Conferir audiência",
            "Encaminhar se válido",
        ),
    )
    d.connect("user", "pool", via=((280, 396), (280, 400)), label="autenticar", at=(290, 372))
    d.line([(715, 287), (1000, 287)], label="A  ·  ALLOW", at=(855, 267))
    d.line([(715, 350), (1000, 350)], label="B  ·  DENY: aud", at=(855, 333), kind="deny")
    d.line([(715, 490), (1000, 490)], label="DENY: assinatura", at=(855, 470), kind="deny")
    d.service("fn", 1172, 625, "lambda", "AWS Lambda", "Controle positivo com A", size=48)
    d.connect("gw", "fn", start="B", end="T", label="tools/call permitido", at=(1172, 584))
    d.note(
        160,
        666,
        750,
        "Confiar no emissor não autoriza todas as aplicações.\nAdulterar claims não produz uma credencial válida.",
        title="O que comparar nas respostas",
    )
    return d


def runtime():
    d = Diagram(
        "03",
        "Implantar e invocar um Runtime MCP",
        height=830,
        subtitle="Nosso notebook faz deploy direto de código: ZIP ARM64 em S3, sem imagem ECR.",
    )
    d.cloud()
    d.service("nb", 175, 350, "client", "Notebook na AWS", "Código Python + boto3")
    d.service("s3", 475, 180, "s3", "Amazon S3", "ZIP + dependências")
    d.group(
        "rt",
        740,
        240,
        355,
        285,
        "AgentCore Runtime",
        rows=(
            "Servidor MCP",
            "workload_identity",
            "Sessão de execução",
            "Código Python 3.12 / ARM64",
        ),
    )
    d.service("sts", 1280, 350, "sts", "AWS STS", "Identidade do workload")
    d.line(
        [(175, 343), (175, 211), (420, 211)],
        label="1  ·  empacotar / enviar",
        at=(324, 192),
        kind="config",
    )
    d.line(
        [(530, 211), (660, 211), (660, 285), (740, 285)],
        label="2  ·  criar Runtime",
        at=(641, 179),
        kind="config",
    )
    d.connect(
        "nb", "rt", via=((540, 381), (540, 382.5)), label="3  ·  InvokeAgentRuntime", at=(479, 364)
    )
    d.badge(370, 416, "SigV4 / IAM")
    d.connect(
        "rt", "sts", via=((1160, 382.5), (1160, 381)), label="GetCallerIdentity", at=(1190, 339)
    )
    d.service(
        "role", 915, 615, "role", "IAM execution role", "Identidade do código hospedado", size=48
    )
    d.service("logs", 1280, 615, "cloudwatch", "CloudWatch Logs", "Logs do Runtime", size=48)
    d.connect("role", "rt", start="T", end="B", kind="config")
    d.line([(1095, 480), (1170, 480), (1170, 639), (1225, 639)], kind="config")
    d.note(
        125,
        595,
        540,
        "Sessão que invoca ≠ role de execução.\nCompare o ARN retornado pelo código com o ARN do notebook.",
        title="Fronteira de identidade",
    )
    return d


def policy():
    d = Diagram(
        "04",
        "Autenticar a pessoa e autorizar a ferramenta",
        height=835,
        subtitle="Cognito confirma a identidade; Cedar decide a chamada antes da execução Lambda.",
    )
    d.cloud()
    d.service("nb", 150, 310, "client", "Notebook / MCP")
    d.service("cog", 440, 310, "cognito", "Amazon Cognito", "Analista / auditor")
    d.group(
        "gw",
        720,
        245,
        305,
        205,
        "AgentCore Gateway",
        color=PURPLE,
        rows=("JWT validado", "customer_risk"),
    )
    d.service("fn", 1250, 315, "lambda", "AWS Lambda", "Apenas se ALLOW")
    d.connect("nb", "cog", label="login", at=(295, 319))
    d.connect("cog", "gw", via=((610, 341), (610, 347.5)), label="JWT", at=(610, 322))
    d.connect("gw", "fn", label="invocar", at=(1115, 326))
    d.group(
        "policy",
        675,
        565,
        390,
        155,
        "AgentCore Policy",
        color=TEAL,
        rows=("Engine ENFORCE · regras Cedar",),
    )
    d.connect(
        "gw",
        "policy",
        start="B",
        end="T",
        label="principal · ação · contexto",
        at=(872, 506),
        both=True,
    )
    d.note(
        115,
        567,
        490,
        "Analista / cliente-001  →  ALLOW\nAnalista / cliente-002  →  DENY\nAuditor / cliente-001  →  DENY",
        title="Matriz da validação",
        color=PURPLE,
    )
    return d


def authoring():
    d = Diagram(
        "05",
        "Gerar, revisar e observar uma política",
        height=840,
        subtitle="Um rascunho LOG_ONLY não substitui a política ACTIVE do Gateway.",
    )
    d.cloud()
    d.service("intent", 150, 225, "client", "Intenção de acesso", "Notebook")
    d.group(
        "gen",
        365,
        178,
        300,
        188,
        "AgentCore Policy",
        rows=("Geração de Cedar", "Assets + findings"),
    )
    d.service("review", 875, 225, "client", "Revisão do Cedar", "Ler + testar com cedarpy")
    d.group("draft", 1095, 178, 285, 188, "Rascunho", rows=("Cedar revisado", "LOG_ONLY"))
    d.connect("intent", "gen", label="1  ·  gerar", at=(280, 236))
    d.connect("gen", "review", label="2  ·  revisar", at=(744, 236))
    d.connect("review", "draft", label="3  ·  criar", at=(1010, 236))
    d.group(
        "active",
        365,
        530,
        330,
        168,
        "AgentCore Policy",
        rows=("ACTIVE · ENFORCE", "Proteção aplicada"),
    )
    d.group(
        "gw",
        835,
        530,
        300,
        168,
        "AgentCore Gateway",
        color=PURPLE,
        rows=("Chamada de controle", "Autorização atual"),
    )
    d.service("fn", 1285, 583, "lambda", "AWS Lambda", size=48)
    d.connect("active", "gw", label="decisão", at=(765, 594), both=True)
    d.connect("gw", "fn")
    d.line(
        [(1237.5, 366), (1237.5, 455), (985, 455), (985, 530)],
        label="observar em LOG_ONLY",
        at=(1110, 440),
        kind="config",
    )
    d.note(
        110,
        435,
        550,
        "A promoção é uma decisão separada.\nA aula mantém o engine ENFORCE e testa a proteção existente.",
        title="Revisão antes de conceder acesso",
    )
    return d


def registry():
    d = Diagram(
        "06",
        "Registry: catálogo e descoberta autenticada",
        height=725,
        subtitle="Governar descritores e aprovações não concede acesso ao endpoint catalogado.",
    )
    d.cloud()
    d.service("nb", 190, 240, "client", "Notebook na AWS")
    d.service("iam", 530, 240, "iam", "AWS IAM", "Sessão / SigV4")
    d.group(
        "reg",
        875,
        185,
        400,
        285,
        "Agent Registry",
        color=TEAL,
        rows=(
            "Catálogo de capacidades",
            "Descoberta autenticada",
            "Aprovação manual",
            "Sem autoaprovação",
        ),
    )
    d.connect("nb", "iam", label="assinar chamada", at=(355, 248))
    d.connect(
        "iam", "reg", via=((735, 271), (735, 327.5)), label="consultar catálogo", at=(728, 248)
    )
    d.service("anon", 190, 490, "user", "Chamador anônimo", size=48)
    d.line(
        [(245, 514), (1075, 514), (1075, 470)],
        label="DENY  ·  sem assinatura AWS",
        at=(637, 499),
        kind="deny",
    )
    d.note(
        485,
        572,
        800,
        "O catálogo começa sem publicação automática.\nPublicação, aprovação e consumo serão exercitados na aula 08.",
        title="Governança do catálogo",
    )
    return d


def personas():
    d = Diagram(
        "07",
        "Três personas IAM e permissões distintas",
        height=830,
        subtitle="AssumeRole emite sessões temporárias; a role determina o acesso aos serviços.",
    )
    d.cloud()
    d.service("sts", 165, 355, "sts", "AWS STS", "AssumeRole")
    for key, y, title, detail in [
        ("pub", 190, "Publisher", "Publicar / submeter"),
        ("adm", 370, "Approver", "Revisar / aprovar"),
        ("con", 550, "Consumer", "Descobrir / consumir"),
    ]:
        d.group(key, 405, y, 310, 132, title, icon="iam", color=RED, rows=(detail,))
        d.line([(220, 386), (310, 386), (310, y + 66), (405, y + 66)], kind="config")
    d.group(
        "reg", 1030, 220, 315, 180, "Agent Registry", rows=("GetRegistry", "Três personas: ALLOW")
    )
    for y in [256, 436, 616]:
        d.line([(715, y), (865, y), (865, 310), (1030, 310)])
    d.label(865, 196, "Leitura do Registry")
    d.group(
        "rt", 1030, 515, 315, 180, "AgentCore Runtime", rows=("GetAgentRuntime", "Consumer: ALLOW")
    )
    d.line(
        [(715, 650), (920, 650), (920, 605), (1030, 605)], label="leitura permitida", at=(867, 709)
    )
    d.note(
        115,
        689,
        760,
        "Publisher / Runtime: DENY    ·    Approver / Runtime: DENY",
        title="Negativas verificadas na mesma matriz",
        color=RED,
    )
    return d


def discovery():
    d = Diagram(
        "08",
        "Da publicação à invocação autorizada",
        height=870,
        subtitle="Duas sessões descobrem a mesma capacidade; só uma possui permissão de invocação.",
    )
    d.cloud()
    d.service("pub", 175, 190, "iam", "Publisher", size=48)
    d.group(
        "reg",
        535,
        165,
        395,
        235,
        "Agent Registry",
        rows=("Publicar descritor", "Submeter para aprovação", "Registro APPROVED"),
    )
    d.service("adm", 1190, 190, "iam", "Approver", size=48)
    d.connect(
        "pub",
        "reg",
        via=((340, 214), (340, 260), (535, 260)),
        label="publicar / submeter",
        at=(354, 193),
    )
    d.line(
        [(1135, 214), (1015, 214), (1015, 280), (930, 280)],
        label="revisar / aprovar",
        at=(1038, 192),
        kind="config",
    )
    d.service("consumer", 175, 480, "iam", "Consumer", "Sessão IAM completa", size=48)
    d.service("limited", 175, 650, "iam", "Consumer limitado", "Somente descoberta", size=48)
    d.group(
        "rt",
        1015,
        500,
        330,
        190,
        "AgentCore Runtime",
        rows=("Capacidade descoberta", "Autorização IAM própria"),
    )
    d.line([(230, 504), (455, 504), (455, 375), (535, 375)], label="descobrir", at=(371, 482))
    d.line([(230, 674), (455, 674), (455, 375)], kind="config", label="descobrir", at=(359, 650))
    d.line([(230, 550), (800, 550), (800, 570), (1015, 570)], label="invocar: ALLOW", at=(741, 532))
    d.line(
        [(230, 674), (335, 674), (335, 768), (875, 768), (875, 640), (1015, 640)],
        label="invocar: DENY",
        at=(719, 791),
        kind="deny",
    )
    return d


def integration():
    d = Diagram(
        "09",
        "JWT na entrada; IAM no salto ao Runtime",
        height=825,
        subtitle="A identidade humana é autorizada no Gateway. O Runtime observa a identidade de execução.",
    )
    d.cloud()
    d.service("nb", 170, 365, "client", "Notebook / MCP")
    d.service("cog", 170, 165, "cognito", "Amazon Cognito", size=48)
    d.line([(170, 297), (170, 358)], label="JWT humano", at=(244, 332))
    d.group(
        "gw",
        495,
        290,
        340,
        220,
        "AgentCore Gateway",
        color=PURPLE,
        rows=("Authorizer Cognito", "Policy ENFORCE", "Target MCP Runtime"),
    )
    d.group(
        "rt",
        1030,
        290,
        340,
        220,
        "AgentCore Runtime",
        rows=("MCP · workload_identity", "Role do código hospedado", "Sem JWT humano neste salto"),
    )
    d.connect("nb", "gw", label="/mcp + JWT", at=(350, 375))
    d.connect("gw", "rt", label="SigV4", at=(933, 423))
    d.badge(862, 348, "Role Gateway")
    d.group("pol", 495, 610, 340, 120, "AgentCore Policy", rows=("Cedar: pessoa + ferramenta",))
    d.connect("gw", "pol", start="B", end="T", label="ALLOW / DENY", at=(665, 566), both=True)
    d.service("sts", 1200, 620, "sts", "AWS STS", "ARN do workload", size=48)
    d.connect("rt", "sts", start="B", end="T", label="GetCallerIdentity", at=(1200, 566))
    d.note(90, 587, 355, "Analista: ALLOW\nAuditor: DENY", title="Validação MCP", color=PURPLE)
    return d


def memory():
    d = Diagram(
        "15",
        "Memory e a autorização atual da pessoa",
        height=850,
        subtitle="A referência fica na memória; o acesso ao documento depende da concessão atual na fonte.",
    )
    d.cloud()
    d.service("nb", 160, 370, "client", "Notebook")
    d.service("pool", 160, 165, "cognito", "Cognito User Pool", "Autenticação", size=48)
    d.line([(160, 309), (160, 363)], label="JWT", at=(207, 343))
    d.group(
        "identity",
        405,
        300,
        330,
        205,
        "Cognito Identity Pool",
        icon="cognito",
        color=RED,
        rows=("JWT → credenciais AWS", "Role IAM por pessoa"),
    )
    d.connect("nb", "identity", label="token da pessoa", at=(308, 380))
    d.group(
        "session",
        835,
        300,
        270,
        205,
        "Sessão IAM",
        icon="iam",
        color=RED,
        rows=("actor = sub", "Partição da pessoa"),
    )
    d.connect("identity", "session", label="federar", at=(786, 381))
    d.service("mem", 1260, 175, "agentcore", "AgentCore Memory", "Evento / referência", size=58)
    d.service("data", 1260, 535, "dynamodb", "Amazon DynamoDB", "Visão atual autorizada", size=58)
    d.line(
        [(1105, 365), (1150, 365), (1150, 204), (1205, 204)], label="próprio actor", at=(1079, 246)
    )
    d.line(
        [(1105, 440), (1150, 440), (1150, 564), (1205, 564)],
        label="própria partição",
        at=(1074, 531),
    )
    d.note(
        110,
        638,
        760,
        "1. Guardar referência no actor do analista.\n2. Revogar a visão autorizada no DynamoDB.\n3. Relê-la na memória não restaura o acesso ao dado.",
        title="Validação de revogação",
        color=RED,
    )
    d.line([(795, 701), (1260, 701), (1260, 680)], kind="config", arrow=True)
    return d


def rag():
    d = Diagram(
        "16",
        "RAG: contexto autorizado antes da geração",
        height=910,
        subtitle="JWT humano → Policy → ACL nativa. O modelo recebe somente os trechos recuperados.",
    )
    d.cloud()
    d.service("nb", 155, 345, "client", "Notebook", "Pergunta + JWT")
    d.service("cog", 155, 155, "cognito", "Amazon Cognito", size=48)
    d.line([(155, 280), (155, 338)], label="autenticar", at=(229, 316))
    d.group(
        "rt",
        390,
        290,
        340,
        235,
        "AgentCore Runtime",
        rows=("Agente HTTP", "Validar JWT / derivar sub", "Recuperar → gerar"),
    )
    d.group(
        "gw",
        915,
        290,
        300,
        235,
        "AgentCore Gateway",
        color=PURPLE,
        rows=("JWT humano", "rag___Retrieve", "Conector nativo"),
    )
    d.connect("nb", "rt", via=((305, 376), (305, 407.5)), label="1  ·  invocar", at=(298, 351))
    d.connect("rt", "gw", label="2  ·  MCP + JWT", at=(823, 389))
    d.group("pol", 860, 620, 330, 140, "AgentCore Policy", rows=("userContext.userId == sub",))
    d.connect(
        "gw",
        "pol",
        start="B",
        end="T",
        via=((1065, 578), (1025, 578)),
        label="ENFORCE",
        at=(1009, 567),
        both=True,
    )
    d.service("kb", 1325, 580, "bedrock", "Knowledge Base", "MANAGED / ACL nativa", size=50)
    d.line([(1215, 440), (1325, 440), (1325, 573)], label="3  ·  Retrieve", at=(1283, 418))
    d.service("s3", 1325, 165, "s3", "Amazon S3", "Corpus + ACL", size=50)
    d.line([(1380, 190), (1390, 190), (1390, 605), (1380, 605)], kind="config")
    d.label(1309, 340, "ingestão + ACL", size=14)
    d.service("model", 560, 650, "bedrock", "Amazon Bedrock", "Nova Lite / Converse", size=58)
    d.connect(
        "rt",
        "model",
        start="B",
        end="T",
        label="4  ·  contexto autorizado",
        at=(560, 593),
        both=True,
    )
    d.line(
        [(730, 482), (784, 482), (784, 808), (1325, 808), (1325, 734)],
        label="DENY: Retrieve direto pelo Runtime",
        at=(1010, 831),
        kind="deny",
    )
    return d


def accounts():
    d = Diagram(
        "90",
        "Quatro contas e suas fronteiras",
        height=825,
        legacy=True,
        subtitle="O preflight consulta STS em cada sessão e exige quatro IDs de conta diferentes.",
    )
    panels = [
        (40, 120, "Plataforma / hub C"),
        (860, 120, "Retail / origem A"),
        (40, 450, "Transaction / fonte B"),
        (860, 450, "Lending"),
    ]
    for i, (x, y, title) in enumerate(panels, 1):
        d.cloud(x, y, 540, 275, title=f"Conta {i}  /  {title}")
        d.service("gw" + str(i), x + 135, y + 78, "agentcore", "Gateway + Policy", size=50)
        d.service("rt" + str(i), x + 390, y + 78, "agentcore", "Runtime + Memory", size=50)
    d.service("nb", 720, 340, "client", "Notebook AWS", "Perfis / sessões legados", size=55)
    for pts in [
        [(665, 367.5), (620, 367.5), (620, 255), (580, 255)],
        [(775, 367.5), (815, 367.5), (815, 255), (860, 255)],
        [(665, 367.5), (620, 367.5), (620, 585), (580, 585)],
        [(775, 367.5), (815, 367.5), (815, 585), (860, 585)],
    ]:
        d.line(pts, kind="config")
    d.label(720, 238, "STS / preflight", size=17)
    return d


def central_agent():
    d = Diagram(
        "91",
        "Agente central e três domínios AWS",
        height=850,
        legacy=True,
        subtitle="A plataforma agrega ferramentas MCP; cada domínio mantém seus próprios serviços e dados.",
    )
    d.cloud(35, 115, 535, 640, title="Conta 1  /  plataforma")
    d.group(
        "agent",
        95,
        200,
        415,
        200,
        "AgentCore Runtime",
        rows=("Agente central", "Pessoa autenticada"),
    )
    d.group(
        "hub",
        95,
        510,
        415,
        190,
        "AgentCore Gateway",
        color=PURPLE,
        rows=("Cognito + Policy", "Descoberta MCP agregada"),
    )
    d.connect("agent", "hub", start="B", end="T", label="descobrir / chamar", at=(302, 458))
    for i, (name, y) in enumerate([("Retail", 115), ("Transaction", 335), ("Lending", 555)], 2):
        d.cloud(895, y, 510, 200, title=f"Conta {i}  /  {name}")
        d.service("domain" + str(i), 1040, y + 68, "agentcore", "Gateway", size=42)
        d.service("runtime" + str(i), 1270, y + 68, "agentcore", "Runtime MCP", size=42)
        d.connect("domain" + str(i), "runtime" + str(i))
        d.line([(510, 605), (720, 605), (720, y + 89), (985, y + 89)])
        d.label(773, y + 73, name.lower() + "___…", size=16)
    return d


def federation():
    d = Diagram(
        "92",
        "Autorização no hub e no domínio",
        height=825,
        legacy=True,
        subtitle="Duas contas no caminho principal; Retail e Lending continuam exigidas pelo legado.",
    )
    d.cloud(30, 190, 600, 460, title="Conta 1  /  plataforma")
    d.cloud(785, 190, 625, 460, title="Conta 3  /  Transaction")
    d.service("nb", 150, 355, "client", "Notebook", "JWT Cognito", size=48)
    d.group(
        "hub",
        330,
        315,
        270,
        200,
        "Gateway do hub",
        color=PURPLE,
        rows=("Authorizer JWT", "Policy do hub"),
    )
    d.group(
        "domain",
        825,
        315,
        270,
        200,
        "Gateway de domínio",
        color=PURPLE,
        rows=("Entrada própria", "Policy do domínio"),
    )
    d.service("rt", 1260, 390, "agentcore", "Runtime MCP", "Ferramenta / fonte", size=48)
    d.connect("nb", "hub", via=((260, 379), (260, 415)), label="entrada central", at=(265, 348))
    d.connect("hub", "domain", label="caminho federado", at=(713, 395))
    d.connect("domain", "rt", label="ALLOW", at=(1150, 393))
    d.line(
        [(150, 348), (150, 158), (960, 158), (960, 315)],
        label="teste da entrada direta",
        at=(700, 144),
        kind="config",
    )
    d.note(
        95,
        702,
        560,
        "Conta 2 / Retail  +  Conta 4 / Lending",
        title="Dependências adicionais da implantação",
        color=RED,
    )
    d.note(
        810,
        702,
        540,
        "Entrada autorizada ≠ acesso irrestrito à fonte.",
        title="Duas decisões de Policy",
        color=PURPLE,
    )
    return d


def databricks():
    d = Diagram(
        "13",
        "Identidade e concessões na fonte sintética",
        height=820,
        legacy=True,
        subtitle="O simulador Databricks executa no Runtime e usa DynamoDB; não é um workspace Databricks real.",
    )
    d.cloud(30, 130, 370, 520, title="Conta 1 / plataforma")
    d.cloud(600, 130, 810, 520, title="Conta 3 / Transaction")
    d.service("cog", 215, 215, "cognito", "Amazon Cognito", size=48)
    d.service("nb", 215, 440, "client", "Notebook / pessoa", size=48)
    d.connect("cog", "nb", start="B", end="T", label="JWT", at=(260, 382))
    d.group(
        "gw",
        640,
        245,
        280,
        180,
        "AgentCore Gateway",
        color=PURPLE,
        rows=("Policy na entrada", "Ferramentas MCP"),
    )
    d.group(
        "rt",
        1025,
        245,
        345,
        190,
        "Runtime MCP",
        rows=("Verificar JWT + grants", "Simulador Databricks"),
    )
    d.line(
        [(270, 464), (510, 464), (510, 335), (640, 335)], label="JWT + tools/call", at=(491, 448)
    )
    d.connect("gw", "rt", label="consulta", at=(971, 316))
    d.service("ddb", 1200, 510, "dynamodb", "Amazon DynamoDB", "Dados + concessões", size=43)
    d.connect("rt", "ddb", start="B", end="T")
    d.note(
        90,
        697,
        1180,
        "Retail e Lending também são exigidas pelo manifesto da implantação atual.",
        title="Quatro contas no ambiente legado",
        color=RED,
    )
    return d


def integrated():
    d = Diagram(
        "14",
        "Origem A → hub C → fonte B",
        height=850,
        legacy=True,
        subtitle="Agentes de Riscos e Fraude usam capacidades descobertas no catálogo e autorizadas na fonte.",
    )
    for x, w, title in [
        (30, 365, "Conta 2 / Retail · A"),
        (530, 370, "Conta 1 / plataforma · C"),
        (1040, 370, "Conta 3 / Transaction · B"),
    ]:
        d.cloud(x, 135, w, 570, title=title)
    d.group(
        "risks",
        65,
        230,
        295,
        175,
        "Runtime Riscos",
        rows=("App Riscos / aud própria", "Agente na origem"),
    )
    d.group(
        "fraud",
        65,
        500,
        295,
        175,
        "Runtime Fraude",
        rows=("App Fraude / aud própria", "Agente na origem"),
    )
    d.group(
        "reg",
        563,
        215,
        304,
        175,
        "Agent Registry",
        rows=("Registros APPROVED", "Descritores de capacidades"),
    )
    d.group(
        "hub",
        563,
        500,
        304,
        175,
        "Gateway + Policy",
        color=PURPLE,
        rows=("Hub C", "Entrada federada"),
    )
    d.group(
        "source",
        1070,
        215,
        310,
        235,
        "Gateway + Runtime",
        rows=("Fonte B / MCP", "JWT humano + ACL", "Simulador Databricks"),
    )
    d.service("ddb", 1225, 565, "dynamodb", "Amazon DynamoDB", size=48)
    d.line(
        [(563, 302), (467, 302), (467, 317), (360, 317)],
        label="descoberta",
        at=(461, 276),
        kind="config",
    )
    d.line([(563, 340), (487, 340), (487, 526), (360, 526)], kind="config")
    d.line([(360, 365), (434, 365), (434, 588), (563, 588)])
    d.line([(360, 588), (563, 588)], label="chamada", at=(465, 568))
    d.line([(867, 588), (971, 588), (971, 332.5), (1070, 332.5)], label="capacidade", at=(971, 466))
    d.connect("source", "ddb", start="B", end="T", label="concessão atual", at=(1225, 515))
    d.note(
        70,
        747,
        1250,
        "Lending é a quarta conta exigida pela federação atual, fora do caminho A → C → B.",
        color=RED,
    )
    return d


def cleanup():
    d = Diagram(
        "99",
        "Limpar na ordem das dependências",
        height=850,
        subtitle="Inventariar, validar a propriedade e aguardar a exclusão antes de remover IDs do registro.",
    )
    d.cloud()
    boxes = [
        (
            "scope",
            80,
            185,
            "1  Escopo",
            "client",
            BLUE,
            ("all ou rag-runtime", "Conferir IDs e propriedade"),
        ),
        (
            "links",
            570,
            185,
            "2  Integrações",
            "agentcore",
            PURPLE,
            ("Targets / registros", "Consumidores antes das fontes"),
        ),
        (
            "svc",
            1060,
            185,
            "3  Serviços",
            "agentcore",
            TEAL,
            ("Runtime / Gateway / Registry", "Memory / base RAG"),
        ),
        (
            "data",
            1060,
            515,
            "4  Dados e artefatos",
            "s3",
            ORANGE,
            ("S3 / DynamoDB / logs", "Itens desta execução"),
        ),
        (
            "iam",
            570,
            515,
            "5  Identidades",
            "iam",
            RED,
            ("Roles / pools Cognito", "Segredo: agendar 7 dias"),
        ),
        (
            "state",
            80,
            515,
            "6  Confirmar ausência",
            "client",
            BLUE,
            ("Registro conciliado", "all → COMPLETE / CLEANED"),
        ),
    ]
    for key, x, y, title, icon, color, rows in boxes:
        d.group(key, x, y, 300, 185, title, icon=icon, color=color, rows=rows)
    d.connect("scope", "links", kind="step")
    d.connect("links", "svc", kind="step")
    d.connect(
        "svc", "data", start="B", end="T", label="aguardar exclusão", at=(1210, 447), kind="step"
    )
    d.connect("data", "iam", start="L", end="R", kind="step")
    d.connect("iam", "state", start="L", end="R", kind="step")
    d.note(
        100,
        422,
        760,
        "O escopo rag-runtime preserva a base, a fonte e as demais aulas.",
        title="Limpeza parcial explícita",
    )
    return d


RENDERERS = {
    "00": preflight,
    "01": gateway,
    "02": identity,
    "03": runtime,
    "04": policy,
    "05": authoring,
    "06": registry,
    "07": personas,
    "08": discovery,
    "09": integration,
    "10": accounts,
    "11": central_agent,
    "12": federation,
    "13": databricks,
    "14": integrated,
    "15": memory,
    "16": rag,
    "99": cleanup,
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--only", nargs="+", choices=RENDERERS)
    args = parser.parse_args()
    ART.mkdir(parents=True, exist_ok=True)
    for lab, render in RENDERERS.items():
        if args.only and lab not in args.only:
            continue
        number = display_number(lab)
        svg = ART / f"{number}.svg"
        svg.write_text(render().finish())
        subprocess.run(
            ["rsvg-convert", "--zoom", "1.5", "--output", str(ART / f"{number}.png"), str(svg)],
            check=True,
        )
        subprocess.run(
            [
                "pngquant", "--quality=90-100", "--speed", "1", "--strip", "--force",
                "--output", str(ART / f"{number}.png"), "--", str(ART / f"{number}.png"),
            ],
            check=True,
        )
        print(f"{number}: SVG + PNG")


if __name__ == "__main__":
    main()
