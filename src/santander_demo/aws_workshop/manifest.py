"""Dependências explícitas; uma aula só pode executar com seus serviços implantados."""

from .config import DOMAINS, check_accounts, validate

LABS = {
    "00": ("core",),
    "01": ("core",),
    "02": ("core", "agent"),
    "03": ("core",),
    "04": ("core",),
    "05": ("core", "policy-draft"),
    "06": ("registry",),
    "07": ("registry",),
    "08": ("registry", "agent"),
    "09": ("terraform",),
    "10": ("multi-account",),
    "11": ("multi-account", "agent", "federation"),
    "12": ("multi-account", "federation"),
    "13": ("multi-account",),
    "14": ("multi-account", "origin-agents", "registry", "federation"),
    "15": ("core", "rag"),
    "16": ("rag", "rag-runtime"),
}

# Contas no fluxo demonstrado versus dependências da implantação atual.
# O IaC de federation-bindings agrega os três domínios, sem seleção parcial.
SCENARIO_ACCOUNTS = {
    "10": DOMAINS,
    "11": DOMAINS,
    "12": ("platform", "transaction-banking"),
    "13": ("platform", "transaction-banking"),
    "14": ("retail-banking", "platform", "transaction-banking"),
}


def required_domains(lab):
    if lab not in LABS:
        raise ValueError("UNKNOWN_LAB:" + lab)
    return DOMAINS if "multi-account" in LABS[lab] else ("platform",)


def account_requirements(lab):
    required = required_domains(lab)
    return {
        "scenario_accounts": list(SCENARIO_ACCOUNTS.get(lab, required)),
        "required_accounts": list(required),
        "required_count": len(required),
    }


def account_plan(config, labs=None, *, runner=False):
    """Só inspeciona IDs declarados: não consulta AWS nem atesta prontidão."""
    validate(config)
    selected = list(dict.fromkeys(labs or LABS))

    def blockers(domains):
        ids = [config["accounts"][domain].get("id") for domain in domains]
        missing = [domain for domain, value in zip(domains, ids, strict=True) if not value]
        problems = []
        if missing:
            problems.append("IDs ausentes: " + ", ".join(missing))
        present = [value for value in ids if value]
        if len(present) != len(set(present)):
            problems.append("IDs repetidos: perfis diferentes não representam contas distintas")
        return problems

    rows = []
    for lab in selected:
        requirements = account_requirements(lab)
        problems = blockers(requirements["required_accounts"])
        rows.append({
            "lab": lab, **requirements, "dependencies": list(LABS[lab]),
            "status": "BLOCKED" if problems else "ACCOUNTS_CONFIGURED",
            "blockers": problems,
        })
    runner_blockers = blockers(DOMAINS) if runner else []
    return {
        "validation": "ACCOUNT_CONFIGURATION_ONLY",
        "status": "BLOCKED" if runner_blockers or any(row["blockers"] for row in rows)
        else "ACCOUNTS_CONFIGURED",
        "labs": rows,
        "runner_required_accounts": list(DOMAINS) if runner else [],
        "runner_blockers": runner_blockers,
        "note": (
            "IDs configurados não comprovam credenciais, roles, stacks ou serviços disponíveis. "
            "O runner completo exige quatro contas e Registry, Terraform e RAG, mesmo com --labs."
        ),
    }


def assert_account_plan(plan):
    if plan["status"] != "BLOCKED":
        return
    details = [
        f"aula {row['lab']} exige {row['required_count']} contas distintas "
        f"({', '.join(row['required_accounts'])}): {'; '.join(row['blockers'])}"
        for row in plan["labs"] if row["blockers"]
    ]
    if plan["runner_blockers"]:
        details.append(
            "runner completo exige 4 contas distintas, mesmo com --labs: "
            + "; ".join(plan["runner_blockers"])
        )
    raise ValueError(
        "WORKSHOP_PREREQUISITES_BLOCKED: " + " | ".join(details)
        + ". Consulte docs/contas-e-elegibilidade.md; nenhuma aula foi iniciada."
    )


def check_selection(config, labs=None, *, runner=False):
    """Falha antes de executar qualquer aula se a seleção não estiver preparada."""
    plan = account_plan(config, labs, runner=runner)
    assert_account_plan(plan)
    if runner:
        check_accounts(config, domains=DOMAINS)
    return {row["lab"]: require(config, row["lab"]) for row in plan["labs"]}


def require(config, lab):
    from .client import stack_name
    from .config import session, stack_outputs

    assert_account_plan(account_plan(config, [lab]))
    accounts = check_accounts(config, domains=required_domains(lab))
    result = {"accounts": accounts}
    for dependency in LABS[lab]:
        if dependency == "multi-account":
            result[dependency] = accounts
            for domain in DOMAINS:
                for phase in ("gateway", "backend", "bindings"):
                    stack_outputs(session(config, domain), stack_name(config, domain, phase))
        elif dependency in {"federation", "origin-agents", "rag-runtime"}:
            domain = "retail-banking" if dependency == "origin-agents" else "platform"
            phases = {
                "federation": ("federation-bindings",),
                "origin-agents": ("agent-riscos", "agent-fraude"),
                "rag-runtime": ("rag-agent",),
            }[dependency]
            result[dependency] = {
                phase: stack_outputs(session(config, domain), stack_name(config, domain, phase))
                for phase in phases
            }
        elif dependency in {"core", "agent", "policy-draft"}:
            phases = ("identity", "gateway", "backend", "bindings") if dependency == "core" else [dependency]
            result[dependency] = {
                phase: stack_outputs(session(config), stack_name(config, "platform", phase))
                for phase in phases
            }
        else:
            integration = config.get("integrations", {}).get(dependency)
            if not integration:
                raise ValueError(f"LAB_DEPENDENCY_REQUIRED:{lab}:{dependency}")
            result[dependency] = integration
    return result
