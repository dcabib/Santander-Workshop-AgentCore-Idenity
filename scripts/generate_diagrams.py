"""Diagramas da jornada AWS; conteúdo compartilhado com os notebooks."""

import argparse
import html
import json
import shutil
import subprocess
import sys
from pathlib import Path
from textwrap import wrap

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.aws_notebook_lessons import LESSONS  # noqa: E402

OUT = ROOT / "docs/diagramas"
FLOWS = [
    ("Preflight", ["Notebook AWS", "STS: plataforma", "CloudFormation", "Gateway / Runtime"], "Uma conta: 00–09 e 15–16. Aulas 10–14: quatro contas. O runner exige os recursos da seleção implantada."),
    ("Gateway", ["Notebook AWS", "Gateway + Cedar", "Lambda / MCP Runtime", "DynamoDB: fonte"], "Dois tipos de target; JWT na entrada e autorização antes da ferramenta."),
    ("Identity", ["Cognito: pessoa", "Runtime: agente", "Identity: workload", "Gateway: ferramentas"], "Pessoa e workload são identidades distintas; inferência acontece no Runtime."),
    ("Identity", ["Pessoa C", "Apps Supervisor / Riscos", "Gateway + Policy", "Fonte: grant + app"], "A mesma pessoa recebe decisões diferentes conforme a aplicação autenticada."),
    ("Policy", ["Pessoa + app", "Ferramenta + parâmetros", "Policy: ENFORCE", "ALLOW / DENY"], "Uma negativa Cedar não é um erro de rede; a fonte possui ACL independente."),
    ("Policy", ["Intenção explícita", "Geração de rascunho", "Revisão de Cedar", "Publicação por IaC"], "Um rascunho não concede permissão; a publicação exige revisão."),
    ("Registry", ["Descritor + digest", "DRAFT", "PENDING_APPROVAL", "APPROVED"], "O Registry governa metadados e versões; o serviço de destino autoriza a execução."),
    ("Registry", ["Developer", "Publisher", "Approver", "Consumer"], "Sessões STS e políticas IAM separam as quatro responsabilidades."),
    ("Registry", ["Consumer", "Descoberta no Registry", "Descritor validado", "Runtime autorizado"], "Descobrir uma capacidade não concede permissão de invocação."),
    ("Terraform", ["Runtime + Bedrock", "Identity: token M2M", "Gateway", "Lambda: ferramenta"], "Terraform gerencia recursos e estado; M2M identifica a aplicação."),
    ("Contas", ["Plataforma", "Retail", "Transaction", "Lending"], "O STS exige quatro contas distintas, com Gateway e fonte por domínio."),
    ("Gateway", ["Runtime supervisor", "Gateway plataforma", "Gateways: 3 domínios", "MCP / fonte"], "Exige quatro contas distintas: plataforma, Retail, Transaction e Lending. Não executa em conta única."),
    ("Gateway", ["Cognito JWT", "Policy plataforma", "Policy domínio", "ACL da fonte"], "Fluxo de duas contas; manifesto e federação atuais exigem quatro contas preparadas."),
    ("Fonte", ["Pessoa autenticada", "Runtime MCP", "Grants DynamoDB", "Dados sintéticos"], "Simulador AWS. Identidade e fonte em duas contas; o manifesto atual exige quatro. Não executa em conta única."),
    ("Contas", ["Retail: dois agentes", "Plataforma: Gateway", "Transaction: Gateway", "Runtime: fonte"], "Três contas no fluxo, quatro exigidas pelo IaC e preflight atuais. Não executa em conta única."),
    ("Memory", ["JWT: issuer + sub", "Actor / sessão", "Memory: referência", "Fonte: grant atual"], "Uma referência antiga nunca restaura permissão revogada na fonte."),
    ("RAG", ["Cognito: A / B / C / D", "Runtime RAG", "Gateway + Policy", "Knowledge Base + ACL"], "O modelo recebe somente trechos autorizados; retrieval direto é negado."),
]


def page(name, title, flow):
    pillar, nodes, takeaway = flow
    return {"id": name, "pillar": pillar, "title": title, "nodes": nodes,
            "description": takeaway, "result": "Confrontar a resposta AWS com as asserções da aula.",
            "notes": ["Recursos e permissões declarados no IaC.",
                      "JWT Cognito; notas Entra explicam as diferenças de protocolo.",
                      "A figura descreve a arquitetura; aceite depende da execução AWS."]}


