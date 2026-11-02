"""Build the phenotype comparison release from a closurized Monarch KG via koza."""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tarfile
from datetime import datetime, timezone
from importlib.metadata import version as package_version
from collections.abc import Iterable
from pathlib import Path

import duckdb
import yaml
from koza.graph_operations import compute_annotation_information_content, compute_pairwise_similarity
from koza.model.graph_operations import AnnotationInformationContentConfig, PairwiseSimilarityConfig

from pheno_comparisons.spec import (
    ASSOCIATION_PREDICATE,
    COMPARISONS,
    CORPORA,
    CORPUS_COLUMNS,
    CORPUS_TABLE,
    IC_TABLE,
    MIN_ANCESTOR_INFORMATION_CONTENT,
    Corpus,
)

logger = logging.getLogger(__name__)

# The historical semsimian release layout (runoak similarity + label join); columns
# semsimian never filled are written as the string "None", as before.
RELEASE_COLUMNS = (
    "subject_id", "subject_label", "subject_source", "object_id", "object_label", "object_source",
    "ancestor_id", "ancestor_label", "ancestor_source", "object_information_content",
    "subject_information_content", "ancestor_information_content", "jaccard_similarity",
    "cosine_similarity", "dice_similarity", "phenodigm_score",
)
_RELEASE_SELECT = """
    SELECT subject_id, coalesce(subject_label, 'None') AS subject_label, 'None' AS subject_source,
           object_id, coalesce(object_label, 'None') AS object_label, 'None' AS object_source,
           ancestor_id, 'None' AS ancestor_label, 'None' AS ancestor_source,
           'None' AS object_information_content, 'None' AS subject_information_content,
           ancestor_information_content, jaccard_similarity,
           'None' AS cosine_similarity, 'None' AS dice_similarity, phenodigm_score
    FROM read_parquet(?)
    ORDER BY subject_id, object_id  -- deterministic output; also compresses ~30% smaller
"""


def _q(s: str) -> str:
    return "'" + str(s).replace("'", "''") + "'"


def _koza_version() -> str:
    try:
        return package_version("koza")
    except Exception:  # pragma: no cover - editable/odd installs
        return "unknown"


# --------------------------------------------------------------------------- step 1


def compute_information_content_tables(
    kg_path: str | Path, quiet: bool = True, corpora: Iterable[Corpus] | None = None
) -> list[dict]:
    """Write each corpus's annotation IC into the KG's shared `IC_TABLE` and record it in `CORPUS_TABLE`.

    `corpora` defaults to the release's `CORPORA`; callers pass their own to add corpora to the
    same tables (monarch-ingest adds the Monarch API's other search groups). Only the given
    corpora's rows are replaced in either table, so runs for different corpora can come in any
    order. A corpus with no annotations fails the run rather than leaving an empty corpus to
    surface later. Needs write access to `kg_path` (run it in the KG build's sequential stage).
    """
    kg_path = Path(kg_path)
    rows = []
    for corpus in corpora if corpora is not None else CORPORA.values():
        result = compute_annotation_information_content(AnnotationInformationContentConfig(
            database_path=kg_path,
            output_table=IC_TABLE,
            corpus=corpus.key,
            association_predicate=ASSOCIATION_PREDICATE,
            association_categories=corpus.categories,
            subject_prefixes=corpus.subject_prefixes,
            object_prefixes=corpus.object_prefixes,
            include_negated=False,
            quiet=quiet,
        ))
        if not result.entity_count:
            raise RuntimeError(
                f"annotation corpus {corpus.key} ({corpus.description}) has no annotated entities in {kg_path}"
            )
        logger.info(f"{IC_TABLE} {corpus.key}: {result.term_count:,} terms from {result.entity_count:,} entities")
        rows.append({
            "corpus": corpus.key, "description": corpus.description,
            "categories": corpus.categories, "subject_prefixes": corpus.subject_prefixes,
            "object_prefixes": corpus.object_prefixes, "entity_count": result.entity_count,
            "association_count": result.association_count, "term_count": result.term_count,
            "koza_version": _koza_version(), "computed_at": datetime.now(timezone.utc).isoformat(),
        })
    _record_corpora(kg_path, rows)
    return rows


