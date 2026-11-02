#!/usr/bin/env python3
"""Spot-check a ducksim all-by-all table against live semsimian on a random sample of subject terms.

Runs semsimian (the same Rust library runoak uses) on N sampled subject terms x all object terms,
with the same PHENIO file, IC file and Resnik threshold, then compares those rows with the
ducksim table restricted to the same subjects.

Usage: python spotcheck_semsimian.py --phenio phenio.db --ic mpa_ic.tsv --set1 HPO_terms.txt \
           --set2 MP_terms.txt --table HP_vs_MP_..._ducksim.tsv [--n 300] [--seed 1]
"""
import argparse
import json
import random

import duckdb
from semsimian import Semsimian


def ids(path):
    return list(dict.fromkeys(l.split(" ! ", 1)[0].strip() for l in open(path) if l.strip()))


def main():
    ap = argparse.ArgumentParser()
    for a in ("--phenio", "--ic", "--set1", "--set2", "--table"):
        ap.add_argument(a, required=True)
    ap.add_argument("--n", type=int, default=300)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--threshold", type=float, default=1.5)
    a = ap.parse_args()

    s1, s2 = ids(a.set1), ids(a.set2)
    random.seed(a.seed)
    sample = sorted(random.sample(s1, min(a.n, len(s1))))
    ss = Semsimian(spo=None, predicates=["rdfs:subClassOf"], resource_path=a.phenio, custom_ic_map_path=a.ic)
    res = ss.all_by_all_pairwise_similarity(subject_terms=set(sample), object_terms=set(s2),
                                            minimum_jaccard_threshold=None, minimum_resnik_threshold=a.threshold)
    sem = {}
    for s, d in res.items():
        for o, (j, r, p, _cos, anc) in d.items():
            sem[(s, o)] = (r, j, p, set(anc))

    con = duckdb.connect()
    tbl = a.table.replace("'", "''")
    rows = con.execute(f"""
        SELECT subject_id, object_id, ancestor_id, ancestor_information_content::DOUBLE,
               jaccard_similarity::DOUBLE, phenodigm_score::DOUBLE
        FROM read_csv('{tbl}', delim='\t', header=true, quote='', all_varchar=true)
        WHERE subject_id IN (SELECT unnest(?::VARCHAR[]))""", [sample]).fetchall()
    duck = {(s, o): (r, j, p, anc) for s, o, anc, r, j, p in rows}

    both = sem.keys() & duck.keys()
    rep = {
        "sampled_subjects": len(sample),
        "rows_semsimian": len(sem), "rows_ducksim": len(duck),
        "only_semsimian": len(sem.keys() - duck.keys()), "only_ducksim": len(duck.keys() - sem.keys()),
        "max_delta_resnik": max((abs(sem[k][0] - duck[k][0]) for k in both), default=0.0),
        "max_delta_jaccard": max((abs(sem[k][1] - duck[k][1]) for k in both), default=0.0),
        "max_delta_phenodigm": max((abs(sem[k][2] - duck[k][2]) for k in both), default=0.0),
        "ducksim_ancestor_not_in_semsimian_max_ic_set": sum(1 for k in both if duck[k][3] not in sem[k][3]),
    }
    rep["pass"] = (rep["only_semsimian"] == 0 and rep["only_ducksim"] == 0
                   and max(rep["max_delta_resnik"], rep["max_delta_jaccard"], rep["max_delta_phenodigm"]) <= 1e-9
                   and rep["ducksim_ancestor_not_in_semsimian_max_ic_set"] == 0)
    print(json.dumps(rep, indent=2))


if __name__ == "__main__":
    main()
