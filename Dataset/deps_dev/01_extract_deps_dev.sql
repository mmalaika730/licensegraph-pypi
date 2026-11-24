-- =============================================================================
-- LicenseGraph-PyPI | Extraction from the deps.dev BigQuery dataset
-- =============================================================================
-- STATUS: NOT YET RUN. Written against the schema published at
--         https://docs.deps.dev/bigquery/ (checked 3 Nov 2026). Dry-run first.
--
-- SETUP
--   1. Replace YOUR_PROJECT everywhere below with your own GCP project ID.
--   2. Create a dataset for the intermediate tables:
--        bq mk --dataset YOUR_PROJECT:licensegraph
--      (or create it in the console).
--
-- COST
--   Click "More > Query settings" and use the dry-run estimate shown by the
--   console (or `bq query --dry_run`) BEFORE running each statement.
--   Statement 2 is the large one: DependencyGraphEdgesLatest covers five
--   ecosystems. The BigQuery free tier is 1 TB of queries per month. If the
--   estimate is far above what you want to spend, the same data is served by
--   the deps.dev REST API (api.deps.dev), which needs no BigQuery at all.
--
-- DESIGN NOTES
--   * We use the "...Latest" views, so no SnapshotAt handling is needed.
--   * Edges come from DependencyGraphEdgesLatest: each row is an edge between
--     two RESOLVED package versions inside the dependency graph of a root
--     version. From/To are therefore direct requirements in a consistent graph.
--     (`From` and `To` are reserved words in BigQuery, hence the backticks.)
--   * Licenses is an array of SPDX expressions, which BigQuery cannot export
--     to CSV, so it is flattened with ';' as the separator. build_kg.py
--     splits SPDX expressions such as "MIT OR Apache-2.0" again.
--   * A package version that appears under several roots may resolve to
--     slightly different children in different roots. direct_edges keeps the
--     union; root_edges keeps the per-root detail for the validation step.
-- =============================================================================


-- -----------------------------------------------------------------------------
-- 1. Seed roots: the latest release of each seed package
-- -----------------------------------------------------------------------------
-- Seed mix: web, data, DevOps and security libraries. Several (mysqlclient,
-- pylint, ansible-core, mutagen, unidecode, paramiko, psycopg2-binary,
-- pyinstaller) are included because they are commonly reported as
-- copyleft-licensed. CONFIRM THIS FROM THE EXTRACTED DATA, not from this
-- comment. Tune the list so that statement 5 returns 100 to 200 nodes.
CREATE OR REPLACE TABLE `YOUR_PROJECT.licensegraph.seed_roots` AS
SELECT Name AS name, Version AS version
FROM `bigquery-public-data.deps_dev_v1.PackageVersionsLatest`
WHERE System = 'PYPI'
  AND VersionInfo.IsRelease
  AND Name IN (
    'requests', 'flask', 'django', 'fastapi', 'uvicorn', 'jinja2', 'click',
    'sqlalchemy', 'pydantic', 'httpx', 'celery', 'redis', 'boto3', 'pytest',
    'black', 'numpy', 'pandas', 'scipy', 'matplotlib', 'scikit-learn',
    'pillow', 'lxml', 'beautifulsoup4', 'selenium', 'openpyxl', 'pyyaml',
    'cryptography', 'paramiko', 'docker', 'psycopg2-binary', 'mysqlclient',
    'pylint', 'ansible-core', 'mutagen', 'unidecode', 'pyinstaller'
  )
QUALIFY ROW_NUMBER() OVER (PARTITION BY Name ORDER BY VersionInfo.Ordinal DESC) = 1;
-- Ordinal sorts a package's versions in the ecosystem's own order, so DESC
-- picks the latest release (pre-releases are excluded by IsRelease).


-- -----------------------------------------------------------------------------
-- 2. All edges in the resolved dependency graph of every seed root
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE `YOUR_PROJECT.licensegraph.root_edges` AS
SELECT
  s.name            AS root_name,
  s.version         AS root_version,
  e.`From`.Name     AS name,
  e.`From`.Version  AS version,
  e.`To`.Name       AS dep_name,
  e.`To`.Version    AS dep_version,
  e.Requirement     AS requirement
FROM `bigquery-public-data.deps_dev_v1.DependencyGraphEdgesLatest` AS e
JOIN `YOUR_PROJECT.licensegraph.seed_roots` AS s
  ON e.Name = s.name AND e.Version = s.version
