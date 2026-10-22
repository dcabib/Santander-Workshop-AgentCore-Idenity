"""Contrato executável LOCAL de quotas; não representa medição AWS/Databricks."""

from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock


@dataclass(frozen=True)
class Limits:
    qpm: int
    tpm: int
    monthly_micro_usd: int

    def __post_init__(self):
        if any(type(n) is not int or n <= 0 for n in (self.qpm, self.tpm, self.monthly_micro_usd)):
            raise ValueError("POSITIVE_INTEGER_LIMITS_REQUIRED")


class LocalQuotaLedger:
    """Contadores por agente/tool, independentes de usuário/sessão.

    Tokens e custo são reservas vindas de um medidor confiável, nunca do prompt.
    Valores são sintéticos neste exercício. Em produção precisam de store atômico,
    idempotência, reconciliação de uso real e cobertura de todas as rotas.
    """

    def __init__(self):
        self.minute, self.month, self.lock = {}, {}, Lock()

    def reserve(self, agent, tool, *, tokens, micro_usd, now, limits):
        if any(type(n) is not int or n < 0 for n in (tokens, micro_usd)):
            raise ValueError("INVALID_MEASUREMENT")
        when = datetime.fromtimestamp(now, UTC)
        minute_key = (agent, tool, int(now // 60))
        month_key = (agent, tool, when.strftime("%Y-%m"))
        with self.lock:
            requests, used_tokens = self.minute.get(minute_key, (0, 0))
            spent = self.month.get(month_key, 0)
            if requests + 1 > limits.qpm:
                decision = "QPM_DENY"
            elif used_tokens + tokens > limits.tpm:
                decision = "TPM_DENY"
            elif spent + micro_usd > limits.monthly_micro_usd:
                decision = "BUDGET_DENY"
            else:
                self.minute[minute_key] = (requests + 1, used_tokens + tokens)
                self.month[month_key] = spent + micro_usd
                decision = "ALLOW"
        return {"mode": "LOCAL_QUOTA_CONTRACT", "decision": decision, "billing_measured": False}


def local_quota_demo():
    ledger = LocalQuotaLedger()
    caps = Limits(qpm=2, tpm=100, monthly_micro_usd=30)
    start = datetime(2026, 10, 1, tzinfo=UTC).timestamp()
    result = [
        ledger.reserve("riscos", "sql", tokens=40, micro_usd=10, now=start, limits=caps),
        ledger.reserve("riscos", "sql", tokens=40, micro_usd=10, now=start, limits=caps),
        ledger.reserve("riscos", "sql", tokens=1, micro_usd=1, now=start, limits=caps),
        ledger.reserve("riscos", "sql", tokens=101, micro_usd=1, now=start + 60, limits=caps),
        ledger.reserve("riscos", "sql", tokens=40, micro_usd=11, now=start + 60, limits=caps),
    ]
    assert [r["decision"] for r in result] == [
        "ALLOW",
        "ALLOW",
        "QPM_DENY",
        "TPM_DENY",
        "BUDGET_DENY",
    ]
    return result
