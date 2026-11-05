"""Fonte única da jornada AWS. Artefatos distribuídos não contêm credenciais/saídas."""

import sys
from pathlib import Path

import nbformat

from santander_demo.notebook_catalog import LESSON_TITLES, published_stem, source_stem

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.reference_notebook_lessons import build_reference  # noqa: E402


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
    return build_reference(name)


def main(only=None):
    selected = {source_stem(name) for name in only} if only else None
    for name in sorted(LESSON_TITLES, key=published_stem):
        if selected and name not in selected:
            continue
        notebook = build_notebook(name)
        nbformat.write(notebook, ROOT / "notebooks" / f"{published_stem(name)}.ipynb")


if __name__ == "__main__":
    main()
