import json
from unittest.mock import Mock

import nbformat
import pytest

from santander_demo.aws_workshop import manifest
from santander_demo.aws_workshop.config import DOMAINS
from scripts import verify_notebooks, workshop_runner
from scripts.generate_aws_notebooks import build_notebook


@pytest.fixture
def config():
    return {
        "schema_version": 1,
        "project": "test-workshop",
        "region": "us-east-1",
        "auth_provider": "cognito",
        "source_kind": "aws_simulated_databricks",
        "accounts": {
            name: {"id": str(index + 1) * 12, "profile": name}
            for index, name in enumerate(DOMAINS)
        },
    }


def single_account(config):
    for domain in DOMAINS[1:]:
        config["accounts"][domain] = {"id": None, "profile": None}
    return config


def test_one_account_report_distinguishes_fundamentals_and_blocked_labs(config):
    report = manifest.account_plan(single_account(config))
    assert report["validation"] == "ACCOUNT_CONFIGURATION_ONLY"
    assert report["status"] == "BLOCKED"
    blocked = [row["lab"] for row in report["labs"] if row["status"] == "BLOCKED"]
    assert blocked == ["10", "11", "12", "13", "14"]
    assert all(row["status"] != "PASS" for row in report["labs"])


def test_three_account_flow_does_not_claim_three_account_deployment(config):
    config["accounts"]["lending-wealth"]["id"] = None
    report = manifest.account_plan(config, ["14"])
    row, = report["labs"]
    assert len(row["scenario_accounts"]) == 3
    assert row["required_count"] == 4
    assert row["status"] == "BLOCKED"
    with pytest.raises(ValueError, match="aula 14 exige 4 contas distintas"):
        manifest.assert_account_plan(report)


def test_duplicate_account_ids_are_blocked_even_with_different_profiles(config, monkeypatch):
    config["accounts"]["retail-banking"]["id"] = config["accounts"]["platform"]["id"]
    sts = Mock()
    monkeypatch.setattr(manifest, "check_accounts", sts)
    with pytest.raises(ValueError, match="IDs repetidos"):
        manifest.require(config, "10")
    sts.assert_not_called()


def test_full_selection_is_blocked_before_any_lesson_or_aws_call(config, monkeypatch):
    require = Mock()
    monkeypatch.setattr(manifest, "require", require)
    with pytest.raises(ValueError, match="aula 14 exige 4"):
        manifest.check_selection(single_account(config), ["00", "14"])
    require.assert_not_called()


def test_fundamentals_selection_does_not_require_domain_accounts(config, monkeypatch):
    require = Mock(return_value={"core": {}})
    monkeypatch.setattr(manifest, "require", require)
    result = manifest.check_selection(single_account(config), ["00", "01", "09", "15", "16"])
    assert list(result) == ["00", "01", "09", "15", "16"]
    assert require.call_count == 5


def test_runner_still_requires_four_accounts_for_partial_selection(config):
    report = manifest.account_plan(single_account(config), ["00"], runner=True)
    assert report["labs"][0]["status"] == "ACCOUNTS_CONFIGURED"
    assert report["status"] == "BLOCKED"
    with pytest.raises(ValueError, match="runner completo exige 4 contas distintas"):
        manifest.assert_account_plan(report)


def test_complete_configuration_is_not_operational_acceptance(config):
    report = manifest.account_plan(config, runner=True)
    assert report["status"] == "ACCOUNTS_CONFIGURED"
    assert not report["runner_blockers"]
    assert all(row["status"] == "ACCOUNTS_CONFIGURED" for row in report["labs"])


def test_unknown_lesson_is_not_silently_omitted(config):
    with pytest.raises(ValueError, match="UNKNOWN_LAB:17"):
        manifest.account_plan(config, ["00", "17"])


