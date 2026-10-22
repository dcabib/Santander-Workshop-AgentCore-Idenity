import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class Environment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    mode: Literal["aws"] = "aws"
    region: str
    profile: str | None = None
    hub_account: str = Field(pattern=r"^\d{12}$")
    origin_account: str = Field(pattern=r"^\d{12}$")
    fraud_account: str = Field(pattern=r"^\d{12}$")
    gateway_id: str
    gateway_arn: str
    gateway_url: str
    policy_engine_id: str
    registry_id: str
    registry_arn: str
    registry_consumer_role_arn: str
    tenant_id: str
    gateway_audience: str
    token_version: Literal["1.0", "2.0"]
    login_client_id: str
    login_scope: str
    agent_client_id: str | None = None
    agent_secret_arn: str | None = None
    gateway_obo_scope: str | None = None
    expected_graph_oid: str
    fraud_runtime_arn: str
    supervisor_runtime_arn: str
    risk_log_group: str
    fraud_log_group: str
    graph_tool: str = "graph___getMyProfile"
    databricks_host: str | None = None
    databricks_warehouse: str | None = None
    expected_databricks_user: str | None = None
    databricks_canary_table: str | None = None

    @classmethod
    def load(cls, path: str | Path):
        result = cls.model_validate_json(Path(path).read_text())
        if "REPLACE" in json.dumps(result.model_dump()):
            raise ValueError("Preencha config/local.json com os outputs IaC")
        return result
