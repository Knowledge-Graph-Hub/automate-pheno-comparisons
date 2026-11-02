"""Command line: `pheno-comparisons information-content` and `pheno-comparisons build`."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import yaml

from pheno_comparisons.build import build_release, compute_information_content_tables, ontology_versions
from pheno_comparisons.spec import COMPARISONS


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="pheno-comparisons", description=__doc__)
    sub = p.add_subparsers(dest="command", required=True)

    ic = sub.add_parser("information-content",
                        help="write the annotation IC into a closurized KG (needs write access)")
    ic.add_argument("kg", type=Path, help="closurized monarch-kg.duckdb")

    b = sub.add_parser("build", help="write the comparison tarballs (reads the KG read-only)")
    b.add_argument("kg", type=Path, help="monarch-kg.duckdb with the annotation IC")
    b.add_argument("-o", "--output-dir", type=Path, required=True)
    b.add_argument("--kg-version", required=True, help="KG release, e.g. 2026-09-04; names files kg-<version>")
    b.add_argument("--metadata", type=Path,
                   help="the KG's metadata.yaml, to record PHENIO and ontology versions in the logs")
    b.add_argument("--comparison", action="append", choices=sorted(COMPARISONS),
                   help="repeatable; default all")
    b.add_argument("--work-dir", type=Path, help="scratch space (default <output-dir>/.work)")
    b.add_argument("--memory-limit", help="DuckDB memory limit, e.g. 64GB")
    b.add_argument("--threads", type=int)
    b.add_argument("--keep-work", action="store_true")

    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.command == "information-content":
        for row in compute_information_content_tables(args.kg):
            print(f"{row['corpus']}: {row['term_count']:,} terms, {row['entity_count']:,} entities")
        return 0
    versions = {}
    if args.metadata:
        versions = ontology_versions((yaml.safe_load(args.metadata.read_text()) or {}).get("sources", []))
    for t in build_release(args.kg, args.output_dir, args.kg_version, versions=versions,
                           comparisons=args.comparison, work_dir=args.work_dir,
                           memory_limit=args.memory_limit, threads=args.threads, keep_work=args.keep_work):
        print(t)
    return 0


if __name__ == "__main__":
    sys.exit(main())