@pytest.mark.parametrize("override,saved,expected", [
    ([], "00 01", ["00", "01"]),
    ([], "", []),
    (["14"], "00 01", ["14"]),
])
def test_runner_preflights_the_effective_build_selection(
    config, monkeypatch, override, saved, expected,
):
    codebuild = Mock()
    codebuild.batch_get_projects.return_value = {"projects": [{
        "environment": {"environmentVariables": [{"name": "WORKSHOP_LABS", "value": saved}]},
    }]}
    check = Mock()
    monkeypatch.setattr(workshop_runner, "check_selection", check)
    workshop_runner.preflight_run(config, codebuild, "test-notebooks", override)
    check.assert_called_once_with(config, expected, runner=True)
    if override:
        codebuild.batch_get_projects.assert_not_called()


def test_run_cannot_start_build_when_accounts_are_missing(config, monkeypatch):
    config = single_account(config)
    codebuild = Mock()
    aws = Mock()
    aws.client.return_value = codebuild
    monkeypatch.setattr(workshop_runner, "load", lambda _: config)
    monkeypatch.setattr(workshop_runner, "check_accounts", Mock())
    monkeypatch.setattr(workshop_runner, "outputs", lambda *_: {"ProjectName": "test-notebooks"})
    monkeypatch.setattr(workshop_runner, "session", lambda *_: aws)
    monkeypatch.setattr("sys.argv", ["workshop_runner.py", "run", "--labs", "14", "--execute"])
    with pytest.raises(ValueError, match="WORKSHOP_PREREQUISITES_BLOCKED"):
        workshop_runner.main()
    codebuild.start_build.assert_not_called()


def test_runner_deploy_blocks_missing_accounts_before_packaging_or_upload(config, monkeypatch):
    package = Mock()
    aws = Mock()
    monkeypatch.setattr(workshop_runner, "package", package)
    monkeypatch.setattr(workshop_runner, "session", aws)
    with pytest.raises(ValueError, match="runner completo exige 4"):
        workshop_runner.deploy(single_account(config), ["00"], True)
    package.assert_not_called()
    aws.assert_not_called()


def test_notebook_batch_checks_later_labs_before_starting_first_kernel(
    config, tmp_path, monkeypatch,
):
    notebooks = tmp_path / "notebooks"
    notebooks.mkdir()
    for number in ["00", "14"]:
        nbformat.write(nbformat.v4.new_notebook(), notebooks / f"{number}_example.ipynb")
    monkeypatch.setattr(verify_notebooks, "ROOT", tmp_path)
    monkeypatch.setattr(verify_notebooks, "load", lambda _: single_account(config))
    monkeypatch.setenv("CODEBUILD_BUILD_ARN", "synthetic-build")
    output = tmp_path / "previous-results.json"
    output.write_text('[{"status": "PASS", "validation": "AWS_EXECUTION"}]')
    monkeypatch.setattr("sys.argv", [
        "verify_notebooks.py", "--labs", "00", "14", "--output", str(output),
    ])
    kernel = Mock()
    monkeypatch.setattr(verify_notebooks, "NotebookClient", kernel)
    with pytest.raises(ValueError, match="aula 14 exige 4"):
        verify_notebooks.main()
    kernel.assert_not_called()
    report = json.loads((tmp_path / "evidence/workshop-prerequisites.json").read_text())
    assert report["status"] == "BLOCKED"
    results = json.loads(output.read_text())
    assert len(results) == 2
    assert all(row["status"] == "BLOCKED" for row in results)
    assert all(row["validation"] == "AWS_PREFLIGHT" for row in results)


def test_notebook_warns_about_three_vs_four_accounts_before_any_code():
    notebook = build_notebook("14_cenario_santander_integrado")
    assert notebook.metadata.workshop.required_count == 4
    assert len(notebook.metadata.workshop.scenario_accounts) == 3
    introduction = "\n".join(
        cell.source for cell in notebook.cells[:next(
            i for i, cell in enumerate(notebook.cells) if cell.cell_type == "code"
        )]
    )
    assert "não executa em uma conta única" in introduction
    assert "fluxo mostrado envolve 3 contas" in introduction
    assert "quatro contas preparadas" in introduction
