#!/usr/bin/env python3
"""All-by-all term similarity in DuckDB, reproducing `runoak similarity` + semsimian output.

Mirrors what run_pipeline.py produces for one comparison, but computed as SQL instead of
semsimian's in-memory Rust closure:

    closure  = PHENIO entailed_edge, predicate rdfs:subClassOf (reflexive, as semsql ships it)
    IC       = the annotation-derived IC file (hpoa_ic.tsv / mpa_ic.tsv / zpa_ic.tsv);
               ancestors absent from it are ignored for Resnik, exactly as semsimian does
    Jaccard  = |anc(s) ∩ anc(o)| / |anc(s) ∪ anc(o)|   (full closure, IC-independent)
    Resnik   = max IC over shared ancestors;   row kept only if Resnik > threshold (strict)
    Phenodigm= sqrt(Resnik * Jaccard)

Differences from the semsimian release that are expected and not bugs:
  * ancestor_id: when several shared ancestors tie for max IC, semsimian/oaklib emits an
    arbitrary one; here the lexically smallest tied ID is used (deterministic).
  * row order differs.

Usage:
  python ducksim_all_by_all.py --phenio phenio.db --ic hpoa_ic.tsv \
      --set1 HPO_terms.txt --set2 HPO_terms.txt --labels HPO_terms.tsv \
      --out HP_vs_HP_ducksim.tsv [--threshold 1.5] [--batch-size 500]
"""
import argparse
import os
import time
from pathlib import Path

import duckdb

OUT_COLUMNS = """
    subject_id, subject_label, 'None' AS subject_source,
    object_id, object_label, 'None' AS object_source,
    ancestor_id, 'None' AS ancestor_label, 'None' AS ancestor_source,
    'None' AS object_information_content, 'None' AS subject_information_content,
    ancestor_information_content, jaccard_similarity,
    'None' AS cosine_similarity, 'None' AS dice_similarity, phenodigm_score
"""


def read_terms(path):
    """runoak `descendants` output: 'CURIE ! label' per line -> CURIEs (order kept, deduped)."""
    ids = []
    for line in Path(path).read_text().splitlines():
        cur = line.split(" ! ", 1)[0].strip()
        if cur:
            ids.append(cur)
    return list(dict.fromkeys(ids))


