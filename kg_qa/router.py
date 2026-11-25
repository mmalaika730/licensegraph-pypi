"""
router.py | turns a natural-language question into (1) the entities it mentions and (2) a retrieval intent.

No LLM is involved here on purpose: entity linking is exact matching against names stored in the graph, and the intent is
chosen with transparent keyword rules, so every routing decision can be explained and tested. The limitation is that questions
phrased in ways the rules do not cover are answered with "insufficient evidence" instead of being guessed.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from rdflib import URIRef

from .kg import KG, LG, LIC, norm_name

# package names that are also ordinary English words: only linked when marked as a package ("package click", `click`, "click")
AMBIGUOUS = {"click", "black", "six", "requests", "decorator", "outcome", "deprecated", "constantly", "incremental",
             "packaging", "filetype", "babel", "wrapt", "vine", "invoke", "fabric", "redis", "docker", "attrs", "trio",
             "setuptools", "unidecode", "lap", "brotli", "confuse", "protego", "twisted", "blinker", "cycler", "pytokens"}

LICENSE_ALIASES = {  # phrase -> lower-case spdx id stored in the graph
    "apache 2.0": "apache-2.0", "apache 2": "apache-2.0", "apache license 2.0": "apache-2.0", "apache2": "apache-2.0",
    "mit license": "mit", "3-clause bsd": "bsd-3-clause", "bsd 3-clause": "bsd-3-clause", "2-clause bsd": "bsd-2-clause",
    "mozilla public license 2.0": "mpl-2.0", "mpl 2.0": "mpl-2.0", "gplv3": "gpl-3.0-or-later", "gpl v3": "gpl-3.0-or-later",
    "gpl 3": "gpl-3.0-or-later", "gplv2": "gpl-2.0-or-later", "gpl v2": "gpl-2.0-or-later", "gpl 2": "gpl-2.0-or-later",
}
CATEGORY_WORDS = [  # (regex, category class); more specific first
    (r"\bnetwork[- ]copyleft\b|\bagpl\b", "NetworkCopyleftLicense"),
    (r"\bstrong[- ]copyleft\b|\bgpl\b", "StrongCopyleftLicense"),
    (r"\bweak[- ]copyleft\b|\blgpl\b", "WeakCopyleftLicense"),
    (r"\bpermissive\b", "PermissiveLicense"),
    (r"\bproprietary\b|\bclosed[- ]source\b|\bcommercial\b", "ProprietaryLicense"),
    (r"\bcopyleft\b", "CopyleftLicense"),
]


@dataclass
class Entities:
    projects: list = field(default_factory=list)     # [(surface text, IRI)]
    packages: list = field(default_factory=list)     # [(surface text, [version IRIs])]
    licenses: list = field(default_factory=list)     # [(surface text, IRI)]
    categories: list = field(default_factory=list)   # [category class local names]
    unknown_packages: list = field(default_factory=list)  # names that look like packages but are not in the graph
    unmatched_versions: list = field(default_factory=list)  # (package, requested version) when the graph has other versions

    def nodes(self):
        out = [iri for _, iri in self.projects]
        for _, vs in self.packages:
            out.extend(vs)
        return out


def _find(q: str, phrase: str) -> bool:
    return re.search(r"(?<![\w-])" + re.escape(phrase) + r"(?![\w-])", q) is not None


def link_entities(kg: KG, question: str) -> Entities:
    q = question.lower()
    ent = Entities()
    taken = []                                           # character spans already linked, longest names first

    def free(span):
        return all(span[1] <= a or span[0] >= b for a, b in taken)

    for name, iri in sorted(kg.projects.items(), key=lambda kv: -len(kv[0])):
        for m in re.finditer(r"(?<![\w-])" + re.escape(name).replace(r"\-", r"[-_ ]") + r"(?![\w-])", q):
            if free(m.span()):
                taken.append(m.span())
                ent.projects.append((name, iri))
                break
    for name, versions in sorted(kg.packages.items(), key=lambda kv: -len(kv[0])):
        pat = re.escape(name).replace(r"\-", r"[-_ ]")
        for m in re.finditer(r"(?<![\w-])" + pat + r"(?![\w-])", q):
            if not free(m.span()):
                continue
            if name in AMBIGUOUS:
                before, after = q[max(0, m.start() - 12):m.start()], q[m.end():m.end() + 10]
                marked = before.rstrip().endswith(("package", "library", "module", "`", '"', "'")) or after.lstrip().startswith(("package", "library", "`", '"', "'", "==", "/", "1", "2", "3", "4", "5", "6", "7", "8", "9"))
                if not marked:
                    continue
            taken.append(m.span())
            # explicit version, e.g. "beets 2.14.1" or "beets/2.14.1"
            vm = re.match(r"[\s/=]*v?(\d+(?:\.\d+)+\w*)", q[m.end():])
            chosen = versions
            if vm:
                hit = [v for v in versions if str(v).endswith("/" + vm.group(1))]
                if hit:
                    chosen = hit
                else:
                    ent.unmatched_versions.append((name, vm.group(1), [str(v).rsplit("/", 1)[-1] for v in versions]))
            ent.packages.append((name, list(chosen)))
            break
    for alias, sid in LICENSE_ALIASES.items():
        m = re.search(r"(?<![\w-])" + re.escape(alias) + r"(?![\w-])", q)
        if m and free(m.span()) and sid in kg.licenses:
            taken.append(m.span())
            ent.licenses.append((alias, kg.licenses[sid]))
    for sid, iri in sorted(kg.licenses.items(), key=lambda kv: -len(kv[0])):
        m = re.search(r"(?<![\w-])" + re.escape(sid) + r"(?![\w-])", q)
        if m and free(m.span()):
            taken.append(m.span())
            ent.licenses.append((sid, iri))
    ent.licenses.sort(key=lambda x: q.find(x[0]))
    # licence family words that were not matched to a specific licence id
    for rx, cat in CATEGORY_WORDS:
        m = re.search(rx, q)
        if m and free(m.span()):
            taken.append(m.span())
            ent.categories.append(cat)
    # unknown package-like names after cue words, so "does django-foo have conflicts" is answered "not in the graph"
    known = {n for n in kg.packages} | set(kg.projects)
    for m in re.finditer(r"(?:package|library|module|project|does|of|on|for)\s+[`\"']?([a-z][a-z0-9_.-]{2,})[`\"']?", q):
        cand = norm_name(m.group(1))
        if cand not in known and cand not in STOPWORDS and not any(cand == norm_name(s) for s, _ in ent.licenses) \
                and cand not in {l for l in kg.licenses}:
            ent.unknown_packages.append(cand)
    return ent


STOPWORDS = set("""the a an this that these those it its any all each every my our your their which what who whom whose how why when where
there here have has had does do did is are was were be been being can could should would will may might must shall
license licenses licence licensed licensing package packages project projects dependency dependencies dependent dependents
tree trees graph copyleft permissive proprietary conflict conflicts compatible incompatible direct directly transitive transitively
version versions chain chains hops depth below under with without from into than then also only more most less least many much
using used use uses user users depend depends depending ship shipping release released open source code library libraries
module modules and for not are one two three four five six seven eight nine ten first last next other another same different
mit gpl lgpl agpl mpl bsd apache osi approved common frequent often top number count size large""".split())

# ------------------------------------------------------------------------------------------------ intents
INTENT_RULES = [  # (intent, regex over the lower-cased question), first match wins
    ("graph_stats", r"how many (?:package|version|license|dependenc|project|triple|edge|fact)\w*(?: \w+){0,3} (?:are |does |is )?(?:there )?(?:in|does|stored in|contained in) (?:the |this |our )?(?:graph|kg|knowledge graph|database)|size of the (?:graph|knowledge graph)"),
    ("firm_vs_avoidable", r"\bavoidable\b|\bfirm\b|dual[- ]licen|choos\w+ (?:another|a different|the other) (?:option|licen)|\bavoid\w* (?:the )?conflict"),
    ("predict_license", r"\bpredict|\bguess|likely licen|licen\w+ (?:is|would be) (?:likely|probably)|suggest\w* (?:a )?licen"),
    ("deep_copyleft", r"\b(?:3|three|4|four|5|five) (?:or more )?(?:hops|levels|steps)\b|depth (?:of )?(?:3|three) |at least (?:3|three) |deeply nested|\bdeep copyleft\b|(?:3|three) or more"),
    ("license_pair", r"\bcompatible with\b|\bmix\b.*\blicen|\bcombine\b|\bcan (?:a|an|the)\b.*\b(?:project|app|application|software)\b.*\b(?:use|depend|include|link)"),
    ("compatibility", r"\bcompatible\b|\bsafe to (?:ship|release|use)|\bcan (?:we|i) (?:ship|release|distribute|publish)|\bis it (?:ok|okay|fine|allowed)\b|\bany (?:problem|issue)s?\b|\bfully\b"),
    ("conflicts", r"conflict|incompatib|violat|\brisk|\bflagged\b|\bwhy is\b.*\b(?:flag|problem)|which rule|\bproblem\b"),
    ("non_osi", r"\bosi\b|not approved|unapproved|non-standard|non standard|\bunknown licen|\bunrecognis"),
    ("direct_deps", r"direct(?:ly)? dependenc|\bdepend\w*\b.*\bdirect(?:ly)?\b|\bdirect(?:ly)?\b.*\bdepend|\bdirect\b"),
    ("dependency_chains", r"\bchain|\bpath\b|\bhow does\b.*\b(?:depend|reach|end up|get)|\bthrough which|\bvia which|\bintroduc"),
    ("dependents", r"\bwho (?:depends|uses|relies)\b|\bwhich (?:projects?|packages?|versions?)(?: and (?:projects?|packages?))? (?:that )?(?:depend|rely|use)\w*\b|\bexposed\b|\bdependents?\b|\breach(?:es|ed)? |\bpulls? in\b|\baffected by\b"),
    ("tree_size", r"how many (?:transitive|indirect|total|packages|dependencies)|\bsize of\b|how large|how big|tree size|number of (?:transitive|indirect|total)"),
    ("copyleft_chains", r"copyleft|\bgpl\b|\bgplv|\blgpl\b|\bagpl\b|\bmpl\b"),
    ("tree_licenses", r"licen\w+.*\b(?:tree|anywhere|below|transitive|indirect|all)\b|\b(?:tree|transitive|indirect)\b.*licen"),
    ("direct_deps", r"\bwhat does\b.*\bdepend|\bdependencies of\b|\bdepends? on\b"),
    ("license_of", r"what licen|which licen|licen\w+ (?:of|does|is|for)|licensed under|\bunder which licen|\bwhat is the licen"),
    ("license_frequency", r"most (?:common|frequent|popular|used)|\bfrequen|how many .*(?:use|under)|\bpopular"),
]
NEEDS = {"license_of": "node", "direct_deps": "node", "tree_licenses": "node", "copyleft_chains": "node", "dependency_chains": "node+target",
         "dependents": "target", "deep_copyleft": "none", "conflicts": "project", "compatibility": "project", "firm_vs_avoidable": "project",
         "license_frequency": "none", "non_osi": "none", "graph_stats": "none", "tree_size": "node", "predict_license": "node", "license_pair": "licenses"}


@dataclass
class Route:
    intent: str | None
    entities: Entities
    status: str = "ok"            # ok | no_intent | missing_entity | unknown_entity
    reason: str = ""
    nodes: list = field(default_factory=list)
    targets: list = field(default_factory=list)


def route(kg: KG, question: str) -> Route:
    ent = link_entities(kg, question)
    q = question.lower()
    intent = next((i for i, rx in INTENT_RULES if re.search(rx, q)), None)
    # a dependency-chain question names two packages/projects; "who depends on X" names the target
    names = len(ent.projects) + len(ent.packages)
    if intent == "copyleft_chains" and re.search(r"\bwho\b|\bwhich (?:projects?|packages?) .*(?:depend|use)", q) and names:
        intent = "dependents"
    if intent == "dependency_chains" and names < 2 and ent.projects == [] and names == 1:
        intent = "dependents" if re.search(r"\bwho\b|\bwhich\b", q) else "dependency_chains"
    if intent == "conflicts" and not ent.projects and re.search(r"\bwhy\b", q) and ent.packages:
        intent = "dependents"
    if intent is None:
        return Route(None, ent, "no_intent", "The question does not match any of the question types this graph can answer.")
    need = NEEDS[intent]
    if intent == "license_pair" and len(ent.licenses) + len(ent.categories) < 2:
        intent = "compatibility" if ent.projects else None
        if intent is None:
            return Route(None, ent, "missing_entity", "A compatibility question needs two licenses or license families (for example MIT and GPL-3.0-or-later).")
        need = NEEDS[intent]
    r = Route(intent, ent)
    if ent.unmatched_versions and need in ("node", "node+target", "target", "project"):
        pkg, asked, have = ent.unmatched_versions[0]
        r.status = "unknown_entity"
        r.reason = f"The graph does not contain {pkg} version {asked}; it only holds {pkg} {', '.join(have)}."
        return r
    if need == "project":
        if not ent.projects:
            if ent.packages:                       # accept a package version as the "project" being audited
                r.nodes = ent.nodes()
                return r
            return _missing(r, ent, "a project from the graph (for example acme-mit-app)")
        r.nodes = [i for _, i in ent.projects]
    elif need == "node":
        if not ent.nodes():
            return _missing(r, ent, "a package or project from the graph")
        r.nodes = ent.nodes()
    elif need == "target":
        if not ent.packages:
            return _missing(r, ent, "the package whose dependents you want (for example mutagen)")
        r.targets = [vs for _, vs in ent.packages]
    elif need == "node+target":
        if names < 2:
            return _missing(r, ent, "two entities: where the chain starts (a project or package) and the package it should reach")
        starts = [i for _, i in ent.projects] or None
        if starts:
            r.nodes, r.targets = starts, [vs for _, vs in ent.packages]
        else:
            r.nodes, r.targets = list(ent.packages[0][1]), [vs for _, vs in ent.packages[1:]]
    return r


def _missing(r: Route, ent: Entities, what: str) -> Route:
    r.status = "unknown_entity" if ent.unknown_packages else "missing_entity"
    if ent.unknown_packages:
        r.reason = f"'{ent.unknown_packages[0]}' is not in the knowledge graph. The question needs {what}."
    else:
        r.reason = f"The question needs {what}, but none was recognised in it."
    return r
