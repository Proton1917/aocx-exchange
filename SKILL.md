---
name: aocx-exchange
description: "Prepare, import, migrate, compress, or validate context for another agent using AOCX. Use for explicit context handoffs, research or project archives, AOCI/GBCX compatibility, and BabelTele-style language views. Includes executable checks and preserves free-form exploratory content."
---

# AOCX Exchange

Use `scripts/aocx.py` as the executable core. Load a reference only for the operation at hand. Keep existing AOCI MCP tools as the software cognition service.

## Workflow

1. Identify the source, intended reader, task scope, and requested fidelity. Preserve existing artifacts as inputs; write conversions to new directories.
2. Preserve exploratory ideas in arbitrary `text` or `body`. Give each record `id`, `rev`, `kind`, and `text`. Add conditions, scope, evidence, quantities, and relations when relevant. Keep new domain kinds and unknown fields.
3. Choose the operation:

```bash
python3 scripts/aocx.py create --records records.jsonl --relations relations.jsonl --out exchange --namespace project-name
python3 scripts/aocx.py import-aoci path/to/cognition exchange --namespace project-name
python3 scripts/aocx.py import-gbcx archive.zip exchange --namespace project-name
python3 scripts/aocx.py validate exchange
python3 scripts/aocx.py capsule exchange --out context.aocx
```

4. Run `validate` after creation. Resolve hard errors in references, versions, types, paths, and file digests. Preserve uncertainty and open questions as data. Record unsupported profiles and use the exact representation when needed.
5. Generate selected context with its prerequisite closure. Preserve conditions, scope, revisions, states, and protected anchors. Use `--full` for exact JSON-value recovery. Treat a handoff view as a declared projection.
6. For a BabelTele-style view, retain the exact source and run `check-view`. Report structural validation and reader-task evaluation separately. Use measured reader/model/tokenizer evidence before selecting a semantic view as the sole task context.
7. Deliver the requested artifact with verification results, compatibility scope, and concrete unresolved references. Persist ordinary deliverables using the active environment's file workflow.

## References and checks

- [Core specification](references/specification.md): objects, graph, revisions, extensibility, packaging, compact encoding.
- [Profiles](references/profiles.md): AOCI/GBCX mappings, restoration, BabelTele and other codecs.
- [MCP binding](references/mcp-binding.md): existing AOCI reads, receipts and host-side projection.
- [Validation](references/validation.md): executable checks and model-level evaluation.
- [Research](references/research.md): primary papers, repositories and design decisions.

Schemas and authored examples are in `assets/`. Run implementation checks with:

```bash
python3 -m unittest discover -s scripts/tests -v
```

Keep workflow progress distinct from claim status. Validate declared data contracts; evaluate domain conclusions through their evidence. Preserve native AOCI receipts and governance through the original AOCI workflow.
