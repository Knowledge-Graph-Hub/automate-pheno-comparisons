#!/usr/bin/env python3
"""Find which annotation-IC definition reproduces `runoak information-content --use-associations`.

Compares candidate SQL definitions (over PHENIO's subClassOf entailed_edge + a 2-column
entity<TAB>term association file) against an IC file runoak wrote.

Usage: python ic_definition_probe.py --phenio phenio.db --assoc mpa.tsv --ic mpa_ic.tsv
"""
import argparse
import json

import duckdb

ap = argparse.ArgumentParser()
ap.add_argument("--phenio", required=True)
ap.add_argument("--assoc", required=True, help="entity<TAB>term, no header (as run_pipeline.py writes mpa/zpa)")
ap.add_argument("--ic", required=True)
a = ap.parse_args()

c = duckdb.connect()
c.execute("INSTALL sqlite; LOAD sqlite")
c.execute(f"""CREATE TABLE clo AS SELECT DISTINCT subject s, object o FROM sqlite_scan('{a.phenio}','entailed_edge')
              WHERE predicate = 'rdfs:subClassOf'""")
c.execute(f"""CREATE TABLE assoc AS SELECT column0 e, column1 t FROM read_csv('{a.assoc}', header=false, delim='\t',
              quote='', columns={{'column0':'VARCHAR','column1':'VARCHAR'}})""")
c.execute(f"""CREATE TABLE ref AS SELECT column0 term, try_cast(column1 AS DOUBLE) ic FROM read_csv('{a.ic}',
              header=false, delim='\t', quote='', columns={{'column0':'VARCHAR','column1':'VARCHAR'}})
              WHERE try_cast(column1 AS DOUBLE) IS NOT NULL""")
info = dict(zip(["assoc_rows", "assoc_distinct_pairs", "entities", "ref_terms"],
                c.execute("""SELECT (SELECT count(*) FROM assoc), (SELECT count(*) FROM (SELECT DISTINCT e,t FROM assoc)),
                             (SELECT count(DISTINCT e) FROM assoc), (SELECT count(*) FROM ref)""").fetchone()))

# freq variants x denominator variants
freqs = {
    "distinct_entities": "count(DISTINCT a.e)",
    "assoc_rows": "count(*)",
    "distinct_pairs": "count(DISTINCT (a.e, a.t))",
}
denoms = {
    "distinct_entities": "(SELECT count(DISTINCT e) FROM assoc)",
    "assoc_rows": "(SELECT count(*) FROM assoc)",
    "distinct_pairs": "(SELECT count(*) FROM (SELECT DISTINCT e, t FROM assoc))",
}
results = {}
for fn, fexpr in freqs.items():
    for dn, dexpr in denoms.items():
        c.execute(f"""CREATE OR REPLACE TABLE cand AS
            SELECT c.o term, -log2({fexpr}::DOUBLE / {dexpr}) ic
            FROM assoc a JOIN clo c ON c.s = a.t GROUP BY c.o""")
        r = c.execute("""SELECT count(*) FILTER (WHERE r.term IS NOT NULL AND k.term IS NOT NULL),
                                count(*) FILTER (WHERE k.term IS NULL), count(*) FILTER (WHERE r.term IS NULL),
                                max(abs(r.ic - k.ic)), count(*) FILTER (WHERE abs(r.ic - k.ic) > 1e-12)
                         FROM ref r FULL OUTER JOIN cand k USING (term)""").fetchone()
        results[f"freq={fn} N={dn}"] = dict(zip(["both", "only_ref", "only_candidate", "max_abs_diff", "n_diff"], r))
best = min(results, key=lambda k: (results[k]["n_diff"] + results[k]["only_ref"] + results[k]["only_candidate"]))
extra = c.execute("""SELECT term, ic FROM ref WHERE term NOT IN (SELECT c.o FROM assoc a JOIN clo c ON c.s = a.t)
                     ORDER BY ic LIMIT 8""").fetchall()
print(json.dumps({"inputs": info, "best": best, "results": results, "ref_terms_not_reached_examples": extra},
                 indent=2, default=str))
