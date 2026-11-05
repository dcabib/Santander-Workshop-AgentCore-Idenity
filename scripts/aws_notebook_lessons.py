"""Primitivas de células dos notebooks; não cria recursos nem carrega infraestrutura."""

from textwrap import dedent

import nbformat


def md(text):
    return nbformat.v4.new_markdown_cell(dedent(text).strip())


def code(text):
    return nbformat.v4.new_code_cell(dedent(text).strip())


def step(title, explanation, implementation):
    return [md("### " + title + "\n\n" + explanation), code(implementation)]
