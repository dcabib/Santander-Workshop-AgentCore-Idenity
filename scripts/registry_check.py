"""Verifica catálogo, permissões e execução nos serviços AWS implantados."""

import argparse
import json
from pathlib import Path

from santander_demo.registry_workflow.client import RegistryLab


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--config", default="config/aws.registry.json")
    args = p.parse_args()
    result = RegistryLab(json.loads(Path(args.config).read_text())).acceptance()
    Path("evidence").mkdir(exist_ok=True)
    Path("evidence/registry-personas.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