WHERE e.System = 'PYPI'
  AND e.`From`.System = 'PYPI'
  AND e.`To`.System = 'PYPI';


-- -----------------------------------------------------------------------------
-- 3. Distinct direct edges across all roots
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE `YOUR_PROJECT.licensegraph.direct_edges` AS
SELECT DISTINCT name, version, dep_name, dep_version
FROM `YOUR_PROJECT.licensegraph.root_edges`
WHERE NOT (name = dep_name AND version = dep_version);


-- -----------------------------------------------------------------------------
-- 4. Node table with licenses (one row per resolved package version)
-- -----------------------------------------------------------------------------
CREATE OR REPLACE TABLE `YOUR_PROJECT.licensegraph.node_versions` AS
WITH nodes AS (
  SELECT name, version FROM `YOUR_PROJECT.licensegraph.direct_edges`
  UNION DISTINCT
  SELECT dep_name, dep_version FROM `YOUR_PROJECT.licensegraph.direct_edges`
  UNION DISTINCT
  SELECT name, version FROM `YOUR_PROJECT.licensegraph.seed_roots`
)
SELECT
  n.name,
  n.version,
  IFNULL(ARRAY_TO_STRING(pv.Licenses, ';'), '') AS licenses,
  s.name IS NOT NULL AS is_seed
FROM nodes AS n
LEFT JOIN `bigquery-public-data.deps_dev_v1.PackageVersionsLatest` AS pv
  ON pv.System = 'PYPI' AND pv.Name = n.name AND pv.Version = n.version
LEFT JOIN `YOUR_PROJECT.licensegraph.seed_roots` AS s
  ON s.name = n.name AND s.version = n.version;


-- -----------------------------------------------------------------------------
-- 5. SIZE CHECK: aim for 100 to 200 nodes. Add or drop seeds in statement 1
--    and rerun 1 to 4 if it is outside that range.
-- -----------------------------------------------------------------------------
SELECT
  (SELECT COUNT(*) FROM `YOUR_PROJECT.licensegraph.node_versions`) AS nodes,
  (SELECT COUNT(*) FROM `YOUR_PROJECT.licensegraph.direct_edges`)  AS edges,
  (SELECT COUNT(*) FROM `YOUR_PROJECT.licensegraph.seed_roots`)    AS seeds,
  (SELECT COUNT(*) FROM `YOUR_PROJECT.licensegraph.node_versions` WHERE licenses = '') AS nodes_without_license;


-- -----------------------------------------------------------------------------
-- 6. OPTIONAL VALIDATION (extra scan of DependenciesLatest, check the estimate)
--    For each seed root, the number of distinct nodes in its graph should
--    match the number of rows deps.dev lists as its (transitive) dependencies.
--    Small differences are worth investigating and mentioning in the report.
-- -----------------------------------------------------------------------------
WITH graph_counts AS (
  SELECT root_name, root_version,
         COUNT(DISTINCT CONCAT(dep_name, '@', dep_version)) AS graph_nodes
  FROM `YOUR_PROJECT.licensegraph.root_edges`
  GROUP BY root_name, root_version
),
dep_counts AS (
  SELECT s.name AS root_name, s.version AS root_version, COUNT(*) AS deps_rows
  FROM `bigquery-public-data.deps_dev_v1.DependenciesLatest` AS dl
  JOIN `YOUR_PROJECT.licensegraph.seed_roots` AS s
    ON dl.Name = s.name AND dl.Version = s.version
  WHERE dl.System = 'PYPI'
  GROUP BY s.name, s.version
)
SELECT g.root_name, g.root_version, g.graph_nodes, d.deps_rows,
       g.graph_nodes - IFNULL(d.deps_rows, 0) AS diff
FROM graph_counts AS g
LEFT JOIN dep_counts AS d
  ON g.root_name = d.root_name AND g.root_version = d.root_version
ORDER BY ABS(diff) DESC;


-- -----------------------------------------------------------------------------
-- 7. EXPORT (tables are tiny, so the console download is enough)
--    Run each query below, then "Save results > CSV (local file)" and name the
--    files exactly as shown, into Dataset/deps_dev/ :
-- -----------------------------------------------------------------------------
-- node_versions.csv
SELECT name, version, licenses, is_seed
FROM `YOUR_PROJECT.licensegraph.node_versions`
ORDER BY name, version;

-- direct_edges.csv
SELECT name, version, dep_name, dep_version
FROM `YOUR_PROJECT.licensegraph.direct_edges`
ORDER BY name, version, dep_name, dep_version;
