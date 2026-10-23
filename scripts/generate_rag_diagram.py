"""Diagrama do lab 16, no mesmo estilo visual dos demais notebooks."""

import subprocess
from pathlib import Path

from scripts.generate_diagrams import Diagram

ROOT = Path(__file__).resolve().parents[1]


def save(d, name):
    folder = ROOT / "docs/rag"
    folder.mkdir(parents=True, exist_ok=True)
    svg, png = folder / f"{name}.svg", folder / f"{name}.png"
    svg.write_text(d.finish().replace("14 / 09", "LAB 16"))
    subprocess.run(
        ["rsvg-convert", "-w", "2400", "-h", "1500", "-o", str(png), str(svg)], check=True
    )
    return png


def generate_processes():
    d = Diagram(
        {
            "id": "16_provisionamento",
            "title": "Como políticas e acessos são criados",
            "subtitle": "As regras viram templates; o pipeline aplica cada fase pelo CloudFormation.",
            "status": "PROVISIONAMENTO · SOMENTE POR IaC",
            "takeaway": "ACLs novas precisam de ingestão. Policies são aplicadas no stack de acesso.",
            "description": "Código de ACLs e Cedar, templates, change set e quatro fases CloudFormation.",
        }
    )
    d.node(
        64,
        245,
        420,
        160,
        "1 · Código versionado",
        ["contract.py: matriz de acesso", "cognito.py: regras Cedar"],
        "local",
        "code",
    )
    d.node(
        590,
        245,
        420,
        160,
        "2 · Templates",
        ["identity.json · data.json", "access-cognito.json"],
        "local",
        "document",
    )
    d.node(
        1116,
        245,
        420,
        160,
        "3 · Revisar e aplicar",
        ["scripts.rag_deploy", "Change set → CloudFormation"],
        "gateway",
        "deploy",
    )
    d.arrow([(484, 325), (590, 325)], "local")
    d.arrow([(1010, 325), (1116, 325)], "gateway")
    d.arrow([(1326, 405), (1326, 475), (224, 475), (224, 550)], "gateway")
    d.label(800, 476, "Aplicar uma fase por vez, respeitando as dependências", "gateway", 19)
    phases = [
        ("bootstrap", ["Bucket privado de artefatos", "ZIP das funções"], "local", "cloud"),
        (
            "identity",
            [
                "Cognito + quatro usuários",
                "Senhas no Secrets Manager",
                "Outputs: subjects e e-mails",
            ],
            "identity",
            "user",
        ),
        (
            "data",
            ["Managed KB + fonte S3", "Documentos e ACLs nativas", "Custom resource: ingestão"],
            "registry",
            "database",
        ),
        (
            "access",
            ["Gateway + 3 permits Cedar", "Role IAM + Identity + logs", "Policy em modo ENFORCE"],
            "policy",
            "shield",
        ),
    ]
    for i, (title, body, tone, icon) in enumerate(phases):
        x = 64 + i * 384
        d.node(x, 550, 320, 200, title, body, tone, icon)
        if i < 3:
            d.arrow([(x + 320, 650), (x + 384, 650)], "gateway")
    d.tag(
        64,
        784,
        1472,
        "Os custom resources publicam o corpus e disparam a ingestão como parte do stack.",
        "local",
        height=42,
        size=20,
    )
    provisioning = save(d, "provisionamento")

    d = Diagram(
        {
            "id": "16_decisao",
            "title": "Onde a consulta pode continuar ou parar",
            "subtitle": "Leia o resultado esperado de cada teste antes de interpretar uma negativa.",
            "status": "CONSULTA · AUTENTICAÇÃO + AUTORIZAÇÃO",
            "takeaway": "Negativa esperada pode ser PASS. Falha operacional nunca comprova autorização.",
            "description": "JWT, Policy, ACL e geração, com caminhos de negativa e falha separados.",
        }
    )
    top = [
        (
            "Autenticar",
            ["Validar assinatura e claims", "JWT Cognito do usuário"],
            "identity",
            "token",
        ),
        (
            "Aplicar Policy",
            ["JWT vincula o userContext", "A/B/C: permit · D: sem permit"],
            "policy",
            "shield",
        ),
        ("Recuperar com ACL", ["Riscos: A e C", "Fraude: B e C"], "registry", "database"),
        (
            "Validar e gerar",
            ["Conferir todos os trechos", "Converse com esse contexto"],
            "gateway",
            "agent",
        ),
    ]
    bottom = [
        ("HTTP 401", ["JWT ausente ou inválido", "Parou na autenticação"], "identity", "stop"),
        (
            "Negativa da Policy",
            ["D ou A tentando usar C", "Sem retrieval nem geração"],
            "policy",
            "stop",
        ),
        (
            "Sem resultados",
            ["Sem trechos recuperados", "Sem geração; rever a busca"],
            "registry",
            "search",
        ),
        (
            "Falha operacional",
            ["Rede, timeout ou modelo", "Investigar; não marcar PASS"],
            "local",
            "review",
        ),
    ]
    for i, ((title, body, tone, icon), (bt, bb, bc, bi)) in enumerate(
        zip(top, bottom, strict=True)
    ):
        x = 64 + i * 384
        d.node(x, 270, 320, 180, title, body, tone, icon)
        d.node(x, 580, 320, 180, bt, bb, bc, bi)
        d.arrow([(x + 160, 450), (x + 160, 580)], tone, dashed=i == 3)
        d.label(x + 160, 523, ["inválido", "negado", "vazio", "erro"][i], tone, 18)
        if i < 3:
            d.arrow([(x + 320, 350), (x + 384, 350)], tone)
            d.label(x + 352, 246, ["válido", "permitido", "trechos"][i], tone, 17)
    d.tag(
        64,
        791,
        1472,
        "Falhas de transporte também podem ocorrer nas etapas anteriores; não equivalem a DENY.",
        "local",
        height=38,
        size=19,
    )
    decision = save(d, "decisao-acesso")
    return {"provisionamento": provisioning, "decisao": decision}


