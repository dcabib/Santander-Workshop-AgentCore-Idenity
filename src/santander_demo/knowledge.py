"""Contrato local de ingestão, ACL, ciclo de vida documental e memória isolada."""

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class Document:
    id: str
    source: str
    text: str
    allowed_groups: frozenset[str]
    version: int


class KnowledgeLab:
    """IDs/grupos vêm do conector/IdP confiável, não de filtros escolhidos pelo LLM."""

    def __init__(self):
        self.documents = {}
        self.memberships = {
            "user-riscos": frozenset({"bdag-riscos"}),
            "user-fraude": frozenset({"bdag-fraude"}),
            "user-ambos": frozenset({"bdag-riscos", "bdag-fraude"}),
        }
        self.memory = {}
        self.audit = []

    def discover(self):
        return [
            {"source": name, "connector": "CONTRACT_ONLY", "live_ingestion": False}
            for name in ("SharePoint", "Databricks Silver/Gold", "SQL on-prem", "AWS API")
        ]

    def register(self, doc):
        if doc.id in self.documents or doc.version != 1 or not doc.allowed_groups:
            raise ValueError("INVALID_REGISTRATION")
        self.documents[doc.id] = doc
        self._audit("register", doc)

    def update(self, doc):
        current = self.documents.get(doc.id)
        if not current or doc.version != current.version + 1 or not doc.allowed_groups:
            raise ValueError("VERSION_OR_ACL_MISMATCH")
        self.documents[doc.id] = doc
        self._audit("update", doc)

    def delete(self, doc_id):
        doc = self.documents.pop(doc_id)
        self._audit("delete", doc)
        # Memória guarda referências, nunca uma cópia persistente do conteúdo removido.

    def _audit(self, operation, doc):
        self.audit.append(
            {
                "operation": operation,
                "document_id": doc.id,
                "version": doc.version,
                "source": doc.source,
                "content_sha256": hashlib.sha256(doc.text.encode()).hexdigest(),
                "mode": "LOCAL_INGESTION_CONTRACT",
            }
        )

    def _visible(self, user, doc):
        return bool(self.memberships.get(user, frozenset()) & doc.allowed_groups)

    def retrieve(self, user, query):
        return [
            {"document_id": doc.id, "text": doc.text, "source": doc.source, "version": doc.version}
            for doc in self.documents.values()
            if self._visible(user, doc) and query.casefold() in doc.text.casefold()
        ]

    def remember(self, user, session, document_ids):
        if (
            not user
            or not session
            or any(
                doc_id not in self.documents or not self._visible(user, self.documents[doc_id])
                for doc_id in document_ids
            )
        ):
            raise ValueError("MEMORY_ACCESS_DENIED")
        self.memory[(user, session)] = tuple(document_ids)

    def recall(self, user, session):
        # Revalida ACL após revogação: a memória não amplia privilégios de retrieval.
        return [
            doc.text
            for doc_id in self.memory.get((user, session), ())
            if (doc := self.documents.get(doc_id)) and self._visible(user, doc)
        ]


def local_knowledge_demo():
    lab = KnowledgeLab()
    lab.register(
        Document(
            "R1",
            "SharePoint",
            "# Política de risco\nRevisão de limite.",
            frozenset({"bdag-riscos"}),
            1,
        )
    )
    lab.register(
        Document(
            "F1",
            "Databricks Silver/Gold",
            "# Política de fraude\nRevisão de dispositivo.",
            frozenset({"bdag-fraude"}),
            1,
        )
    )
    before = {
        user: [r["document_id"] for r in lab.retrieve(user, "política")] for user in lab.memberships
    }
    lab.remember("user-riscos", "same-session", ["R1"])
    assert lab.recall("user-fraude", "same-session") == []
    lab.update(Document("R1", "SharePoint", "# Política revisada", frozenset({"bdag-fraude"}), 2))
    assert lab.recall("user-riscos", "same-session") == []
    lab.delete("F1")
    assert all(r["document_id"] != "F1" for r in lab.retrieve("user-ambos", "política"))
    return {
        "mode": "LOCAL_INGESTION_CONTRACT",
        "connectors_bda_kb_memory_aws": "NOT_RUN",
        "visibility_before": before,
        "memory_cross_user": "DENIED",
        "revoked_acl_in_memory": "DENIED",
        "deleted_document": "NOT_RETRIEVABLE",
        "lifecycle": lab.audit,
    }