def _record_corpora(kg_path: Path, rows: list[dict]) -> None:
    """Replace these corpora's rows of `CORPUS_TABLE`, creating it if needed, in one transaction."""
    columns = ", ".join(CORPUS_COLUMNS)
    con = duckdb.connect(str(kg_path))
    try:
        con.execute("BEGIN TRANSACTION")
        con.execute(f"CREATE TABLE IF NOT EXISTS {CORPUS_TABLE} "
                    f"({', '.join(f'{c} {t}' for c, t in CORPUS_COLUMNS.items())})")
        con.execute(f"DELETE FROM {CORPUS_TABLE} WHERE corpus IN (SELECT unnest(?))", [[r["corpus"] for r in rows]])
        con.executemany(f"INSERT INTO {CORPUS_TABLE} ({columns}) VALUES ({', '.join('?' for _ in CORPUS_COLUMNS)})",
                        [[r[c] for c in CORPUS_COLUMNS] for r in rows])
        con.execute("COMMIT")
    finally:
        con.close()


# --------------------------------------------------------------------------- versions


def ontology_versions(sources: list[dict]) -> dict[str, str]:
    """PHENIO and component ontology versions from Monarch KG release metadata.

    `sources` is the `sources` list of a KG `metadata.yaml`, or the list of
    per-ingest release-metadata documents monarch-ingest aggregates into it.
    Returns e.g. {"phenio": "v2026-09-01", "hp": "2026-06-23", "mp": ..., "zp": ...}.
    """
    found: dict[str, str] = {}

    def walk(nodes, inside_phenio=False):
        if not isinstance(nodes, list):
            return
        for node in nodes:
            if not isinstance(node, dict):  # an empty or malformed metadata document; versions are log-only
                continue
            node_id = str(node.get("id", ""))
            is_phenio = node_id in ("phenio", "infores:phenio")
            if is_phenio and node.get("version"):
                found.setdefault("phenio", str(node["version"]))
            if inside_phenio and node_id.startswith("infores:") and node.get("version"):
                found.setdefault(node_id.split(":", 1)[1], str(node["version"]))
            walk(node.get("sources"), inside_phenio or is_phenio)

    walk(sources)
    return found


# --------------------------------------------------------------------------- step 2


def _tar_gz(tarball: Path, directory: Path, members: list[str], threads: int | None) -> None:
    """tar | pigz when pigz is available (the TSVs are tens of GB), else tarfile."""
    tmp = tarball.with_name(tarball.name + ".tmp")
    if shutil.which("pigz") and shutil.which("tar"):
        pigz = ["pigz", "-6"] + (["-p", str(threads)] if threads else [])
        with open(tmp, "wb") as out:
            # COPYFILE_DISABLE: stop macOS bsdtar adding AppleDouble "._" entries
            env = {**os.environ, "COPYFILE_DISABLE": "1"}
            tar = subprocess.Popen(["tar", "-cf", "-", *members], cwd=directory, stdout=subprocess.PIPE, env=env)
            gz = subprocess.run(pigz, stdin=tar.stdout, stdout=out, check=False)
            tar.stdout.close()
            if tar.wait() != 0 or gz.returncode != 0:
                tmp.unlink(missing_ok=True)
                raise RuntimeError(f"failed to create {tarball}")
    else:
        with tarfile.open(tmp, "w:gz", compresslevel=6) as tf:
            for m in members:
                tf.add(directory / m, arcname=m)
    tmp.replace(tarball)


def _corpus_provenance(kg_path: Path) -> dict[str, dict]:
    con = duckdb.connect(str(kg_path), read_only=True)
    try:
        cur = con.execute(f"SELECT * FROM {CORPUS_TABLE}")
        cols = [d[0] for d in cur.description]
        return {r[0]: dict(zip(cols, r)) for r in cur.fetchall()}
    except duckdb.CatalogException as e:
        raise RuntimeError(
            f"{kg_path} has no {CORPUS_TABLE} table; compute the annotation information content first "
            "(`pheno-comparisons information-content`, or the KG build's `information-content` stage)"
        ) from e
    finally:
        con.close()


