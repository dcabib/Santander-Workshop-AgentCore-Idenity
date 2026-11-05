"""Catálogo das aulas SDK e referências; nomes anteriores identificam evidências históricas."""

from pathlib import Path

RENAMED_NOTEBOOKS = {
    "10_santander_multi_conta": "90_multiconta_santander",
    "11_blog_multi_account_gateway_mcp": "91_multiconta_agente_central_gateway_mcp",
    "12_gateways_por_conta_identity_policy": "92_multiconta_gateways_identity_policy",
}
SOURCE_NAMES = {published: source for source, published in RENAMED_NOTEBOOKS.items()}
DISPLAY_NUMBERS = {source[:2]: published[:2] for source, published in RENAMED_NOTEBOOKS.items()}
LAB_ALIASES = {number: lab for lab, number in DISPLAY_NUMBERS.items()}


def source_stem(name):
    stem = Path(name).stem
    return SOURCE_NAMES.get(stem, stem)


def published_stem(name):
    stem = source_stem(name)
    return RENAMED_NOTEBOOKS.get(stem, stem)


def lab_id(name):
    """Aceita nome antigo/novo ou número visível preservando a identidade das evidências."""
    number = source_stem(name)[:2]
    return LAB_ALIASES.get(number, number)


def display_number(lab):
    return DISPLAY_NUMBERS.get(lab, lab)


REFERENCE_LABS = frozenset({"10", "11", "12", "13", "14"})

LESSON_TITLES = {'00_preflight': 'Preparar conta, região e sessão AWS', '01_gateway_targets': 'Criar Cognito, Lambda e AgentCore Gateway', '02_identity_entra_obo': 'Pessoa Cognito, aplicação e comparação com Entra ID', '03_identity_agente_mcp': 'Runtime MCP e identidade IAM do workload', '04_policy_cedar': 'Criar Policy Engine e testar Cedar', '05_policy_autoria': 'Gerar e revisar um rascunho de política', '06_registry_governanca': 'Criar Registry e governança', '07_registry_personas': 'Personas e permissões IAM', '08_registry_descoberta_execucao': 'Publicar, aprovar, descobrir e invocar', '09_integracao_runtime_gateway_identity': 'Integrar Runtime, Gateway e Identity', '10_santander_multi_conta': 'Referência — quatro contas e fronteiras', '11_blog_multi_account_gateway_mcp': 'Referência — agente central e domínios', '12_gateways_por_conta_identity_policy': 'Referência — Gateways, Identity e Policy por conta', '13_databricks_e_evidencias': 'Referência — fonte Databricks simulada na AWS', '14_cenario_santander_integrado': 'Referência — origem, plataforma e fonte', '15_ingestao_acl_memoria': 'Memory por actor e autorização na fonte', '16_rag_managed_identity_policy': 'RAG gerenciado, ACL nativa e geração', '99_cleanup_sdk': 'Limpeza dos recursos SDK desta execução'}
