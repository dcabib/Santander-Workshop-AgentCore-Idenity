"""Configuração de implantação e verificação das contas, sem fallback de execução."""

import json
import re
from pathlib import Path

import boto3

DOMAINS = ("platform", "retail-banking", "transaction-banking", "lending-wealth")
SECRET_FIELDS = {
    "access_token", "id_token", "refresh_token", "client_secret", "password",
    "aws_access_key_id", "aws_secret_access_key", "aws_session_token",
}


def _identifiers_only(value):
    if isinstance(value, dict):
        if SECRET_FIELDS.intersection(value):
            raise ValueError("CONFIG_IDENTIFIERS_ONLY: use referências ao Secrets Manager")
        for child in value.values():
            _identifiers_only(child)
    elif isinstance(value, list):
        for child in value:
            _identifiers_only(child)


def validate(config):
    _identifiers_only(config)
    if config.get("schema_version") != 1:
        raise ValueError("WORKSHOP_CONFIG_VERSION: esperado schema_version=1")
    if not re.fullmatch(r"[a-z][a-z0-9-]{2,24}", config.get("project", "")):
        raise ValueError("WORKSHOP_PROJECT_INVALID")
    if config.get("region") != "us-east-1":
        raise ValueError("WORKSHOP_REGION: esta jornada foi preparada para us-east-1")
    if config.get("auth_provider") != "cognito":
        raise ValueError("WORKSHOP_IDP: este pipeline implementa Cognito; Entra exige adaptar o IaC")
    if config.get("source_kind") != "aws_simulated_databricks":
        raise ValueError("WORKSHOP_SOURCE: este pipeline implementa o simulador hospedado na AWS")
    accounts = config.get("accounts", {})
    if set(accounts) != set(DOMAINS):
        raise ValueError("WORKSHOP_ACCOUNTS: declare platform e as três áreas bancárias")
    for name, account in accounts.items():
        account_id = account.get("id")
        if account_id is not None and not re.fullmatch(r"\d{12}", account_id):
            raise ValueError("WORKSHOP_ACCOUNT_ID_INVALID:" + name)
        if account.get("profile") is not None and not isinstance(account["profile"], str):
            raise ValueError("WORKSHOP_PROFILE_INVALID:" + name)
        if account.get("role_arn") and not re.fullmatch(
            r"arn:aws:iam::\d{12}:role/[\w+=,.@/-]+", account["role_arn"]
        ):
            raise ValueError("WORKSHOP_ROLE_INVALID:" + name)
    if not accounts["platform"].get("id"):
        raise ValueError("WORKSHOP_PLATFORM_ACCOUNT_REQUIRED")
    return config


def load(path):
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(
            f"WORKSHOP_CONFIG_REQUIRED: configure {path} com as contas AWS do workshop"
        )
    return validate(json.loads(path.read_text()))


def session(config, domain="platform"):
    """Perfil no host do operador; role de execução/STS no ambiente AWS."""
    account = config["accounts"][domain]
    base = boto3.Session(profile_name=account.get("profile"), region_name=config["region"])
    if not account.get("role_arn"):
        return base
    credentials = base.client("sts").assume_role(
        RoleArn=account["role_arn"],
        RoleSessionName="santander-workshop-" + domain,
    )["Credentials"]
    return boto3.Session(
        region_name=config["region"],
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
    )


def check_accounts(config, *, domains=("platform",), session_factory=session):
    """O ID observado deve coincidir com o configurado, inclusive entre contas."""
    validate(config)
    if len(set(domains)) != len(domains) or not set(domains) <= set(DOMAINS):
        raise ValueError("WORKSHOP_DOMAINS_INVALID")
    configured = [config["accounts"][name].get("id") for name in domains]
    if any(value is None for value in configured):
        raise ValueError("WORKSHOP_ACCOUNT_ID_REQUIRED: complete os IDs antes do exercício")
    if len(configured) > 1 and len(set(configured)) != len(configured):
        raise ValueError("DISTINCT_AWS_ACCOUNTS_REQUIRED")
    checked = {}
    for domain in domains:
        identity = session_factory(config, domain).client("sts").get_caller_identity()
        if identity["Account"] != config["accounts"][domain]["id"]:
            raise ValueError("WRONG_AWS_ACCOUNT:" + domain)
        checked[domain] = {
            "account_id": identity["Account"],
            "principal_arn": identity["Arn"],
            "region": config["region"],
        }
    return checked


def stack_outputs(aws_session, name):
    """Estado estável e outputs do stack exato; não seleciona o primeiro recurso listado."""
    stack = aws_session.client("cloudformation").describe_stacks(StackName=name)["Stacks"][0]
    if stack["StackStatus"] not in {"CREATE_COMPLETE", "UPDATE_COMPLETE", "IMPORT_COMPLETE"}:
        raise RuntimeError(f"STACK_NOT_READY:{name}:{stack['StackStatus']}")
    return {item["OutputKey"]: item["OutputValue"] for item in stack.get("Outputs", [])}
