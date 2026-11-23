"""Run real legacy imports and byte restoration outside the installed Skill.

Inputs are supplied explicitly; original archives are never copied into assets.
"""

from pathlib import Path
from zipfile import ZipFile
import argparse
import hashlib
import importlib.util
import json
import sys
import uuid


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_core(root):
    spec = importlib.util.spec_from_file_location("aocx_legacy_acceptance", root / "scripts/aocx.py")
    core = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = core
    spec.loader.exec_module(core)
    return core


def read_tables(folder):
    manifest = json.loads((folder / "aocx.json").read_text())
    result = {}
    for key in ("records", "relations"):
        result[key] = [json.loads(line) for line in (folder / manifest[key]).read_text().splitlines() if line]
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--gbcx", type=Path, required=True)
    parser.add_argument("--aoci", type=Path)
    parser.add_argument("--work", type=Path, required=True)
    parser.add_argument("--report", type=Path, default=Path(__file__).with_name("gbcx_roundtrip.json"))
    args = parser.parse_args()
    skill = Path(__file__).resolve().parents[2]
    core_path = skill / "scripts/aocx.py"
    source_hash_before = digest(core_path)
    core = load_core(skill)
    run = args.work / ("legacy-roundtrip-" + uuid.uuid4().hex[:10])
    run.mkdir(parents=True)
    report = {
        "scope": "Structure, projection fidelity, exact origin restoration, and pinned condition closure",
        "core_sha256": source_hash_before,
        "adapter_sha256": {name: digest(skill / "scripts/adapters" / (name + ".py"))
                           for name in ("gbcx", "aoci")},
    }

    archive_hash = digest(args.gbcx)
    gbcx_output = run / "gbcx"
    imported = core.import_bundle(args.gbcx, gbcx_output, "acceptance:gbcx-real", "gbcx")
    assert imported["status"] == "passed", imported
    validation = core.validate_bundle(gbcx_output)
    assert validation["status"] == "passed", validation
    tables = read_tables(gbcx_output)
    full = core.parse_capsule(core.capsule(gbcx_output, full=True))
    assert full["records"] == tables["records"]
    assert full["relations"] == tables["relations"]
    assert len(full["records"]) == 422 and len(full["relations"]) == 320
    handoff = core.parse_capsule(core.capsule(gbcx_output))
    handoff_by_id = {r["id"]: r for r in handoff["records"]}
    method_count = symbol_count = 0
    for original_record in tables["records"]:
        record = handoff_by_id[original_record["id"]]
        native = original_record["body"]
        if original_record["kind"] == "method":
            method_count += 1
            assert record["state"]["method_use"] == native["state"]
            anchor = record["anchors"][0]
            for field in ("result", "next_test", "failure_scope"):
                assert anchor[field] == native[field]
        if original_record["kind"] == "term":
            symbol_count += 1
            assert record["anchors"][0]["symbol"] == native["symbol"]
        if original_record["kind"] == "task":
            anchor = record["anchors"][0]
            assert anchor["missing"] == native["missing"]
            assert anchor["next_discriminating_test"] == native["next_discriminating_test"]
        if original_record["kind"] == "source" and "url" in native:
            assert record["anchors"][0]["url"] == native["url"]
    assert method_count == 125 and symbol_count == 27
    fixed_source = handoff_by_id["SRC_R4_SIEVE_S021"]["anchors"][0]["original"]
    assert "4eaee87548250b2682affda7d05d947c05554bae" in fixed_source["url"]
    assert fixed_source["sha256"]
    selected = core.parse_capsule(core.capsule(gbcx_output, select=["R4R009"]))
    selected_records = {(r["id"], r["rev"]): r for r in selected["records"]}
    target = selected_records[("R4R009", "1")]
    expected = {"R4R006", "R4R007", "R4R008"}
    assert {c["ref"]["id"] for c in target["conditions"]} == expected
    for record in selected["records"]:
        for condition in record.get("conditions", []):
            if "ref" in condition:
                assert (condition["ref"]["id"], condition["ref"]["rev"]) in selected_records
    restored = run / "restored_gbcx.zip"
    restore_report = core.restore(gbcx_output, restored)
    assert digest(restored) == archive_hash == digest(args.gbcx)
    report["gbcx"] = {
        "source_sha256": archive_hash, "source_bytes": args.gbcx.stat().st_size,
        "import": imported, "validation": validation,
        "full_capsule": {"records": len(full["records"]), "relations": len(full["relations"]),
                         "all_json_values_equal": True},
        "handoff_capsule": {"method_states_retained": method_count, "symbol_names_retained": symbol_count,
                            "method_results_and_next_tests_retained": True,
                            "frontier_missing_inputs_and_next_steps_retained": True,
                            "source_urls_and_fixed_version_locators_retained": True},
        "selected_capsule": {"records": len(selected["records"]), "relations": len(selected["relations"]),
                             "target": "R4R009", "three_direct_inherited_conditions": sorted(expected),
                             "all_pinned_condition_references_present": True},
        "exact_restore": {"bytes": restore_report["bytes"], "sha256": restore_report["sha256"]},
        "input_unchanged": True,
    }

    if args.aoci:
        aoci_adapter = core._adapter("aoci")
        paths = aoci_adapter.collect_paths(args.aoci)
        original = {path: (args.aoci / path).read_bytes() for path in paths}
        aoci_output = run / "aoci"
        aoci_import = core.import_bundle(args.aoci, aoci_output, "acceptance:aoci-real", "aoci")
        assert aoci_import["status"] == "passed", aoci_import
        aoci_validation = core.validate_bundle(aoci_output)
        assert aoci_validation["status"] == "passed", aoci_validation
        restored_aoci = run / "restored_aoci.zip"
        core.restore(aoci_output, restored_aoci)
        with ZipFile(restored_aoci) as z:
            restored_files = {name: z.read(name) for name in z.namelist() if not name.endswith("/")}
        assert restored_files == original
        assert all((args.aoci / path).read_bytes() == data for path, data in original.items())
        report["aoci"] = {
            "input_files": {path: {"bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                            for path, data in original.items()},
            "import": aoci_import, "validation": aoci_validation,
            "all_native_file_bytes_restored": True, "inputs_unchanged": True,
        }

    final_hash = digest(core_path)
    report["core_sha256_after"] = final_hash
    report["status"] = "passed" if final_hash == source_hash_before else "source_changed"
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if final_hash != source_hash_before:
        raise RuntimeError("Core changed while running; repeat against the final core")


if __name__ == "__main__":
    main()
