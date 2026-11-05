"""Normalização de respostas SDK; nenhuma chamada ou mutação AWS."""

import copy
import io
import json
import zipfile


def managed_source_configuration(configuration):
    """Concilia somente os defaults observados no conector S3 MANAGED.

    GetDataSource pode devolver connectorParameters como JSON serializado.
    A extração de imagens ENABLED e o limite de 500 MB são defaults do
    serviço. Qualquer outro campo ou valor é preservado para detectar drift.
    """
    result = copy.deepcopy(configuration)
    if result.get("type") != "MANAGED_KNOWLEDGE_BASE_CONNECTOR":
        return result
    connector = result["managedKnowledgeBaseConnectorConfiguration"]
    parameters = connector["connectorParameters"]
    if isinstance(parameters, str):
        parameters = json.loads(parameters)
        if not isinstance(parameters, dict):
            raise ValueError("CONNECTOR_PARAMETERS_OBJECT_REQUIRED")
        connector["connectorParameters"] = parameters
    if parameters.get("type") != "S3":
        return result
    filters = parameters.get("filterConfiguration", {})
    if filters.get("maxFileSizeInMegaBytes") == "500":
        del filters["maxFileSizeInMegaBytes"]
    if connector.get("mediaExtractionConfiguration") == {
        "imageExtractionConfiguration": {"imageExtractionStatus": "ENABLED"},
    }:
        del connector["mediaExtractionConfiguration"]
    return result


def native_knowledge_connector(configuration):
    """A versão 1.0.0 é o default observado; outras versões mantêm drift."""
    result = copy.deepcopy(configuration)
    source = result.get("mcp", {}).get("connector", {}).get("source", {})
    if source.get("connectorId") == "bedrock-knowledge-bases" and source.get("version") == "1.0.0":
        del source["version"]
    return result


RAG_MODULES = {
    "bedrock_agentcore/runtime/app.py", "boto3/__init__.py",
    "httpx/__init__.py", "jwt/__init__.py", "main.py",
}


def validate_rag_archive(content, source):
    """Rejeita dependências ausentes, main.py diferente e caminhos duplicados."""
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        names = archive.namelist()
        if len(names) != len(set(names)):
            raise ValueError("RAG_ARCHIVE_DUPLICATE_FILES")
        missing = RAG_MODULES - set(names)
        if missing:
            raise ValueError("RAG_ARCHIVE_MISSING_MODULES: " + ", ".join(sorted(missing)))
        if archive.read("main.py") != source.encode():
            raise ValueError("RAG_ARCHIVE_SOURCE_MISMATCH")
