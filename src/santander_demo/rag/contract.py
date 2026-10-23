"""Contrato compartilhado entre Cedar, clientes, corpus e CloudFormation."""

import json
import re
from uuid import UUID

import cedarpy

TOOL = "rag___Retrieve"
SCOPE = "access_as_user"
EMAIL_PATTERN = r"[A-Za-z0-9][A-Za-z0-9._%+-]*@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}"
DOMAINS = {"a": ("riscos",), "b": ("fraude",), "c": ("riscos", "fraude"), "d": ()}
QUESTION = "Quais são os códigos e os procedimentos das políticas de riscos e fraude?"


def validate_users(users):
    if set(users) != set(DOMAINS):
        raise ValueError("FOUR_USERS_REQUIRED")
    oids, emails = set(), set()
    for value in users.values():
        oid, email = value["oid"], value["email"]
        if str(UUID(oid)) != oid:
            raise ValueError("CANONICAL_OID_REQUIRED")
        if not re.fullmatch(EMAIL_PATTERN, email):
            raise ValueError("EXACT_SOURCE_EMAIL_REQUIRED")
        oids.add(oid)
        emails.add(email.casefold())
    if len(oids) != 4 or len(emails) != 4:
        raise ValueError("FOUR_DISTINCT_IDENTITIES_REQUIRED")
    return users


def principal_label(identity, users):
    """O e-mail assinado deve corresponder ao OID cadastrado; não é uma heurística."""
    for label, user in users.items():
        if identity.claims.get("oid") == user["oid"]:
            if identity.claims.get("email") != user["email"]:
                raise ValueError("SOURCE_IDENTITY_MISMATCH")
            return label
    raise ValueError("USER_NOT_REGISTERED")


def cedar(gateway_arn, tenant, broker, users):
    """O parâmetro userContext só é aceito quando corresponde ao JWT verificado."""
    q = json.dumps
    policies = {}
    for label in ("a", "b", "c"):
        user = users[label]
        conditions = {
            "tid": tenant,
            "azp": broker,
            "ver": "2.0",
            "scp": SCOPE,
            "oid": user["oid"],
            "email": user["email"],
        }
        checks = [
            f'principal.hasTag("{key}") && principal.getTag("{key}") == {q(value)}'
            for key, value in conditions.items()
        ]
        checks.append("context.input has userContext")
        checks.append(f"context.input.userContext.userId == {q(user['email'])}")
        condition = " &&\n  ".join(checks)
        policies["AllowUser" + label.upper()] = f"""permit(
  principal is AgentCore::OAuthUser,
  action == AgentCore::Action::{q(TOOL)},
  resource == AgentCore::Gateway::{q(gateway_arn)}
)
when {{
  {condition}
}};"""
    # D não recebe permit: a decisão padrão do Cedar é DENY.
    return policies


def evaluate(claims, arguments, *, gateway_arn, tenant, broker, users, action=TOOL):
    principal = {"type": "AgentCore::OAuthUser", "id": claims.get("sub", "missing")}
    return cedarpy.is_authorized(
        {
            "principal": principal,
            "action": {"type": "AgentCore::Action", "id": action},
            "resource": {"type": "AgentCore::Gateway", "id": gateway_arn},
            "context": {"input": arguments},
        },
        "\n".join(cedar(gateway_arn, tenant, broker, users).values()),
        [{"uid": principal, "attrs": {}, "parents": [], "tags": claims}],
    ).allowed


def connector_configuration(knowledge_base_id):
    """Uma única tool, KB fixa e userContext exposto para validação pela Policy."""
    return {
        "source": {"connectorId": "bedrock-knowledge-bases"},
        "enabled": ["Retrieve"],
        "configurations": [
            {
                "name": "Retrieve",
                "parameterValues": {
                    "knowledgeBaseId": knowledge_base_id,
                    "retrievalConfiguration": {
                        "managedSearchConfiguration": {
                            "numberOfResults": 10,
                            "rerankingModelType": "MANAGED",
                        }
                    },
                },
                "parameterOverrides": [
                    {"path": "$.retrievalQuery.text", "visible": True},
                    {"path": "$.userContext", "visible": True},
                ],
            }
        ],
    }
