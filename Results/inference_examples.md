# Inference examples (Explicit facts -> Rule/Schema knowledge -> Inferred fact)

Computed on the real graph: 2756 stored triples (schema + rules + data); 6395 after OWL 2 RL reasoning; conflict rule R01 applied on top.

Each example was verified by script: explicit facts are in the stored graph, the inferred triple is **absent** from the stored graph and **present** after reasoning.

## Example 1: Transitive dependency (transitive property + subproperty)

**Explicit facts (stored)**

- `project:acme-mit-app lg:directlyDependsOn ver:beets/2.14.1`
- `ver:beets/2.14.1 lg:directlyDependsOn ver:mediafile/0.17.0`
- `ver:mediafile/0.17.0 lg:directlyDependsOn ver:mutagen/1.48.1`

**Rule / schema knowledge**

- `lg:directlyDependsOn rdfs:subPropertyOf lg:dependsOn`
- `lg:dependsOn a owl:TransitiveProperty`

**Inferred fact (never stored)**

- `project:acme-mit-app lg:dependsOn ver:mutagen/1.48.1`

Check: explicit facts stored = True; inferred triple stored = False; inferred after reasoning = True

## Example 2: License category (subclass reasoning)

**Explicit facts (stored)**

- `license:GPL-2.0-or-later rdf:type lg:StrongCopyleftLicense`

**Rule / schema knowledge**

- `lg:StrongCopyleftLicense rdfs:subClassOf lg:CopyleftLicense`

**Inferred fact (never stored)**

- `license:GPL-2.0-or-later rdf:type lg:CopyleftLicense`

Check: explicit facts stored = True; inferred triple stored = False; inferred after reasoning = True

## Example 3: License anywhere in the tree (property chain)

**Explicit facts (stored)**

- `project:acme-mit-app lg:directlyDependsOn ver:beets/2.14.1`
- `ver:beets/2.14.1 lg:directlyDependsOn ver:mediafile/0.17.0`
- `ver:mediafile/0.17.0 lg:directlyDependsOn ver:mutagen/1.48.1`
- `ver:mutagen/1.48.1 lg:hasLicense license:GPL-2.0-or-later`

**Rule / schema knowledge**

- `lg:treeContainsLicense owl:propertyChainAxiom ( lg:dependsOn lg:hasLicense )`
- `lg:dependsOn a owl:TransitiveProperty`; `lg:directlyDependsOn rdfs:subPropertyOf lg:dependsOn`

**Inferred fact (never stored)**

- `project:acme-mit-app lg:treeContainsLicense license:GPL-2.0-or-later`

Check: explicit facts stored = True; inferred triple stored = False; inferred after reasoning = True

## Example 4: License conflict (curated compatibility rule + rule R01)

**Explicit facts (stored)**

- `project:acme-mit-app lg:directlyDependsOn ver:beets/2.14.1`
- `ver:beets/2.14.1 lg:directlyDependsOn ver:mediafile/0.17.0`
- `ver:mediafile/0.17.0 lg:directlyDependsOn ver:mutagen/1.48.1`
- `project:acme-mit-app lg:hasLicense license:MIT`
- `ver:mutagen/1.48.1 lg:hasLicense license:GPL-2.0-or-later`
- `license:MIT rdf:type lg:PermissiveLicense`
- `license:GPL-2.0-or-later rdf:type lg:StrongCopyleftLicense`

**Rule / schema knowledge**

- `rule:R1 lg:projectCategory lg:PermissiveLicense ; lg:dependencyCategory lg:StrongCopyleftLicense ; lg:verdict lg:Incompatible`
- Rule file `00_infer_conflicts.ru` (INSERT ... WHERE with `lg:dependsOn`-style path and `a/rdfs:subClassOf*`)

**Inferred fact (never stored)**

- `http://example.org/licensegraph/conflict/1ae194d6c16a226a5a6c2e9f90ac1df6 rdf:type lg:LicenseConflict`

  - rule: `rule:R1`, verdict: `lg:Incompatible`, dependency: `ver:mutagen/1.48.1`

Check: explicit facts stored = True; inferred triple stored = False; inferred after reasoning = True
