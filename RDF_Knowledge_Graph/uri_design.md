# URI Design: LicenseGraph-PyPI

## Namespaces

| Prefix | Namespace | Holds |
|--------|-----------|-------|
| `lg:` | `http://example.org/licensegraph#` | Vocabulary: classes and properties (T-Box) |
| `pkg:` | `http://example.org/licensegraph/pkg/` | Packages (name only) |
| `ver:` | `http://example.org/licensegraph/ver/` | Package versions |
| `lic:` / `license:` | `http://example.org/licensegraph/license/` | Licenses |
| `project:` | `http://example.org/licensegraph/project/` | The user's own project |
| `rule:` | `http://example.org/licensegraph/rule/` | Compatibility rules |

`example.org` is a placeholder. To change the base, edit the prefixes at the top of the ontology and `BASE` / `LG` in `build_kg.py`; keep them identical in both places.
The ontology file writes the license prefix as `lic:` and the generated data writes it as `license:`. Both expand to the same IRIs, so the two files line up.

## Patterns

| Thing | Pattern | Example |
|-------|---------|---------|
| Package | `pkg/{normalised-name}` | `.../pkg/flask` |
| Package version | `ver/{normalised-name}/{version}` | `.../ver/flask/3.0.0` |
| License | `license/{spdx-id}` | `.../license/Apache-2.0` |
| Project | `project/{normalised-name}` | `.../project/acme-mit-app` |
| Rule | `rule/R{n}` | `.../rule/R1` |
| Vocabulary term | `lg#{Term}` | `lg#directlyDependsOn` |

## Decisions and reasons

1. **Package and package version are separate resources.** deps.dev records licenses and dependencies per version, and the same package can have different licenses or children in different versions. A conflict chain such as `app -> A 2.1 -> B 0.9 -> C 3.0 (GPL)` is only exact if each hop is a specific version. `pkg:` carries the name and links to its versions with `lg:hasVersion`; everything else attaches to `ver:`.
2. **Readable, not opaque.** URIs contain the real names and versions, so GraphDB's visual graph, the SPARQL results and the LLM's cited entities are understandable without a lookup.
3. **Hash for the vocabulary, slash for the data.** The vocabulary is small and read as one file. The instance data is large and each resource is addressed on its own.
4. **Names are normalised (PEP 503).** Lower-case, and any run of `-`, `_` or `.` becomes one `-`, so `Flask`, `flask` and `Typing_Extensions` / `typing-extensions` cannot create duplicate nodes. `build_kg.py` applies this to every name, including in the edge file and the projects file.
5. **Only URI-safe characters are kept.** Letters, digits and `- . _ ~` stay; everything else is percent-encoded. Example: `1.0+local` becomes `1.0%2Blocal`, `GPL-2.0+` becomes `GPL-2.0%2B`.
6. **Licenses use the SPDX identifier as-is.** Values that are not SPDX ids keep their literal text under the same path (`license/non-standard`, `license/NOASSERTION`, `license/LicenseRef-Proprietary`) and are typed `UnknownLicense` or `ProprietaryLicense` through `Dataset/curated/license_categories.csv`.
7. **No version or date inside package or license URIs.** The name identifies the package, and the version path segment identifies a release, so URIs stay stable between extractions.

## What the generated data looks like

```turtle
<http://example.org/licensegraph/ver/demo-http/2.1.0> a lg:PackageVersion ;
    lg:hasLicense license:Apache-2.0 ;
    lg:directlyDependsOn <http://example.org/licensegraph/ver/demo-parse/0.9.3> ;
    lg:versionString "2.1.0" ;
    lg:isSeedRoot false ;
    lg:hasMultipleDeclaredLicenses false ;
    lg:declaredLicenseString "Apache-2.0" .

license:GPL-3.0-only a lg:StrongCopyleftLicense ;
    rdfs:label "GNU General Public License v3.0 only" ;
    lg:spdxId "GPL-3.0-only" ;
    lg:isOsiApproved true ;
    lg:isFsfLibre true .
```

(From the synthetic test fixture, not real deps.dev data.) Version URIs appear in full `<...>` form because a version path segment cannot be written as a Turtle prefixed name. They are ordinary IRIs.

## Not done yet

- Links to external identifiers (`rdfs:seeAlso <https://spdx.org/licenses/MIT.html>`, a Package URL literal such as `pkg:pypi/flask@3.0.0`) would make the graph linkable to outside data. Easy to add once the real extract exists.
