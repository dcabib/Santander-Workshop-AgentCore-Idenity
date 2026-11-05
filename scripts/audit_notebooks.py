"""Confronta evidências da execução AWS com os notebooks distribuídos."""

import argparse
import hashlib
import json
from pathlib import Path

import nbformat

from santander_demo.notebook_catalog import LAB_ALIASES, lab_id

ROOT = Path(__file__).resolve().parents[1]


def audit(evidence, source_dir, executed_dir, labs=None):
    labs = [lab_id(lab) for lab in labs] if labs else None
    paths = [p for p in sorted(source_dir.glob("*.ipynb")) if not labs or lab_id(p) in labs]
    if not paths:
        raise ValueError("NO_NOTEBOOKS")
    if labs and {lab_id(path) for path in paths} != set(labs):
        raise ValueError("SELECTED_NOTEBOOK_FILES_MISSING")
    rows = {row["notebook"]: row for row in evidence}
    if len(rows) != len(evidence):
        raise ValueError("DUPLICATE_EVIDENCE")
    for path in paths:
        row = rows.get(path.name)
        if not row or row.get("validation") != "AWS_EXECUTION" or row.get("status") != "PASS":
            raise ValueError("AWS_ACCEPTANCE_MISSING:" + path.name)
        if row["source_sha256"] != hashlib.sha256(path.read_bytes()).hexdigest():
            raise ValueError("STALE_EVIDENCE:" + path.name)
        source = nbformat.read(path, as_version=4)
        executed = nbformat.read(executed_dir / path.name, as_version=4)
        if [(c.cell_type, c.source) for c in source.cells] != [
            (c.cell_type, c.source) for c in executed.cells
        ]:
            raise ValueError("EXECUTED_SOURCE_MISMATCH:" + path.name)
        code = [c for c in executed.cells if c.cell_type == "code"]
        if row["code_cells"] != len(code) or any(c.execution_count is None for c in code):
            raise ValueError("INCOMPLETE_EXECUTION:" + path.name)
        if any(o.output_type == "error" for cell in code for o in cell.outputs):
            raise ValueError("CELL_ERROR:" + path.name)
    return {"status": "MATCH", "notebooks": len(paths),
            "labs": [path.name[:2] for path in paths], "scope": "AWS_NOTEBOOK_EVIDENCE"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence", default="evidence/notebooks-aws.json")
    parser.add_argument("--executed", default="evidence/executed")
    parser.add_argument("--labs", nargs="+", choices=[*[f"{n:02d}" for n in range(17)], *LAB_ALIASES])
    args = parser.parse_args()
    result = audit(json.loads(Path(args.evidence).read_text()), ROOT / "notebooks",
                   Path(args.executed), args.labs)
    print(json.dumps(result))


if __name__ == "__main__":
    main()