def render(p):
    text = html.escape
    parts = ['<svg xmlns="http://www.w3.org/2000/svg" width="1600" height="1000" viewBox="0 0 1600 1000" role="img" aria-labelledby="title desc">',
             f'<title id="title">{text(p["title"])}</title><desc id="desc">{text(p["description"])}</desc>',
             '<rect width="1600" height="1000" fill="#f4f7fb"/>',
             '<defs><marker id="arrow" markerWidth="10" markerHeight="10" refX="8" refY="3" orient="auto"><path d="M0,0 L8,3 L0,6" fill="#64748b"/></marker></defs>',
             '<g font-family="Arial,Helvetica,sans-serif" fill="#172b46">',
             '<rect x="64" y="66" width="7" height="40" rx="3" fill="#d52e3f"/>',
             f'<text x="91" y="95" font-size="24" font-weight="700">SANTANDER · AGENTCORE · AULA {p["id"][:2]}</text>',
             '<text x="64" y="151" font-size="18" fill="#52657c">Serviços e agentes implantados na AWS</text>']
    for index,line in enumerate(wrap(p['title'], 62)):
        parts.append(f'<text x="64" y="{219+index*48}" font-size="40" font-weight="700">{text(line)}</text>')
    colors=['#2469dd','#7546c7','#bd650f','#087f82']
    for index,label in enumerate(p['nodes']):
        x=64+index*379
        parts.append(f'<rect x="{x}" y="352" width="330" height="188" rx="18" fill="white" stroke="#dae3ee" stroke-width="2"/>')
        parts.append(f'<rect x="{x}" y="352" width="330" height="7" rx="3" fill="{colors[index]}"/>')
        parts.append(f'<text x="{x+24}" y="397" font-size="18" fill="{colors[index]}">ETAPA {index+1}</text>')
        for row,line in enumerate(wrap(label, 24)):
            parts.append(f'<text x="{x+24}" y="{448+row*34}" font-size="25" font-weight="700">{text(line)}</text>')
        if index<3:
            parts.append(f'<path d="M{x+335},446 H{x+367}" stroke="#64748b" stroke-width="3" marker-end="url(#arrow)"/>')
    parts.append('<rect x="64" y="600" width="1472" height="180" rx="18" fill="#e8eff8"/>')
    parts.append('<text x="91" y="645" font-size="20" font-weight="700">O QUE ESTA FRONTEIRA ENSINA</text>')
    for row,line in enumerate(wrap(p['description'], 99)):
        parts.append(f'<text x="91" y="{693+row*35}" font-size="25">{text(line)}</text>')
    parts.append('<text x="64" y="850" font-size="22">Código → IaC → chamadas AWS → asserções e evidências</text>')
    parts.append('<text x="64" y="916" font-size="18" fill="#52657c">Dados sintéticos · JWT e Cedar · Sem tokens ou senhas nas evidências</text>')
    return '\n'.join(parts+['</g></svg>'])


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--svg-only', action='store_true')
    args=parser.parse_args()
    pages=[]
    for folder in ['svg','png']:
        (OUT/folder).mkdir(parents=True,exist_ok=True)
    for (name,(title,_)),flow in zip(sorted(LESSONS.items()),FLOWS,strict=True):
        p=page(name,title,flow)
        pages.append(p)
        svg=OUT/'svg'/f'{name}.svg'
        svg.write_text(render(p))
        if not args.svg_only:
            subprocess.run(['rsvg-convert','-w','1600','-h','1000','-o',str(OUT/'png'/f'{name}.png'),str(svg)],check=True)
    template=(ROOT/'scripts/templates/diagrams.html').read_text()
    (OUT/'index.html').write_text(template.replace('__DIAGRAM_MANIFEST__',json.dumps(pages,ensure_ascii=False)))
    (OUT/'manifest.json').write_text(json.dumps(pages,ensure_ascii=False,indent=2)+'\n')
    (OUT/'README.md').write_text('# Diagramas da jornada AWS\n\n'
        +'[Abrir galeria](index.html). Diagramas descrevem a arquitetura; evidências vêm da execução AWS.\n\n'
        +'\n'.join(f'- [{p["id"][:2]} — {p["title"]}](svg/{p["id"]}.svg)' for p in pages)+'\n')
    for folder,number in {'registry':7,'terraform':9,'banking':11,'federation':12,'journey':14,'ingestao':15,'rag':16}.items():
        for suffix in ['svg','png'] if not args.svg_only else ['svg']:
            shutil.copyfile(OUT/suffix/f'{pages[number]["id"]}.{suffix}',ROOT/'docs'/folder/f'arquitetura.{suffix}')
    for folder,name,number in [('registry','fronteiras',8),('rag','provisionamento',5),('rag','decisao-acesso',16)]:
        for suffix in ['svg','png'] if not args.svg_only else ['svg']:
            shutil.copyfile(OUT/suffix/f'{pages[number]["id"]}.{suffix}',ROOT/'docs'/folder/f'{name}.{suffix}')
    print(f'{len(pages)} diagramas da jornada AWS gerados.')


if __name__=='__main__':
    main()
