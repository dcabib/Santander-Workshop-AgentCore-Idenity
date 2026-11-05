"""Identificadores criados pelas aulas; este módulo não faz chamadas AWS."""

import json
import os
import re
import tempfile
import uuid
from pathlib import Path

SECRET_KEYS = {
    "password", "clientsecret", "client_secret", "secretstring", "secretbinary",
    "accesskeyid", "secretaccesskey", "sessiontoken", "aws_access_key_id",
    "aws_secret_access_key", "aws_session_token", "accesstoken", "access_token",
    "idtoken", "id_token", "refreshtoken", "refresh_token", "authorization",
}


def identifiers_only(value):
    """Evita salvar respostas de autenticação junto aos identificadores."""
    if isinstance(value, dict):
        if any(str(key).lower() in SECRET_KEYS for key in value):
            raise ValueError("NOTEBOOK_STATE_SECRETS_FORBIDDEN")
        for child in value.values():
            identifiers_only(child)
    elif isinstance(value, list):
        for child in value:
            identifiers_only(child)


class NotebookState:
    """Estado por conta/região, independente de stacks, perfis ou paths do evento."""

    def __init__(self, directory, *, account_id, region):
        if not re.fullmatch(r"\d{12}", account_id):
            raise ValueError("NOTEBOOK_ACCOUNT_INVALID")
        if not re.fullmatch(r"[a-z]{2}(?:-[a-z]+)+-\d+", region):
            raise ValueError("NOTEBOOK_REGION_INVALID")
        self.path = Path(directory) / f"{account_id}-{region}.json"
        if self.path.exists():
            self.data = json.loads(self.path.read_text())
            if (
                self.data.get("schema_version") != 1
                or self.data.get("account_id") != account_id
                or self.data.get("region") != region
                or not re.fullmatch(r"[0-9a-f]{12}", self.data.get("run_id", ""))
                or not isinstance(self.data.get("resources"), dict)
                or not isinstance(self.data.get("released_resources", {}), dict)
                or self.data.get("status", "ACTIVE") not in {"ACTIVE", "CLEANED"}
                or (self.data.get("status") == "CLEANED" and self.data.get("resources"))
            ):
                raise ValueError("NOTEBOOK_STATE_CONTEXT_MISMATCH")
            identifiers_only(self.data)
        else:
            self.data = {
                "schema_version": 1,
                "account_id": account_id,
                "region": region,
                "run_id": uuid.uuid4().hex[:12],
                "status": "ACTIVE",
                "resources": {},
            }
            self.save()

    @property
    def prefix(self):
        return "santander-" + self.data["run_id"]

    @property
    def tags(self):
        return {
            "workshop": "santander-agentcore",
            "workshop-run": self.data["run_id"],
        }

    @property
    def is_closed(self):
        return self.data.get("status") == "CLEANED"

    def get(self, key):
        value = self.data["resources"].get(key)
        return None if value is None else json.loads(json.dumps(value))

    def require(self, key, *, lesson):
        value = self.get(key)
        if value is None:
            raise RuntimeError(
                f"NOTEBOOK_STEP_REQUIRED: execute a criação de {key!r} na aula {lesson}."
            )
        return value

    def record(self, key, identifiers, *, lesson):
        """Guarda somente os campos selecionados na célula, nunca a resposta inteira."""
        if self.is_closed:
            raise RuntimeError("NOTEBOOK_EXECUTION_CLOSED: execute a aula 00 para iniciar outra execução.")
        if not isinstance(identifiers, dict) or not identifiers:
            raise ValueError("NOTEBOOK_IDENTIFIERS_REQUIRED")
        identifiers_only(identifiers)
        entry = json.loads(json.dumps({**identifiers, "lesson": str(lesson)}))
        previous = self.data["resources"].get(key)
        if previous is not None and previous != entry:
            raise ValueError("NOTEBOOK_RESOURCE_ALREADY_RECORDED: " + key)
        self.data["resources"][key] = entry
        try:
            self.save()
        except Exception:
            if previous is None:
                del self.data["resources"][key]
            else:
                self.data["resources"][key] = previous
            raise
        return self.get(key)

    def forget(self, key, *, expected):
        """Remover do registro somente depois de confirmar a exclusão na AWS."""
        if self.data["resources"].get(key) != expected:
            raise ValueError("NOTEBOOK_CLEANUP_STATE_CHANGED")
        previous = self.data["resources"].pop(key)
        released_before = self.data.get("released_resources")
        self.data["released_resources"] = {**(released_before or {}), key: previous}
        try:
            self.save()
        except Exception:
            self.data["resources"][key] = previous
            if released_before is None:
                self.data.pop("released_resources", None)
            else:
                self.data["released_resources"] = released_before
            raise

    def complete_cleanup(self):
        """Fecha o registro somente depois de todas as confirmações da aula 99."""
        if self.data["resources"]:
            raise RuntimeError("NOTEBOOK_CLEANUP_INCOMPLETE")
        if self.is_closed:
            return
        previous = self.data.get("status")
        self.data["status"] = "CLEANED"
        try:
            self.save()
        except Exception:
            if previous is None:
                self.data.pop("status", None)
            else:
                self.data["status"] = previous
            raise

    def start_new_execution(self):
        """Aula 00: arquiva a execução limpa e escolhe novos nomes sem tocar AWS."""
        if not self.is_closed or self.data["resources"]:
            raise RuntimeError("NOTEBOOK_ACTIVE_EXECUTION: conclua a aula 99 antes de reiniciar.")
        previous = self.data
        archive = self.path.parent / "history" / (
            f"{previous['account_id']}-{previous['region']}-{previous['run_id']}.json"
        )
        if archive.exists():
            if json.loads(archive.read_text()) != previous:
                raise ValueError("NOTEBOOK_HISTORY_MISMATCH")
        else:
            self._write(archive, previous, exclusive=True)
        self.data = {
            "schema_version": 1,
            "account_id": previous["account_id"],
            "region": previous["region"],
            "run_id": uuid.uuid4().hex[:12],
            "status": "ACTIVE",
            "resources": {},
        }
        try:
            self.save()
        except Exception:
            self.data = previous
            raise
        return archive

    def save(self):
        self._write(self.path, self.data)

    @staticmethod
    def _write(path, data, *, exclusive=False):
        identifiers_only(data)
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent, delete=False,
            ) as output:
                temporary = Path(output.name)
                json.dump(data, output, ensure_ascii=False, indent=2)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())
            if exclusive:
                os.link(temporary, path)
            else:
                os.replace(temporary, path)
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
