"""Measure complete, verified wires against the same JSON envelope baseline."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from aocx_core import compile_context, create_bundle, verify_representation


def measure(name, source, kind="repository-example"):
    result = compile_context(source, codecs=["aocx-expr/1", "aocx-expr-dict/1", "json/1"])
    report = result["report"]
    verified = verify_representation(source, result["representation"])
    if verified["status"] != "passed":
        raise RuntimeError("Measured representation failed source verification: " + name)
    candidates = report["candidates"]
    baseline = next(row["bytes"] for row in candidates if row["codec"] == "json/1" and row["status"] == "passed")
    return {"name": name, "kind": kind, "counts": verified["counts"],
            "source": report["source"], "selected_codec": report["selected_codec"],
            "wire_bytes": report["bytes"], "json_baseline_bytes": baseline,
            "saved_bytes": baseline - report["bytes"],
            "savings_fraction": round(1 - report["bytes"] / baseline, 6),
            "candidates": candidates, "verification": verified}


def measurements():
    cases = [measure(name, ROOT / "assets" / "examples" / name)
             for name in ("math", "document", "software")]
    formal = ROOT / "assets" / "examples" / "formal" / "source"
    if formal.is_dir():
        cases.append(measure("formal", formal))
    with tempfile.TemporaryDirectory(prefix="aocx-measure-") as temporary:
        source = Path(temporary) / "repeated"
        records = [{"id": "observation/" + str(index), "rev": "1", "kind": "research.observation",
                    "text": "在明确前提下记录观测。Record observations under explicit conditions.",
                    "scope": "Shared experimental context; preserve independent record identities.",
                    "state": {"work": "complete", "knowledge": "observed"},
                    "body": {"value": index, "unit": "µm", "calibration": "reference-standard/2026"},
                    "extensions": {"domain": "mixed-language-research"}}
                   for index in range(128)]
        create_bundle(records, [], source, "benchmark:repeated-context")
        cases.append(measure("repeated-context-128", source, "synthetic-repetition"))
    base = subprocess.run(["git", "merge-base", "HEAD", "origin/main"], cwd=ROOT,
                          capture_output=True, text=True, check=True).stdout.strip()
    return {"format": "AOCX-COMPILER-MEASUREMENTS", "version": "1.0",
            "measured_at": datetime.now(timezone.utc).isoformat(),
            "python": platform.python_version(), "source_base_commit": base,
            "metric": "bytes", "fidelity": "exact", "scope": "context-values",
            "cost_scope": "Complete UTF-8 wire, including codec header, contract, source binding and dictionary",
            "baseline": "json/1 encoding of the identical representation envelope",
            "search": "Finite set of the three bundled codecs; no global-minimum claim",
            "token_measurement": "not-run", "cases": cases}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    report = measurements()
    raw = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(raw, encoding="utf-8")
    else:
        sys.stdout.write(raw)


if __name__ == "__main__":
    main()