def read_ic(path):
    """Same rule as semsimian's import_custom_ic_map: col0 = term, col1 = float IC; later wins."""
    ic = {}
    for line in Path(path).read_text().splitlines():
        cols = line.split("\t")
        if len(cols) >= 2:
            try:
                ic[cols[0]] = float(cols[1])
            except ValueError:
                continue  # header / non-data line
    return ic


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--phenio", required=True, help="PHENIO semsql SQLite file")
    ap.add_argument("--ic", required=True, help="IC TSV (term<TAB>ic), as written by run_pipeline.py")
    ap.add_argument("--set1", required=True, help="subject terms file (runoak descendants output)")
    ap.add_argument("--set2", required=True, help="object terms file (runoak descendants output)")
    ap.add_argument("--labels", required=True, help="id<TAB>label file used for the label join")
    ap.add_argument("--out", required=True, help="output TSV")
    ap.add_argument("--threshold", type=float, default=1.5, help="min ancestor IC (strict >)")
    ap.add_argument("--batch-size", type=int, default=500, help="subject terms per SQL batch")
    ap.add_argument("--db", default=None, help="DuckDB file for intermediates (default: <out>.duckdb)")
    ap.add_argument("--memory-limit", default=os.environ.get("DUCKSIM_MEMORY_LIMIT"),
                    help="DuckDB memory_limit, e.g. 64GB (env DUCKSIM_MEMORY_LIMIT). Set it under SLURM: "
                         "DuckDB's default is 80%% of the machine's RAM, not the job's allocation")
    ap.add_argument("--threads", type=int, default=int(os.environ.get("DUCKSIM_THREADS", 0)) or None,
                    help="DuckDB threads (env DUCKSIM_THREADS)")
    ap.add_argument("--keep-db", action="store_true", help="keep the intermediate DuckDB file")
    args = ap.parse_args()

    t0 = time.time()
    db = args.db or f"{args.out}.duckdb"
    Path(db).unlink(missing_ok=True)
    con = duckdb.connect(db)
    if args.memory_limit:
        con.execute(f"SET memory_limit = '{args.memory_limit}'")
    if args.threads:
        con.execute(f"SET threads = {int(args.threads)}")
    con.execute("SET preserve_insertion_order = false")
    con.execute("INSTALL sqlite; LOAD sqlite")

    # Bulk-load via DuckDB readers: row-wise executemany took ~2 min for ~43k rows.
    s_terms, o_terms = read_terms(args.set1), read_terms(args.set2)
    con.execute("CREATE TABLE s_terms AS SELECT unnest($1::VARCHAR[]) AS t, "
                "((generate_subscripts($1::VARCHAR[], 1) - 1) // $2)::INTEGER AS batch",
                [s_terms, args.batch_size])
    con.execute("CREATE TABLE o_terms AS SELECT unnest($1::VARCHAR[]) AS t", [o_terms])
    ic = read_ic(args.ic)
    con.execute("CREATE TABLE ic AS SELECT unnest($1::VARCHAR[]) AS term, unnest($2::DOUBLE[]) AS ic",
                [list(ic.keys()), list(ic.values())])
    print(f"terms: set1={len(s_terms)} set2={len(o_terms)} ic={len(ic)}  ({time.time()-t0:.0f}s)", flush=True)

    # closure restricted to the terms we compare; DISTINCT mirrors semsimian's HashSet closure
    phenio = str(args.phenio).replace("'", "''")
    con.execute(f"""
        CREATE TABLE clo AS
        SELECT DISTINCT e.subject AS t, e.object AS a
        FROM sqlite_scan('{phenio}', 'entailed_edge') e
        WHERE e.predicate = 'rdfs:subClassOf'
          AND e.subject IN (SELECT t FROM s_terms UNION SELECT t FROM o_terms)
    """)
    con.execute("CREATE TABLE sz AS SELECT t, count(*) AS sz FROM clo GROUP BY t")
    # ancestors of object terms, indexed by ancestor, for the batch join
    con.execute("CREATE TABLE o_clo AS SELECT c.t, c.a FROM clo c JOIN o_terms o ON o.t = c.t")
    n_clo = con.execute("SELECT count(*) FROM clo").fetchone()[0]
    print(f"closure rows={n_clo}  ({time.time()-t0:.0f}s)", flush=True)

    labels = str(args.labels).replace("'", "''")
    con.execute(f"""
        CREATE TABLE labels AS
        SELECT column0 AS id, column1 AS label
        FROM read_csv('{labels}', header=false, delim='\t', quote='', columns={{'column0':'VARCHAR','column1':'VARCHAR'}})
    """)

    con.execute("""
        CREATE TABLE result (subject_id VARCHAR, object_id VARCHAR, ancestor_id VARCHAR,
                             ancestor_information_content DOUBLE, jaccard_similarity DOUBLE,
                             phenodigm_score DOUBLE)
    """)
    n_batches = con.execute("SELECT max(batch) + 1 FROM s_terms").fetchone()[0] or 0
    for b in range(n_batches):
        tb = time.time()
        con.execute("""
            INSERT INTO result
            WITH common AS (
                SELECT sc.t AS s, oc.t AS o, sc.a AS a
                FROM s_terms st
                JOIN clo sc ON sc.t = st.t
                JOIN o_clo oc ON oc.a = sc.a
                WHERE st.batch = ?
            ),
            agg AS (
                SELECT c.s, c.o,
                       count(*) AS inter,
                       max(ic.ic) AS resnik  -- NULL-IC ancestors are ignored, as in semsimian
                FROM common c LEFT JOIN ic ON ic.term = c.a
                GROUP BY c.s, c.o
                HAVING max(ic.ic) > ?
            ),
            mica AS (  -- max-IC shared ancestor; ties -> smallest id (deterministic)
                SELECT c.s, c.o, min(c.a) AS mica
                FROM common c JOIN ic ON ic.term = c.a
                JOIN agg g ON g.s = c.s AND g.o = c.o AND ic.ic = g.resnik
                GROUP BY c.s, c.o
            )
            SELECT g.s, g.o, m.mica, g.resnik,
                   g.inter::DOUBLE / (zs.sz + zo.sz - g.inter) AS jaccard,
                   sqrt(g.resnik * (g.inter::DOUBLE / (zs.sz + zo.sz - g.inter))) AS phenodigm
            FROM agg g
            JOIN mica m ON m.s = g.s AND m.o = g.o
            JOIN sz zs ON zs.t = g.s
            JOIN sz zo ON zo.t = g.o
        """, [b, args.threshold])
        if b % 5 == 0 or b == n_batches - 1:
            n = con.execute("SELECT count(*) FROM result").fetchone()[0]
            print(f"batch {b+1}/{n_batches}: {time.time()-tb:.1f}s  rows so far={n}  "
                  f"elapsed={time.time()-t0:.0f}s", flush=True)

    out = str(args.out).replace("'", "''")
    # inner joins to labels, as run_pipeline.py's add_labels_with_duckdb does
    con.execute(f"""
        COPY (
            SELECT {OUT_COLUMNS}
            FROM (SELECT r.*, l1.label AS subject_label, l2.label AS object_label
                  FROM result r
                  JOIN labels l1 ON l1.id = r.subject_id
                  JOIN labels l2 ON l2.id = r.object_id)
        ) TO '{out}' WITH (HEADER true, DELIMITER '\t')
    """)
    n = con.execute("SELECT count(*) FROM result").fetchone()[0]
    con.close()
    if not args.keep_db:
        Path(db).unlink(missing_ok=True)
    print(f"DONE rows={n} out={args.out} elapsed={time.time()-t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
