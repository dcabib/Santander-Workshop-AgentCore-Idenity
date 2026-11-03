"""Fonte única da jornada AWS. Artefatos distribuídos não contêm credenciais/saídas."""

import hashlib
import sys
from pathlib import Path

import nbformat

from santander_demo.aws_workshop.manifest import account_requirements

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aws_notebook_lessons import LESSONS, md, setup  # noqa: E402


def build_notebook(name):
    if name == "00_preflight":
        from scripts.sdk_notebook_lessons import build_preflight

        return build_preflight()
    if name == "01_gateway_targets":
        from scripts.sdk_notebook_lessons import build_gateway

        return build_gateway()
    if name == "99_cleanup_sdk":
        from scripts.sdk_notebook_lessons import build_cleanup

        return build_cleanup()
    if name == "02_identity_entra_obo":
        from scripts.sdk_notebook_lessons import build_identity

        return build_identity()
    if name == "03_identity_agente_mcp":
        from scripts.sdk_notebook_lessons import build_runtime

        return build_runtime()
    title, lesson = LESSONS[name]
    accounts = account_requirements(name[:2])
    notebook = nbformat.v4.new_notebook()
    notebook.metadata.update({
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
            "workshop": {"execution": "AWS", "lab": name[:2], **accounts},
    })
    notebook.cells = [
            md(f"# {name[:2]} — {title}\n\n"
               "Referência: [AgentCore workshops](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops). "
               "O código e o IaC desta jornada adaptam os conceitos às contas do workshop."),
            md(
                f"## Pré-requisito: {accounts['required_count']} "
                + ("contas AWS distintas" if accounts["required_count"] > 1 else "conta AWS")
                + "\n\n"
                + (
                    "**Esta aula não executa em uma conta única.** "
                    f"O fluxo mostrado envolve {len(accounts['scenario_accounts'])} contas "
                    f"({', '.join(accounts['scenario_accounts'])}), mas o manifesto e o IaC "
                    "atuais exigem as quatro contas preparadas: plataforma, Retail, "
                    "Transaction e Lending. Sem elas, reserve a aula para demonstração "
                    "do instrutor no ambiente completo ou retire-a da seleção de execução."
                    if accounts["required_count"] > 1 else
                    "Esta aula não exige fronteiras entre contas. Seus stacks, integrações "
                    "e permissões precisam estar implantados na conta da plataforma. "
                    "Ela não funciona automaticamente em uma conta AWS vazia."
                )
                + "\n\n**Runner CodeBuild do projeto:** a seleção é declarada no deploy. "
                "A jornada `single-account` inclui 00–09 e 15–16; Registry, Terraform "
                "e RAG são exigidos somente pelas aulas que os utilizam. "
                "Ampliar a seleção exige atualizar a implantação pelo IaC. "
                "Confira a [matriz de contas e execução](../docs/contas-e-elegibilidade.md)."
            ),
            md(f"![Arquitetura AWS da aula {name[:2]}](../docs/diagramas/svg/{name}.svg)\n\n"
               "Leia as fronteiras do diagrama e confronte-as com o IaC e as chamadas abaixo."),
            *setup(name[:2]), *lesson(),
            md("### Evidências e encerramento\n\n"
               "Registre IDs de requisição e decisões, sem tokens ou senhas. "
               "Os recursos são compartilhados entre aulas: a remoção pertence "
               "ao pipeline de limpeza do projeto e deve respeitar essa dependência."),
    ]
    for index, cell in enumerate(notebook.cells):
        cell.id = hashlib.sha256(f"{name}:{index}:{cell.source}".encode()).hexdigest()[:16]
    return notebook


def main(only=None):
    for name in sorted({*LESSONS, "99_cleanup_sdk"}):
        if only and name not in only:
            continue
        notebook = build_notebook(name)
        nbformat.write(notebook, ROOT / "notebooks" / f"{name}.ipynb")


if __name__ == "__main__":
    main()
