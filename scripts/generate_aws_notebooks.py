"""Fonte única da jornada AWS. Artefatos distribuídos não contêm credenciais/saídas."""

import hashlib
import sys
from pathlib import Path

import nbformat

from santander_demo.aws_workshop.manifest import account_requirements
from santander_demo.notebook_catalog import display_number, published_stem, source_stem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.aws_notebook_lessons import LESSONS, md, setup  # noqa: E402
from scripts.notebook_curriculum import enrich_notebook  # noqa: E402


def build_notebook(name):
    name = source_stem(name)
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
    if name == "04_policy_cedar":
        from scripts.sdk_notebook_lessons import build_policy

        return build_policy()
    if name == "05_policy_autoria":
        from scripts.sdk_notebook_lessons import build_policy_authoring

        return build_policy_authoring()
    if name == "06_registry_governanca":
        from scripts.sdk_notebook_lessons import build_registry

        return build_registry()
    if name == "07_registry_personas":
        from scripts.sdk_notebook_lessons import build_registry_personas

        return build_registry_personas()
    if name == "08_registry_descoberta_execucao":
        from scripts.sdk_notebook_lessons import build_registry_execution

        return build_registry_execution()
    if name == "09_integracao_runtime_gateway_identity":
        from scripts.sdk_notebook_lessons import build_integration

        return build_integration()
    if name == "15_ingestao_acl_memoria":
        from scripts.sdk_notebook_lessons import build_memory

        return build_memory()
    if name == "16_rag_managed_identity_policy":
        from scripts.sdk_notebook_lessons import build_rag

        return build_rag()
    title, lesson = LESSONS[name]
    accounts = account_requirements(name[:2])
    notebook = nbformat.v4.new_notebook()
    notebook.metadata.update({
            "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
            "language_info": {"name": "python", "version": "3.12"},
            "workshop": {"execution": "AWS", "lab": name[:2], **accounts},
    })
    notebook.cells = [
            md(f"# {display_number(name[:2])} — {title}\n\n"
               "Referência: [AgentCore workshops](https://github.com/awslabs/agentcore-samples/tree/main/06-workshops). "
               "Esta aula conserva o código da arquitetura anterior enquanto sua conversão está pendente."),
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
                + "\n\nA jornada SDK atual de conta única inclui 00–09 e 15–16. "
                "Os recursos dessas aulas não preparam esta integração legada. "
                "Confira a [matriz de contas e execução](../docs/contas-e-elegibilidade.md)."
            ),
            *setup(name[:2]), *lesson(),
            md("### Evidências e encerramento\n\n"
               "Registre IDs de requisição e decisões, sem tokens ou senhas. "
               "Os recursos são compartilhados entre aulas: a remoção pertence "
               "ao pipeline de limpeza do projeto e deve respeitar essa dependência."),
    ]
    if published_stem(name) != name:
        notebook.metadata.workshop["notebook_number"] = display_number(name[:2])
        notebook.cells[0].source += (
            "\n\n**Bloco final multiconta — fora da jornada de conta única do Workshop Studio.** "
            f"Anteriormente aula {name[:2]}; o ID `{name[:2]}` nas chamadas e evidências legadas "
            "permanece estável. A mudança de ordem não altera os recursos nem dispensa as quatro contas."
        )
    enrich_notebook(notebook, name)
    for index, cell in enumerate(notebook.cells):
        cell.id = hashlib.sha256(f"{name}:{index}:{cell.source}".encode()).hexdigest()[:16]
    return notebook


def main(only=None):
    selected = {source_stem(name) for name in only} if only else None
    for name in sorted({*LESSONS, "99_cleanup_sdk"}, key=published_stem):
        if selected and name not in selected:
            continue
        notebook = build_notebook(name)
        nbformat.write(notebook, ROOT / "notebooks" / f"{published_stem(name)}.ipynb")


if __name__ == "__main__":
    main()
