"""Bancada sem AWS: JWT RSA real + avaliador Cedar real + serviços simulados."""

from dataclasses import asdict, dataclass, field

from santander_demo import backends
from santander_demo.contracts import CLIENTE, LOCAL_ENDPOINT, TOOLS, DemoError, tool_descriptors
from santander_demo.identity import LocalIssuer
from santander_demo.policy import PolicyContract, authorize
from santander_demo.registry import checked_endpoint, seed_local_registry


@dataclass
class Evidence:
    mode: str = "LOCAL_SIMULATION"
    events: list[dict] = field(default_factory=list)
    backend_invocations: int = 0

    def export(self):
        return asdict(self)


class Workshop:
    def __init__(self):
        self.idp = LocalIssuer()
        self.registry = seed_local_registry()
        self.policy = PolicyContract()
        self.evidence = Evidence()

    def tools(self):
        return tool_descriptors()

    def call(self, token: str, tool: str, arguments: dict):
        try:
            identity = self.idp.verifier.verify(token)
            if tool not in TOOLS:
                raise DemoError("UNKNOWN_TOOL")
            backends.validate_input(arguments)
            decision = authorize(identity, tool, arguments, self.policy)
            if not decision.allowed:
                raise DemoError("POLICY_DENY")
            result = backends.execute(tool, arguments)
            self.evidence.backend_invocations += 1
            self.evidence.events.append({"tool": tool, "outcome": "ALLOW", **identity.summary()})
            return result
        except DemoError as exc:
            self.evidence.events.append({"tool": tool, "outcome": exc.code})
            raise

    def analyze(self, token: str, cliente_id=CLIENTE):
        """Supervisor determinístico: a seleção não concede autorização."""
        results = []
        for domain in ("risco", "fraude"):
            records = self.registry.search(domain)
            for record in records:
                checked_endpoint(record["endpoint"], {LOCAL_ENDPOINT})
                try:
                    results.append(
                        self.call(
                            token,
                            record["tool"],
                            {
                                "cliente_id": cliente_id,
                                "max_registros": 10,
                            },
                        )
                    )
                except DemoError as exc:
                    results.append({"tool": record["tool"], "outcome": exc.code})
        return {"mode": "LOCAL_SIMULATION", "results": results}

    def policy_matrix(self):
        tests = [
            ("P-SAN-01 positivo", "riscos", "riscos", "riscos___consultar_risco", 50, {}, "ALLOW"),
            (
                "P-SAN-01 chamador",
                "riscos",
                "intruso",
                "riscos___consultar_risco",
                50,
                {},
                "POLICY_DENY",
            ),
            (
                "P-SAN-02 usuário",
                "riscos",
                "supervisor",
                "fraude___consultar_fraude",
                10,
                {},
                "POLICY_DENY",
            ),
            (
                "P-SAN-02 positivo",
                "ambos",
                "supervisor",
                "fraude___consultar_fraude",
                10,
                {},
                "ALLOW",
            ),
            (
                "P-SAN-03 limite",
                "ambos",
                "supervisor",
                "riscos___consultar_risco",
                51,
                {},
                "POLICY_DENY",
            ),
            (
                "P-SAN-03 obrigatório",
                "ambos",
                "supervisor",
                "riscos___consultar_risco",
                None,
                {},
                "SCHEMA_INVALID",
            ),
            (
                "P-SAN-04 outra tool",
                "ambos",
                "supervisor",
                "intruso___consultar_risco",
                10,
                {},
                "UNKNOWN_TOOL",
            ),
            (
                "P-SAN-05 claim",
                "ambos",
                "supervisor",
                "riscos___consultar_risco",
                10,
                {"oid": None},
                "POLICY_DENY",
            ),
            (
                "P-SAN-06 delegação",
                "ambos",
                "riscos",
                "fraude___consultar_fraude",
                10,
                {},
                "POLICY_DENY",
            ),
            (
                "Identity audiência",
                "ambos",
                "supervisor",
                "riscos___consultar_risco",
                10,
                {"aud": "wrong"},
                "AUTH_INVALID_TOKEN",
            ),
            (
                "Identity expirado",
                "ambos",
                "supervisor",
                "riscos___consultar_risco",
                10,
                {"exp": 1},
                "AUTH_INVALID_TOKEN",
            ),
            (
                "Identity M2M",
                "ambos",
                "supervisor",
                "riscos___consultar_risco",
                10,
                {"scp": None},
                "POLICY_DENY",
            ),
        ]
        rows = []
        for name, user, caller, tool, limit, changes, expected in tests:
            args = {"cliente_id": CLIENTE}
            if limit is not None:
                args["max_registros"] = limit
            before = self.evidence.backend_invocations
            try:
                self.call(self.idp.token(user, caller, **changes), tool, args)
                outcome = "ALLOW"
            except DemoError as exc:
                outcome = exc.code
            delta = self.evidence.backend_invocations - before
            assert outcome == expected, (name, outcome, expected)
            assert delta == (1 if expected == "ALLOW" else 0), name
            rows.append({"test": name, "outcome": outcome, "backend_calls": delta, "passed": True})
        return rows
