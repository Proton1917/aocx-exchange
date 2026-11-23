# Formal context compilation

This example carries an authored domain expression, its Chinese and English
source text, pinned prerequisites, revision history, and open-ended research
content through the same compilation contract.

```text
P' = zh(S[x="GenshinImpact"]⊢x∈{y|SelfDev(Dev(x),y)∧OpenAdvGame(y)})
```

`logic.json` stores the expression as an `aocx-logic/1` AST. The author supplies
the meanings of `S`, `Dev`, `SelfDev`, `OpenAdvGame`, and the `zh` presentation
annotation. The parser records their structure, ordered arguments, explicit
binding and set-builder variable. The expression codec renders that structure
and parses it back to the same typed value. The vocabulary record states the
interpretation and its scope.

## Run the complete example

From the repository root:

```sh
python3 assets/examples/compile_example.py --out /tmp/aocx-formal
```

The script creates a source archive in a temporary directory, compiles exact
and projected representations, and verifies both against their caller-supplied
contracts. It then removes the temporary source and recovers both contexts
from the representation bytes alone. The resulting example directory includes
the source archive and its original attachment as separately stored files.
The script requires only the Python standard library.

Running the script without `--out` checks and reproduces this committed example.
Existing generated files must match the newly calculated bytes. A different
result requires an empty output directory for inspection.

## Artifacts and guarantees

| Artifact | Contents |
| --- | --- |
| `source/` | AOCX archive with records, directed relations, revision heads and original UTF-8 attachment |
| `context.aocxrep` | The smallest verified default candidate for the exact context contract |
| `context.json` | Independently recovered exact logical context |
| `projection.aocxrep` | The smallest verified default candidate for the declared projection |
| `projection.json` | Independently recovered selected records and their prerequisite closure |
| `logic.json` | Domain-authored logic wrapper and AST |
| `expression.txt` | Authored expression and deterministic rendered expression |
| `verification.json` | Candidate costs, source verification, independent recovery and attachment digest |

The exact representation preserves all record revisions, relation direction,
heads, profile declarations, manifest metadata, Unicode text, unknown record
and relation fields, nulls, booleans and numeric values. The codec search measures
the entire wire frame, including the header, recovery data and any dictionary.
Its optimum covers the offered, verified, decoder-compatible candidates.

The projection selects `formal/claim@1`, follows its condition to
`formal/premise@1`, and follows that premise to `formal/vocabulary@1`. The
archive's current premise is revision `2`. The projection retains revision `1`
as a historical prerequisite and keeps the current-head map accurate.
Its contract explicitly omits `body` and `extensions`; the top-level `logic`
and `future.domain` fields remain preserved. The speculative idea retains its
declared knowledge state in the exact context.

Recovery covers the declared logical context values. Attachment bytes remain
available in `source/attachments/source.txt`, with their byte count and digest
in the archive manifest. The source attachment and its archive metadata have
their own storage contract. The verification report establishes preservation
of the authored values; factual assessment of the game taxonomy and any
reader-task comprehension experiment require their own evidence.

The decoded representation envelopes validate against
`assets/schemas/representation.schema.json`. The logic wrapper validates against
`assets/schemas/logic.schema.json`. The executable verifier additionally checks
hash binding, pinned references, projection closure and typed value equality.
