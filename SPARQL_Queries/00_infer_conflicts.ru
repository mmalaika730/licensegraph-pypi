# 00_infer_conflicts.ru  (SPARQL Update)
# RUN THIS ONCE after loading the ontology and instances, BEFORE Q10 and Q11.
#
# Rule: a project conflicts with a dependency license when a CompatibilityRule
# links the category of the project's license to the category of the
# dependency's license with a verdict other than Compatible.
#
#   Explicit facts : myproj hasLicense MIT          ; myproj directlyDependsOn+ X
#                    X hasLicense GPL-3.0-only
#   Schema/rule    : GPL-3.0-only is a StrongCopyleftLicense, MIT a PermissiveLicense
#                    rule:R1 (Permissive project, StrongCopyleft dependency) = Incompatible
#   Inferred fact  : a lg:LicenseConflict for (myproj, X, GPL-3.0-only, rule:R1)
#
# Notes
#  * Uses  directlyDependsOn+  and  a/rdfs:subClassOf*  on purpose, so it gives the same
#    result in GraphDB with OWL2-RL on or off.
#  * The NOT EXISTS block keeps only the most specific rule. Without it, AGPL
#    (a StrongCopyleft) would match both the StrongCopyleft rule and the
#    NetworkCopyleft rule and be reported twice.
#  * The conflict IRI is built from a hash, so running this twice does not
#    create duplicates.

PREFIX lg:   <http://example.org/licensegraph#>
PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>

INSERT {
  ?conflict a lg:LicenseConflict ;
            lg:conflictProject    ?proj ;
            lg:conflictDependency ?dep ;
            lg:conflictLicense    ?depLic ;
            lg:conflictRule       ?rule ;
            lg:conflictVerdict    ?verdict .
}
WHERE {
  ?proj a lg:Project ;
        lg:hasLicense ?projLic ;
        lg:directlyDependsOn+ ?dep .
  ?dep lg:hasLicense ?depLic .

  ?rule a lg:CompatibilityRule ;
        lg:projectCategory    ?pc ;
        lg:dependencyCategory ?dc ;
        lg:verdict            ?verdict .
  FILTER(?verdict != lg:Compatible)

  ?projLic a/rdfs:subClassOf* ?pc .
  ?depLic  a/rdfs:subClassOf* ?dc .

  # keep only the most specific matching dependency category
  FILTER NOT EXISTS {
    ?rule2 a lg:CompatibilityRule ;
           lg:projectCategory    ?pc2 ;
           lg:dependencyCategory ?dc2 ;
           lg:verdict            ?verdict2 .
    FILTER(?verdict2 != lg:Compatible)
    ?projLic a/rdfs:subClassOf* ?pc2 .
    ?depLic  a/rdfs:subClassOf* ?dc2 .
    ?dc2 rdfs:subClassOf+ ?dc .
    # reasoners make subClassOf reflexive (C subClassOf C), so exclude the rule's own category
    FILTER(?dc2 != ?dc)
  }

  BIND(IRI(CONCAT("http://example.org/licensegraph/conflict/",
                  MD5(CONCAT(STR(?proj), "|", STR(?dep), "|", STR(?depLic), "|", STR(?rule))))) AS ?conflict)
}
