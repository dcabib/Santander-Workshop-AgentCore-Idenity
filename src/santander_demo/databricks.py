"""Extensão opt-in: troca RFC 8693 sem fallback para service principal."""

import re
import time
from urllib.parse import urlsplit

import httpx

from santander_demo.contracts import DemoError


class DelegatedDatabricks:
    def __init__(self, host, warehouse, expected_user, *, http=None):
        url = urlsplit(host)
        if url.scheme != "https" or url.path not in {"", "/"} or url.username or url.query:
            raise ValueError("Host Databricks HTTPS inválido")
        if not expected_user or not warehouse:
            raise ValueError("Principal esperado e warehouse são obrigatórios")
        self.host, self.warehouse, self.expected = host.rstrip("/"), warehouse, expected_user
        self.http = http or httpx.Client(timeout=45, follow_redirects=False)

    def exchange(self, user_jwt: str):
        if not user_jwt:
            raise DemoError("DELEGATION_REQUIRED")
        response = self.http.post(
            self.host + "/oidc/v1/token",
            data={
                "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
                "subject_token": user_jwt,
                "subject_token_type": "urn:ietf:params:oauth:token-type:jwt",
                "scope": "all-apis",
            },
        )
        if response.status_code != 200:
            raise DemoError("DATABRICKS_EXCHANGE_DENIED")
        token = response.json().get("access_token")
        if not token:
            raise DemoError("DATABRICKS_NO_DELEGATED_TOKEN")
        return token

    def _sql(self, token, statement):
        headers = {"Authorization": f"Bearer {token}"}
        response = self.http.post(
            self.host + "/api/2.0/sql/statements",
            headers=headers,
            json={
                "warehouse_id": self.warehouse,
                "statement": statement,
                "wait_timeout": "10s",
                "on_wait_timeout": "CANCEL",
                "row_limit": 1,
            },
        )
        if response.status_code != 200:
            raise DemoError("DATABRICKS_SQL_HTTP_ERROR")
        body = response.json()
        deadline = time.monotonic() + 30
        while body.get("status", {}).get("state") in {"PENDING", "RUNNING"}:
            if time.monotonic() >= deadline:
                raise DemoError("DATABRICKS_SQL_TIMEOUT")
            time.sleep(1)
            response = self.http.get(
                self.host + "/api/2.0/sql/statements/" + body["statement_id"], headers=headers
            )
            if response.status_code != 200:
                raise DemoError("DATABRICKS_SQL_HTTP_ERROR")
            body = response.json()
        return body

    def prove(self, user_jwt: str, canary_table: str, *, expect_grant: bool):
        if not re.fullmatch(r"[a-zA-Z_]\w*\.[a-zA-Z_]\w*\.[a-zA-Z_]\w*", canary_table):
            raise ValueError("Use catalog.schema.table para uma tabela CANÁRIO sintética")
        token = self.exchange(user_jwt)
        identity = self._sql(token, "SELECT current_user()")
        if identity.get("status", {}).get("state") != "SUCCEEDED":
            raise DemoError("DATABRICKS_IDENTITY_QUERY_FAILED")
        rows = identity.get("result", {}).get("data_array", [])
        if not rows or rows[0][0] != self.expected:
            raise DemoError("DATABRICKS_PRINCIPAL_MISMATCH")
        grant = self._sql(token, f"SELECT 1 FROM {canary_table} LIMIT 1")
        state = grant.get("status", {}).get("state")
        if expect_grant:
            if state != "SUCCEEDED":
                raise DemoError("DATABRICKS_EXPECTED_GRANT_FAILED")
        else:
            error = grant.get("status", {}).get("error", {})
            # SQL inválido, warehouse parado ou falha de rede não provam negação de grant.
            if state != "FAILED" or error.get("error_code") not in {
                "PERMISSION_DENIED",
                "INSUFFICIENT_PERMISSIONS",
            }:
                raise DemoError("DATABRICKS_DENIAL_NOT_PROVEN")
        return {"mode": "DATABRICKS_LIVE", "principal_matches": True, "grant": expect_grant}
