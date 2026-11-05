"""Ordem dos arquivos; IDs do manifesto legado permanecem estáveis."""

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
    """Aceita nome antigo/novo ou número visível sem mudar dependências AWS."""
    number = source_stem(name)[:2]
    return LAB_ALIASES.get(number, number)


def display_number(lab):
    return DISPLAY_NUMBERS.get(lab, lab)
