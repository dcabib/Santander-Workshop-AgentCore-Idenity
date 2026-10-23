"""Build local do laboratório Terraform. Não acessa nem altera recursos AWS."""

import hashlib
import json
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build/terraform-agentcore"
SOURCE = ROOT / "src/santander_demo/terraform_lab"


def reproducible_zip(path, files):
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        for name, content in sorted(files):
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, content)


def build():
    BUILD.mkdir(parents=True, exist_ok=True)
    package = BUILD / "package"
    if package.exists():
        shutil.rmtree(package)
    subprocess.run([
        "uv", "pip", "install", "--python-platform", "aarch64-manylinux2014",
        "--python-version", "3.12", "--only-binary", ":all:", "--require-hashes",
        "--target", str(package), "-r",
        str(ROOT / "infra/terraform_agentcore/requirements.lock"),
    ], check=True, cwd=ROOT)
    module = package / "santander_demo/terraform_lab"
    module.mkdir(parents=True)
    (module.parent / "__init__.py").write_text("")
    for name in ("__init__.py", "backend.py", "runtime.py"):
        shutil.copy2(SOURCE / name, module / name)
    (package / "main.py").write_text(
        'from santander_demo.terraform_lab.runtime import app\n\n'
        'if __name__ == "__main__":\n    app.run()\n'
    )
    runtime = BUILD / "runtime.zip"
    reproducible_zip(runtime, [
        (p.relative_to(package).as_posix(), p.read_bytes())
        for p in package.rglob("*")
        if p.is_file() and "__pycache__" not in p.parts and p.suffix != ".pyc"
        and p.name not in {".lock", ".gitignore"}
    ])
    backend = BUILD / "lambda.zip"
    reproducible_zip(backend, [("backend.py", (SOURCE / "backend.py").read_bytes())])
    manifest = {
        "architecture": "arm64",
        "python": "3.12",
        "requirements_sha256": hashlib.sha256(
            (ROOT / "infra/terraform_agentcore/requirements.lock").read_bytes()
        ).hexdigest(),
        "artifacts": {
            name: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
            for name, path in (("runtime", runtime), ("lambda", backend))
        },
    }
    (BUILD / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
