# R01 | Conflict inference rule (SPARQL Update)
#
# Schema knowledge (the CompatibilityRule individuals in the ontology) + explicit facts
# (project license, dependency edges, dependency licenses) => inferred LicenseConflict
# individuals that nobody stored directly.
#
# Run ONCE after loading the ontology and instances.ttl (GraphDB: SPARQL > Update tab).
# Safe to re-run: the conflict IRI is derived from an MD5 of its parts, so a second run
# adds nothing new.
#
# Category matching uses  a/rdfs:subClassOf*  so a rule written for StrongCopyleftLicense also
# matches AGPL (a NetworkCopyleftLicense). Rules whose verdict is Compatible are ignored.
#
# Note: the rule links EVERY parsed license id. A dual-licensed "MIT OR GPL-2.0-only"
# dependency therefore produces a conflict; Q10 shows a dual-license warning next to it.

PREFIX lg:   <http://example.org/licensegraph#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

INSERT {
  ?conflict a lg:LicenseConflict ;
            lg:conflictProject    ?project ;
            lg:conflictDependency ?dep ;
            lg:conflictLicense    ?depLicense ;
            lg:conflictRule       ?rule ;
            lg:conflictVerdict    ?verdict .
}
WHERE {
  ?project a lg:Project ;
           lg:hasLicense ?projectLicense ;
           lg:directlyDependsOn+ ?dep .
  ?dep lg:hasLicense ?depLicense .

  ?projectLicense a/rdfs:subClassOf* ?projectCategory .
  ?depLicense     a/rdfs:subClassOf* ?dependencyCategory .

  ?rule a lg:CompatibilityRule ;
        lg:projectCategory    ?projectCategory ;
        lg:dependencyCategory ?dependencyCategory ;
        lg:verdict            ?verdict .
  FILTER (?verdict != lg:Compatible)

  BIND (IRI(CONCAT("http://example.org/licensegraph/conflict/",
                   MD5(CONCAT(STR(?project), "|", STR(?dep), "|", STR(?rule), "|", STR(?depLicense))))) AS ?conflict)
}
