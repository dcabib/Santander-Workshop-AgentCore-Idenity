"""Cadernos de arquitetura ainda sem construção SDK: não executam código AWS."""

import hashlib
from dataclasses import replace

import nbformat

from santander_demo.notebook_catalog import LESSON_TITLES, display_number
from scripts.aws_notebook_lessons import md
from scripts.notebook_curriculum import GUIDES, introduction

STEPS = {
    "10": (
        "Conferir com STS quatro IDs diferentes: plataforma, Retail, Transaction e Lending.",
        "Construir recursos e roles em cada conta, mostrando as chamadas SDK e os IDs retornados.",
        "Testar confiança e permissão separadamente; um perfil diferente não prova outra conta.",
        "Limpar por dependência em todas as contas, com registro próprio por conta e região.",
    ),
    "11": (
        "Construir o Runtime do agente central e os servidores MCP de cada domínio.",
        "Configurar a entrada por domínio e o roteamento do Gateway central com identidades explícitas.",
        "Invocar Retail, Transaction e Lending e correlacionar os Request IDs de cada destino.",
        "Exercitar negativas de domínio e remover os recursos criados em cada conta.",
    ),
    "12": (
        "Construir os Gateways, authorizers e engines Policy da plataforma e dos domínios.",
        "Definir e inspecionar a confiança IAM do salto entre contas.",
        "Comparar a mesma operação pela plataforma e diretamente no domínio.",
        "Confirmar ALLOW e DENY em cada entrada, mantendo o controle da fonte independente.",
    ),
    "13": (
        "Construir um Runtime MCP e uma fonte sintética DynamoDB na conta de dados.",
        "Vincular a pessoa verificada a uma concessão de dados; o modelo não escolhe essa identidade.",
        "Comparar autorização no Gateway com autorização independente na fonte.",
        "Registrar SOURCE_DENY e a identidade verificada sem alegar execução em Databricks real.",
    ),
    "14": (
        "Construir os agentes na origem, o Gateway na plataforma e o backend na conta de dados.",
        "Publicar e aprovar descritores; a descoberta não concede autorização de invocação.",
        "Testar audiências das aplicações e correlacionar origem → plataforma → fonte.",
        "Validar cada fronteira com controles positivos e negativos e limpar por conta.",
    ),
}


def build_reference(name):
    lab = name[:2]
    number = display_number(lab)
    guide = replace(
        GUIDES[lab],
        prerequisites="Leitura de arquitetura. A implementação SDK entre contas ainda precisa ser construída e testada.",
        creates="Nenhum recurso; este caderno contém somente Markdown e diagramas.",
        reuses="Referências conceituais. Não depende de configuração ou recursos da turma atual.",
    )
    cells = [md(
        f"# {number} — {LESSON_TITLES[name]}\n\n"
        "**REFERÊNCIA DE ARQUITETURA — NÃO EXECUTÁVEL.**\n\n"
        "O fluxo antigo de infraestrutura foi retirado do projeto. Ter quatro contas não torna "
        "este caderno executável: ainda falta implementar criação, testes e limpeza nas células SDK. "
        "As quatro contas nos desenhos descrevem a topologia histórica completa. "
        "No Workshop Studio com uma conta, execute **00–09 → 15–16 → 99**.\n\n"
        "[Escopo e contas](../docs/contas-e-elegibilidade.md) · "
        "[Plano de conversão](../docs/cenarios-multiconta.md)"
    ), *introduction(name, guide)]
    cells.append(md("## Passos que a futura implementação precisa tornar executáveis\n\n" +
                    "\n".join(f"{i}. {step}" for i, step in enumerate(STEPS[lab], 1))))
    for checkpoint in guide.checkpoints:
        rows = "\n".join(f"| {case} | {expected} | {meaning} |" for case, expected, meaning in checkpoint.expected)
        cells.append(md(f"## Critérios de validação futuros — {checkpoint.title}\n\n"
                        "Esta tabela é um contrato de aceitação; nenhuma chamada é executada aqui.\n\n"
                        "| Caso | Resultado esperado | O que precisará ser comprovado |\n|---|---|---|\n" + rows))
    cells.append(md(
        f"## Análise da arquitetura\n\n{guide.conclusion}\n\n"
        "**Evidência atual:** não há aceite SDK deste cenário. Os notebooks de conta única "
        "não comprovam isolamento entre contas, federação ou uma instalação real do Databricks.\n\n"
        f"**Para discutir:** {guide.discussion}\n\n"
        "**Encerramento:** a leitura deste caderno não cria recursos. A limpeza 99 atende somente "
        "a jornada SDK de conta única; ela não remove implantações de versões anteriores."
    ))
    notebook = nbformat.v4.new_notebook(cells=cells, metadata={
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.12"},
        "workshop": {"lab": lab, "notebook_number": number, "execution": "REFERENCE_ONLY",
                     "provisioning": "NOT_IMPLEMENTED", "required_count": 4,
                     "migration_status": "SDK_CONVERSION_PENDING", "teaching_guide_version": 1},
    })
    for index, cell in enumerate(notebook.cells):
        cell.id = hashlib.sha256(f"{name}:{index}:{cell.source}".encode()).hexdigest()[:16]
    return notebook
