These fixtures are independently authored interoperability data.

volumes/: Root/Meta/Code/Database, canonical R identities, root relocation,
bracketed filename, historical #filename duplicate, ordinary comment.
Expected active entities: model.py, #state.txt, services/queue.py,
services/[...id].jsx, database://demo/public/jobs (5 total).
Expected projected relations: 4, all relates_to; no requires edge.

legacy/: historical root, dotted tags, S1/S2 projection, unknown segment,
bare R target. Expected active entities: 2. The bare target remains a native
string with an unresolved warning; the adapter does not infer its identity.

BOM/CRLF and malformed/unsafe variants are generated in tests from these
authored bytes. This fixture package does not certify upstream AOCI runtime
governance, source binding, or semantic authoring quality.