def build_release(
    kg_path: str | Path,
    output_dir: str | Path,
    kg_version: str,
    *,
    versions: dict[str, str] | None = None,
    comparisons: list[str] | None = None,
    work_dir: str | Path | None = None,
    build_date: str | None = None,
    memory_limit: str | None = None,
    threads: int | None = None,
    keep_work: bool = False,
) -> list[Path]:
    """Write one tarball per comparison into `output_dir`; returns their paths.

    Each tarball holds the similarity TSV (semsimian release layout), a YAML log
    (KG version, ontology versions, corpus provenance, engine) and the IC file.
    The KG is only read. Intermediates go to `work_dir` (default
    `<output_dir>/.work`), removed afterwards unless `keep_work`.
    """
    kg_path, output_dir = Path(kg_path), Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    work = Path(work_dir) if work_dir else output_dir / ".work"
    work.mkdir(parents=True, exist_ok=True)
    build_date = build_date or datetime.now().strftime("%Y%m%d")
    tag = f"kg-{kg_version}"
    versions = versions or {}
    provenance = _corpus_provenance(kg_path)
    tarballs = []
    try:
        for key in comparisons or list(COMPARISONS):
            comp = COMPARISONS[key]
            corpus = CORPORA[comp.corpus]
            stem = f"{comp.prefix}_{tag}"
            name = f"{stem}_{build_date}"
            parquet = work / f"{name}.parquet"
            result = compute_pairwise_similarity(PairwiseSimilarityConfig(
                database_path=kg_path, output_path=parquet, ic_table=IC_TABLE, ic_corpus=corpus.key,
                subject_root=comp.subject_root, subject_prefixes=[comp.subject_prefix],
                object_root=comp.object_root, object_prefixes=[comp.object_prefix],
                min_ancestor_information_content=MIN_ANCESTOR_INFORMATION_CONTENT,
                memory_limit=memory_limit, threads=threads, quiet=True,
            ))
            logger.info(f"{name}: {result.row_count:,} pairs ({result.subject_count:,} x {result.object_count:,})")

            con = duckdb.connect()
            try:
                if memory_limit:
                    con.execute(f"SET memory_limit = {_q(memory_limit)}")
                if threads:
                    con.execute(f"SET threads = {int(threads)}")
                con.execute(f"SET temp_directory = {_q(str(work / 'spill'))}")
                con.execute(f"COPY ({_RELEASE_SELECT.replace('?', _q(str(parquet)))}) "
                            f"TO {_q(str(work / f'{name}.tsv'))} (FORMAT csv, HEADER true, DELIMITER '\t')")
                unlabeled = con.execute(
                    f"SELECT count(*) FROM read_parquet({_q(str(parquet))}) "
                    "WHERE subject_label IS NULL OR object_label IS NULL").fetchone()[0]
                con.execute(f"ATTACH {_q(str(kg_path))} AS kg (READ_ONLY)")
                con.execute(f"COPY (SELECT term, ic FROM kg.{IC_TABLE} WHERE corpus = {_q(corpus.key)} "
                            "ORDER BY term) "
                            f"TO {_q(str(work / corpus.ic_file))} (FORMAT csv, HEADER false, DELIMITER '\t')")
            finally:
                con.close()

            prov = provenance.get(corpus.key, {})
            log = {
                "name": name,
                "min_ancestor_information_content": MIN_ANCESTOR_INFORMATION_CONTENT,
                "engine": f"koza pairwise-similarity (koza {_koza_version()})",
                "kg": {"name": "monarch-kg", "version": kg_version},
                "versions": {k: versions[k] for k in ("hp", comp.object_ontology, "phenio") if k in versions},
                "annotations": {
                    "source": "monarch-kg edges (biolink:has_phenotype, negated excluded)",
                    "description": corpus.description,
                    "categories": list(corpus.categories),
                    "subject_prefixes": list(corpus.subject_prefixes),
                    "object_prefixes": list(corpus.object_prefixes),
                    "entities": prov.get("entity_count"),
                    "associations": prov.get("association_count"),
                    "ic_table": IC_TABLE,
                    "ic_corpus": corpus.key,
                },
                "terms": {"subject_root": comp.subject_root, "subjects": result.subject_count,
                          "object_root": comp.object_root, "objects": result.object_count},
                "rows": result.row_count,
                "rows_without_labels": unlabeled,
            }
            (work / f"{name}_log.yaml").write_text(yaml.safe_dump(log, sort_keys=False))

            tarball = output_dir / f"{stem}.tsv.tar.gz"
            _tar_gz(tarball, work, [f"{name}.tsv", f"{name}_log.yaml", corpus.ic_file], threads)
            tarballs.append(tarball)
            if not keep_work:
                for f in (parquet, work / f"{name}.tsv"):
                    f.unlink(missing_ok=True)
    finally:
        if not keep_work:
            shutil.rmtree(work, ignore_errors=True)
    return tarballs
