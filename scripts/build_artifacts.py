"""Build local, reproduzível pelo uv.lock, para Lambda/Runtime Linux ARM64."""

import argparse
import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(args, quiet=False):
    subprocess.run(args, cwd=ROOT, check=True, stdout=subprocess.DEVNULL if quiet else None)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--banking", action="store_true", help="Inclui Strands/AgentCore para os notebooks 10/11"
    )
    args = parser.parse_args()
    prefix = "banking" if args.banking else "workshop"
    run(
        [
            "uv",
            "export",
            "--frozen",
            "--no-dev",
            "--no-emit-project",
            "--no-editable",
            *(["--extra", "banking"] if args.banking else []),
            "--format",
            "requirements-txt",
            "--output-file",
            "build/requirements.txt",
        ],
        quiet=True,
    )
    target = ROOT / "build" / ("banking-package" if args.banking else "package")
    if target.exists():
        shutil.rmtree(target)
    target.mkdir(parents=True)
    run(
        [
            "uv",
            "pip",
            "install",
            "--python-platform",
            "aarch64-manylinux2014",
            "--python-version",
            "3.12",
            "--only-binary",
            ":all:",
            "--target",
            str(target),
            "-r",
            "build/requirements.txt",
        ]
    )
    shutil.copytree(
        ROOT / "src/santander_demo",
        target / "santander_demo",
        ignore=shutil.ignore_patterns("__pycache__"),
    )
    shutil.copy(ROOT / "infra/providers/registry_handler.py", target / "registry_handler.py")
    shutil.copy(
        ROOT / "infra/providers/policy_draft_handler.py", target / "policy_draft_handler.py"
    )
    shutil.copy(ROOT / "infra/runtime_main.py", target / "runtime_main.py")
    if args.banking:
        shutil.copy(ROOT / "infra/banking/runtime_main.py", target / "banking_runtime_main.py")
        shutil.copy(ROOT / "infra/journey/runtime_main.py", target / "journey_runtime_main.py")
        shutil.copy(ROOT / "infra/banking/seed_handler.py", target / "banking_seed_handler.py")
        shutil.copy(ROOT / "docs/banking/UPSTREAM-LICENSE", target / "BANKING-UPSTREAM-LICENSE")
    path = ROOT / "build" / f"{prefix}.zip"
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for file in sorted(target.rglob("*")):
            if file.is_file() and "__pycache__" not in file.parts:
                info = zipfile.ZipInfo(
                    str(file.relative_to(target)), date_time=(2026, 1, 1, 0, 0, 0)
                )
                info.compress_type = zipfile.ZIP_DEFLATED
                info.external_attr = 0o644 << 16
                z.writestr(info, file.read_bytes())
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = {
        "file": f"build/{prefix}.zip",
        "sha256": digest,
        "key": f"{prefix}/{digest}.zip",
        "architecture": "arm64",
        "runtime": "python3.12",
    }
    manifest_name = "banking-artifacts.json" if args.banking else "artifacts.json"
    (ROOT / "build" / manifest_name).write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    (ROOT / "build").mkdir(exist_ok=True)
    main()
