"""Focused GBCX projection checks; optionally pass an original GBCX ZIP."""

from pathlib import Path
from zipfile import ZipFile
import hashlib
import importlib.util
import json
import sys


def load_adapter():
    here = Path(__file__).resolve()
    for parent in here.parents:
        for relative in ("adapters/gbcx.py", "scripts/adapters/gbcx.py"):
            path = parent / relative
            if path.is_file():
                spec = importlib.util.spec_from_file_location("gbcx_projection", path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module
    raise RuntimeError("Cannot locate the GBCX adapter")


def check_fixture(adapter):
    folder = Path(__file__).resolve().parent
    files = {p.relative_to(folder).as_posix(): p.read_bytes()
             for p in folder.rglob("*") if p.is_file()}
    result = adapter.project(files)
    assert len(result["records"]) == 8 and not result["warnings"]
    records = {r["id"]: r for r in result["records"]}
    assert records["C1"]["state"]["knowledge"] == "derived"
    assert records["C2"]["state"]["knowledge"] == "reported"
    assert records["C3"]["state"]["knowledge"] == "observed"
    assert records["C1"]["body"] == json.loads(files["claims.jsonl"].splitlines()[0])
    assert records["C1"]["conditions"][:2] == [
        {"text": x} for x in records["C1"]["body"]["assumptions"]]
    assert records["C1"]["conditions"][2]["ref"] == {"id": "C2", "rev": "1"}
    deps = [e for e in result["relations"] if e["kind"] == "depends_on"
            and e["from"]["id"] == "C1" and e["to"]["id"] == "C2"]
    assert len(deps) == 1 and deps[0]["body"]["condition_bearing"]
    assert len(deps[0]["body"]["legacy_origins"]) == 2
    assert records["M1"]["body"]["state"] == "tried_failed"
    assert records["M1"]["state"]["method_use"] == "tried_failed"
    assert records["M1"]["scope"] == "Only this kernel and bound."
    assert records["M1"]["anchors"][0]["next_test"] == records["M1"]["body"]["next_test"]
    assert records["D1"]["anchors"][0]["symbol"] == "N"
    assert records["S1"]["anchors"][0]["url"] == "https://example.invalid/lemma"
    assert records["Q1"]["anchors"][0]["missing"] == "Uniform H"
    method_edges = [e for e in result["relations"] if e["from"]["id"] == "M1"]
    assert len(method_edges) == 1
    assert method_edges[0]["kind"] == "relates_to"
    assert method_edges[0]["body"]["native_field"] == "claim_ids"
    conditional_files = dict(files)
    conditional_rows = [json.loads(raw) for raw in files["claims.jsonl"].splitlines()]
    conditional_rows[0]["assumptions"] = []
    conditional_rows[0]["condition_bearing_dependencies"] = []
    conditional_files["claims.jsonl"] = ("\n".join(json.dumps(r) for r in conditional_rows) + "\n").encode()
    conditional_result = adapter.project(conditional_files)
    conditional_record = next(r for r in conditional_result["records"] if r["id"] == "C1")
    assert conditional_record["conditions"] == [
        {"text": "Legacy conditional claim; hypotheses unspecified in source"}]
    assert any("conditional claim has no listed assumptions" in w
               for w in conditional_result["warnings"])
    for bad_line in (b'{"id":"X","id":"Y"}',
                     b'{"id":"X","assumptions":[1]}',
                     b'{"id":"X","future":NaN}'):
        bad = dict(files, **{"claims.jsonl": bad_line + b"\n"})
        try:
            adapter.project(bad)
        except ValueError:
            pass
        else:
            raise AssertionError("Malformed JSON/assumptions accepted")
    duplicate = dict(files)
    duplicate["claims.jsonl"] += files["claims.jsonl"].splitlines()[0] + b"\n"
    try:
        adapter.project(duplicate)
    except ValueError:
        pass
    else:
        raise AssertionError("Duplicate record ID accepted")
    return {"synthetic_records": 8, "synthetic_relations": len(result["relations"])}


def check_real(adapter, archive):
    archive = Path(archive)
    before = hashlib.sha256(archive.read_bytes()).hexdigest()
    with ZipFile(archive) as z:
        candidates = [n for n in z.namelist() if n.endswith("PROTOCOL.json")]
        assert len(candidates) == 1
        root = candidates[0][:-len("PROTOCOL.json")]
        files = {n[len(root):]: z.read(n) for n in z.namelist()
                 if n.startswith(root) and not n.endswith("/")}
    result = adapter.project(files)
    records = {r["id"]: r for r in result["records"]}
    assert len(records) == len(result["records"])
    for path, kind in adapter.TABLES:
        for raw in files.get(path, b"").splitlines():
            old = json.loads(raw)
            new = records[old["id"]]
            assert old == new["body"]
            if kind == "claim":
                inline = new["extensions"]["gbcx"]["inline_condition_count"]
                assert new["conditions"][:inline] == [{"text": a} for a in old["assumptions"]]
                assert [c["ref"]["id"] for c in new["conditions"][inline:] if "ref" in c] == old["condition_bearing_dependencies"]
                assert new["state"]["knowledge"] != "checked"
    keys = {(r["id"], r["rev"]) for r in result["records"]}
    assert all((e[end]["id"], e[end]["rev"]) in keys
               for e in result["relations"] for end in ("from", "to"))
    assert hashlib.sha256(archive.read_bytes()).hexdigest() == before
    return {"source_sha256": before, "records": len(records),
            "relations": len(result["relations"]), "warnings": result["warnings"]}


if __name__ == "__main__":
    adapter = load_adapter()
    report = {"status": "pass", "fixture": check_fixture(adapter)}
    if len(sys.argv) > 1:
        report["real_archive"] = check_real(adapter, sys.argv[1])
    print(json.dumps(report, ensure_ascii=False, indent=2))
