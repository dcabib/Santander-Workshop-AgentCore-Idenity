"""Testa falhas de autenticação, ACL, configuração e evidência; não é aceite AWS."""

import subprocess
import sys
from pathlib import Path

if __name__ == "__main__":
    subprocess.run([sys.executable, "-m", "pytest", "-q",
                    "tests/test_aws_workshop_security.py", "tests/test_aws_workshop.py",
                    "tests/test_aws_notebook_evidence.py"],
                   cwd=Path(__file__).resolve().parents[1], check=True)
