---
id: library:pydantic
title: pydantic
state: specified
confidence: reviewed
owner: vfeenstr
package: pydantic
ecosystem: pypi
version_range: '>=2.13.4'
license: MIT
replaceable: false
---

Not replaceable: the records are the one source of the schema, and both the
validator and the generated JSON Schema are pydantic's own — see
`decision:pydantic-single-schema-source` and `rejection:msgspec-model-dir`.
