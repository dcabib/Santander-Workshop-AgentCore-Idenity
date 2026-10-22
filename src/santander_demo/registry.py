"""Modelo local do workflow e validação dos descriptors antes de enviar um bearer."""

from dataclasses import asdict, dataclass
from urllib.parse import urlsplit

from santander_demo.contracts import LOCAL_ENDPOINT, TOOLS, DemoError


@dataclass
class Record:
    name: str
    tool: str
    description: str
    endpoint: str = LOCAL_ENDPOINT
    version: str = "1.0"
    state: str = "DRAFT"
    owner: str = "santander-demo"


class LocalRegistry:
    """Simulação explícita: não substitui IAM nem o índice semântico AWS."""

    def __init__(self):
        self.records: dict[str, Record] = {}

    def publish(self, record: Record, role: str):
        if role != "publisher" or record.state != "DRAFT" or record.name in self.records:
            raise DemoError("REGISTRY_PUBLISH_DENIED")
        self.records[record.name] = record

    def submit(self, name: str, role: str):
        if role != "publisher" or self.records[name].state != "DRAFT":
            raise DemoError("REGISTRY_SUBMIT_DENIED")
        self.records[name].state = "PENDING_APPROVAL"

    def decide(self, name: str, state: str, role: str):
        if role != "approver" or state not in {"APPROVED", "REJECTED"}:
            raise DemoError("REGISTRY_APPROVAL_DENIED")
        if self.records[name].state != "PENDING_APPROVAL":
            raise DemoError("REGISTRY_INVALID_TRANSITION")
        self.records[name].state = state

    def search(self, query: str, role="consumer") -> list[dict]:
        if role not in {"consumer", "publisher", "approver"}:
            raise DemoError("REGISTRY_SEARCH_DENIED")
        # Busca lexical determinística no modo local; AWS usa search_registry_records.
        return [
            asdict(r)
            for r in self.records.values()
            if r.state == "APPROVED" and query.casefold() in (r.name + r.description).casefold()
        ]


def checked_endpoint(endpoint: str, allowed: set[str]) -> str:
    parsed = urlsplit(endpoint)
    if (
        endpoint not in allowed
        or parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.fragment
    ):
        raise DemoError("UNTRUSTED_ENDPOINT")
    return endpoint


def seed_local_registry() -> LocalRegistry:
    registry = LocalRegistry()
    for tool, spec in TOOLS.items():
        registry.publish(Record(tool, tool, spec["description"]), "publisher")
        registry.submit(tool, "publisher")
        registry.decide(tool, "APPROVED", "approver")
    registry.publish(
        Record("rascunho", "unpublished", "Capacidade ainda não aprovada"), "publisher"
    )
    registry.publish(Record("rejeitado", "rejected", "Capacidade rejeitada"), "publisher")
    registry.submit("rejeitado", "publisher")
    registry.decide("rejeitado", "REJECTED", "approver")
    return registry
