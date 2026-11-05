"""Apply the reviewed model update to a checkout of the pinned official workshops.

This edits files only. It never invokes AWS or marks a notebook as validated.
"""
import argparse
import hashlib
import json
from pathlib import Path

REPLACEMENTS = {
    "us.anthropic.claude-3-7-sonnet-20250219-v1:0": "us.anthropic.claude-sonnet-4-6",
    "anthropic.claude-3-5-haiku-20241022-v1:0": "us.anthropic.claude-haiku-4-5-20251001-v1:0",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workshops", type=Path, help="Pasta 06-workshops da revisão fixada")
    parser.add_argument("--execute", action="store_true", help="Gravar as alterações planejadas")
    args = parser.parse_args()
    changes = json.loads(Path(__file__).with_name("modelos-atualizados.json").read_text())
    prepared = []
    for item in changes["notebooks"]:
        path = args.workshops / item["path"]
        raw = path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != item["original_sha256"]:
            raise SystemExit(f"Arquivo diferente da revisão de referência: {item['path']}")
        notebook = json.loads(raw)
        for cell in notebook["cells"]:
            source = "".join(cell["source"])
            for old, new in REPLACEMENTS.items():
                source = source.replace(old, new)
            cell["source"] = source.splitlines(keepends=True)
            if cell["cell_type"] == "code":
                cell["outputs"] = []
                cell["execution_count"] = None
        prepared.append((path, notebook))
    # Verify every input before writing any output.
    if args.execute:
        for path, notebook in prepared:
            path.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n")
    print(json.dumps({"notebooks": len(prepared), "written": args.execute,
                      "aws_invoked": False, "validated": False}, indent=2))


if __name__ == "__main__":
    main()
