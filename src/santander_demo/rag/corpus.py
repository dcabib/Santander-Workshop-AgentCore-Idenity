"""Conteúdo sintético e ACLs nativas do conector S3 da Managed Knowledge Base."""

import hashlib
import json

from santander_demo.rag.contract import DOMAINS, validate_users

DOCUMENTS = (
    {
        "id": "R1",
        "domain": "riscos",
        "title": "Revisão de limite",
        "text": "Documento sintético R1. Política de riscos: código RISCO-ORQUIDEA-731. "
        "Uma revisão de limite exige conferir renda declarada e registrar a justificativa.",
    },
    {
        "id": "R2",
        "domain": "riscos",
        "title": "Dupla revisão",
        "text": "Documento sintético R2. Política de riscos: código RISCO-CEDRO-284. "
        "Exceções de crédito devem passar por dois revisores antes de sua aprovação.",
    },
    {
        "id": "F1",
        "domain": "fraude",
        "title": "Dispositivo desconhecido",
        "text": "Documento sintético F1. Política de fraude: código FRAUDE-TUCANO-592. "
        "Um dispositivo desconhecido exige confirmação adicional por canal cadastrado.",
    },
    {
        "id": "F2",
        "domain": "fraude",
        "title": "Preservação de evidências",
        "text": "Documento sintético F2. Política de fraude: código FRAUDE-IPÊ-846. "
        "Um alerta exige preservar identificador da transação e sequência de eventos.",
    },
)


def acl_entries(domain, users):
    return [
        {
            "Name": user["email"],
            "Type": "USER",
            "Access": "ALLOW" if domain in DOMAINS[label] else "DENY",
        }
        for label, user in users.items()
    ]


def objects(bucket, users):
    validate_users(users)
    result = {}
    global_acl = []
    for domain in ("riscos", "fraude"):
        global_acl.append(
            {
                "keyPrefix": f"s3://{bucket}/documents/{domain}/",
                "aclEntries": acl_entries(domain, users),
            }
        )
    result["acl/global-acl.json"] = json.dumps(global_acl, ensure_ascii=False).encode()
    for doc in DOCUMENTS:
        key = f"documents/{doc['domain']}/{doc['id']}.txt"
        result[key] = doc["text"].encode()
        result[key + ".metadata.json"] = json.dumps(
            {
                "metadataAttributes": {
                    "document_id": doc["id"],
                    "domain": doc["domain"],
                },
                "accessControlList": acl_entries(doc["domain"], users),
            },
            ensure_ascii=False,
        ).encode()
    return result


def corpus_digest(users):
    """Força atualização do custom resource se conteúdo ou permissões mudarem."""
    content = objects("digest-only", users)
    return hashlib.sha256(
        b"".join(key.encode() + content[key] for key in sorted(content))
    ).hexdigest()


def allowed_documents(label):
    return {doc["id"] for doc in DOCUMENTS if doc["domain"] in DOMAINS[label]}
