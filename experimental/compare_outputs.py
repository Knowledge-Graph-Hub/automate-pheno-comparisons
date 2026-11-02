#!/usr/bin/env python3
"""Compare a semsimian release TSV against a ducksim_all_by_all.py TSV for the same comparison.

One FULL OUTER JOIN on (subject_id, object_id) yields row-set differences, max absolute score
deltas, and ancestor disagreement. A differing ancestor with equal IC is only a max-IC tie,
which semsimian breaks arbitrarily; --ic checks for that.

Runs on a file-backed DuckDB with a memory limit so large joins spill to disk.

Usage: python compare_outputs.py semsimian.tsv ducksim.tsv [--ic ic.tsv] [--tol 1e-9]
"""
import argparse
import json
import os
import tempfile

import duckdb

COLS = ("subject_id VARCHAR, object_id VARCHAR, ancestor_id VARCHAR, r DOUBLE, j DOUBLE, p DOUBLE")


def load(con, name, path):
    p = path.replace("'", "''")
    con.execute(f"""
        CREATE TABLE {name} AS
        SELECT subject_id, object_id, ancestor_id,
               ancestor_information_content::DOUBLE AS r,
               jaccard_similarity::DOUBLE AS j,
               phenodigm_score::DOUBLE AS p
        FROM read_csv('{p}', delim='\t', header=true, quote='', all_varchar=true)
    """)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("semsimian")
    ap.add_argument("ducksim")
    ap.add_argument("--ic", help="IC TSV, to check that differing ancestors are max-IC ties")
    ap.add_argument("--tol", type=float, default=1e-9)
    ap.add_argument("--memory-limit", default="48GB")
    ap.add_argument("--text", action="store_true",
                    help="also compare every column as exact text (labels, number formatting)")
    ap.add_argument("--workdir", default=os.environ.get("TMPDIR", tempfile.gettempdir()))
    a = ap.parse_args()

    dbfile = os.path.join(a.workdir, f"compare_{os.getpid()}.duckdb")
    con = duckdb.connect(dbfile)
    con.execute(f"SET memory_limit = '{a.memory_limit}'")
    con.execute(f"SET temp_directory = '{a.workdir}/duckdb_spill_{os.getpid()}'")
    con.execute("SET preserve_insertion_order = false")
    try:
        load(con, "sem", a.semsimian)
        load(con, "duck", a.ducksim)
        if a.ic:
            icp = a.ic.replace("'", "''")
            con.execute(f"""CREATE TABLE ic AS SELECT column0 AS term, try_cast(column1 AS DOUBLE) AS ic
                            FROM read_csv('{icp}', delim='\t', header=false,
                                          columns={{'column0':'VARCHAR','column1':'VARCHAR'}})""")
        else:
            con.execute("CREATE TABLE ic (term VARCHAR, ic DOUBLE)")
        row = con.execute("""
            WITH j AS (
                SELECT s.subject_id IS NOT NULL AS in_s, d.subject_id IS NOT NULL AS in_d,
                       abs(s.r - d.r) AS dr, abs(s.j - d.j) AS dj, abs(s.p - d.p) AS dp,
                       s.ancestor_id AS sa, d.ancestor_id AS da
                FROM sem s FULL OUTER JOIN duck d USING (subject_id, object_id)
            )
            SELECT count(*) FILTER (WHERE in_s), count(*) FILTER (WHERE in_d),
                   count(*) FILTER (WHERE in_s AND NOT in_d), count(*) FILTER (WHERE in_d AND NOT in_s),
                   max(dr), max(dj), max(dp),
                   count(*) FILTER (WHERE in_s AND in_d AND sa <> da)
            FROM j
        """).fetchone()
        keys = ["rows_semsimian", "rows_ducksim", "only_semsimian", "only_ducksim",
                "max_delta_resnik", "max_delta_jaccard", "max_delta_phenodigm", "ancestor_id_differs"]
        rep = dict(zip(keys, row))
        rep["dup_pairs_semsimian"] = rep["rows_semsimian"] - con.execute(
            "SELECT count(*) FROM (SELECT DISTINCT subject_id, object_id FROM sem)").fetchone()[0]
        if a.ic:
            rep["ancestor_differs_with_different_ic"] = con.execute("""
                SELECT count(*) FROM sem s JOIN duck d USING (subject_id, object_id)
                LEFT JOIN ic i1 ON i1.term = s.ancestor_id LEFT JOIN ic i2 ON i2.term = d.ancestor_id
                WHERE s.ancestor_id <> d.ancestor_id AND i1.ic IS DISTINCT FROM i2.ic
            """).fetchone()[0]
        # exact text comparison of every column except ancestor_id (max-IC ties differ by design)
        if a.text:
            cols = ["subject_label", "subject_source", "object_label", "object_source", "ancestor_label",
                    "ancestor_source", "object_information_content", "subject_information_content",
                    "ancestor_information_content", "jaccard_similarity", "cosine_similarity",
                    "dice_similarity", "phenodigm_score"]
            for name, path in (("semt", a.semsimian), ("duckt", a.ducksim)):
                pth = path.replace("'", "''")
                con.execute(f"CREATE TABLE {name} AS SELECT * FROM read_csv('{pth}', delim='\t', header=true, "
                            f"quote='', all_varchar=true)")
            rep["header_semsimian"] = [r[0] for r in con.execute("DESCRIBE semt").fetchall()]
            rep["header_identical"] = rep["header_semsimian"] == [r[0] for r in con.execute("DESCRIBE duckt").fetchall()]
            sel = ", ".join(f"count(*) FILTER (WHERE s.{c} IS DISTINCT FROM d.{c}) AS {c}" for c in cols)
            r = con.execute(f"SELECT {sel} FROM semt s JOIN duckt d USING (subject_id, object_id)").fetchone()
            rep["text_mismatches_by_column"] = {c: v for c, v in zip(cols, r) if v}
            ex = [c for c, v in zip(cols, r) if v][:3]
            rep["text_mismatch_examples"] = {
                c: con.execute(f"SELECT s.subject_id, s.object_id, s.{c}, d.{c} FROM semt s JOIN duckt d "
                               f"USING (subject_id, object_id) WHERE s.{c} IS DISTINCT FROM d.{c} LIMIT 3").fetchall()
                for c in ex}
        if rep["only_semsimian"] or rep["only_ducksim"]:
            for side, other, label in (("sem", "duck", "only_semsimian"), ("duck", "sem", "only_ducksim")):
                rep[f"examples_{label}"] = con.execute(
                    f"SELECT subject_id, object_id, r, j FROM {side} ANTI JOIN {other} "
                    f"USING (subject_id, object_id) LIMIT 5").fetchall()
        deltas = [rep[k] or 0 for k in ("max_delta_resnik", "max_delta_jaccard", "max_delta_phenodigm")]
        rep["equivalent"] = (rep["only_semsimian"] == 0 and rep["only_ducksim"] == 0
                             and max(deltas) <= a.tol
                             and not rep.get("ancestor_differs_with_different_ic"))
        print(json.dumps(rep, indent=2, default=str))
    finally:
        con.close()
        os.remove(dbfile)


if __name__ == "__main__":
    main()