def generate():
    page = {
        "id": "16_rag_managed_identity_policy",
        "title": "Uma base. Quatro experiências de acesso.",
        "subtitle": "O JWT identifica. A Policy autoriza a chamada. A ACL limita os documentos.",
        "status": "LAB 16 · COGNITO + MANAGED KNOWLEDGE BASE",
        "takeaway": "O modelo recebe apenas os trechos recuperados para a identidade autorizada.",
        "description": "RAG com identidade humana e autorização antes da recuperação e da geração.",
    }
    d = Diagram(page)
    d.node(
        64,
        265,
        360,
        180,
        "Notebook do workshop",
        ["A: Riscos · B: Fraude", "C: tudo · D: sem acesso", "Sessões independentes"],
        "local",
        "laptop",
    )
    d.node(
        64,
        565,
        360,
        155,
        "Amazon Cognito",
        ["Quatro usuários sintéticos", "JWT assinado · validade curta"],
        "identity",
        "user",
    )
    d.node(
        555,
        265,
        430,
        180,
        "Gateway + Identity",
        [
            "Valida emissor, audiência e JWT",
            "Workload identity gerenciada",
            "Conector nativo: Retrieve",
        ],
        "gateway",
        "gateway",
    )
    d.node(
        555,
        565,
        430,
        155,
        "AgentCore Policy",
        ["Cedar em modo ENFORCE", "sub + e-mail = userContext"],
        "policy",
        "shield",
    )
    d.node(
        1115,
        265,
        420,
        180,
        "Bedrock Managed KB",
        ["Índice e embeddings gerenciados", "ACL nativa por documento", "Origem S3: R1/R2 e F1/F2"],
        "registry",
        "database",
    )
    d.node(
        1115,
        565,
        420,
        155,
        "Resposta com Bedrock",
        ["Converse + citações", "Sem histórico entre usuários"],
        "identity",
        "agent",
    )
    d.arrow([(244, 565), (244, 445)], "identity")
    d.label(244, 508, "1 · Login", "identity", 19)
    d.arrow([(424, 345), (555, 345)], "identity")
    d.label(489, 308, "2 · JWT", "identity", 19)
    d.arrow([(770, 445), (770, 565)], "policy")
    d.label(770, 508, "3 · Autorizar", "policy", 19)
    d.arrow([(985, 345), (1115, 345)], "gateway")
    d.label(1050, 304, "4 · IAM", "gateway", 19)
    d.arrow([(1325, 445), (1325, 565)], "registry")
    d.label(1325, 508, "5 · Trechos permitidos", "registry", 18)
    d.tag(
        555,
        774,
        980,
        "D é autenticado, mas sua chamada é negada antes do retrieval.",
        "policy",
        height=44,
        size=20,
    )
    return save(d, "arquitetura")


if __name__ == "__main__":
    generate()
    generate_processes()
