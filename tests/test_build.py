"""End-to-end tests on a tiny synthetic KG (closure + edges + nodes)."""

from __future__ import annotations

import tarfile

import duckdb
import pytest
import yaml

from pheno_comparisons import Corpus, build_release, compute_information_content_tables, ontology_versions
from pheno_comparisons.build import RELEASE_COLUMNS
from pheno_comparisons.cli import main
from pheno_comparisons.spec import CORPUS_TABLE, IC_TABLE

PARENTS = {  # term -> direct superclasses; UPHENO:X groups HP:1, MP:1 and ZP:1
    "HP:1": ["HP:0000118", "UPHENO:X"], "HP:2": ["HP:0000118"],
    "MP:1": ["MP:0000001", "UPHENO:X"], "MP:2": ["MP:0000001"],
    "ZP:1": ["ZP:0000000", "UPHENO:X"], "ZP:2": ["ZP:0000000"],
    "HP:0000118": [], "MP:0000001": [], "ZP:0000000": [], "UPHENO:X": [],
}
GENE = "biolink:GeneToPhenotypicFeatureAssociation"
DISEASE = "biolink:DiseaseToPhenotypicFeatureAssociation"
# four entities per corpus, one reaching term 1: IC(term 1) = IC(UPHENO:X) = -log2(1/4) = 2
EDGES = (
    [("MONDO:1", "HP:1", DISEASE)] + [(f"MONDO:{i}", "HP:2", DISEASE) for i in (2, 3, 4)]
    + [("MGI:1", "MP:1", GENE)] + [(f"MGI:{i}", "MP:2", GENE) for i in (2, 3, 4)]
    + [("ZFIN:1", "ZP:1", GENE)] + [(f"ZFIN:{i}", "ZP:2", GENE) for i in (2, 3, 4)]
    + [("MGI:9", "MP:1", "biolink:GenotypeToPhenotypicFeatureAssociation")]  # not a gene: excluded
)


def ancestors(t):
    out, todo = {t}, list(PARENTS[t])
    while todo:
        a = todo.pop()
        if a not in out:
            out.add(a)
            todo.extend(PARENTS[a])
    return out


@pytest.fixture
def kg(tmp_path):
    path = tmp_path / "monarch-kg.duckdb"
    con = duckdb.connect(str(path))
    con.execute("CREATE TABLE closure (subject_id VARCHAR, predicate_id VARCHAR, object_id VARCHAR)")
    for t in PARENTS:
        for a in ancestors(t):
            con.execute("INSERT INTO closure VALUES (?, 'rdfs:subClassOf', ?)", [t, a])
    con.execute("""CREATE TABLE edges (id VARCHAR, subject VARCHAR, predicate VARCHAR, object VARCHAR,
                   category VARCHAR, negated VARCHAR)""")
    for i, (s, o, cat) in enumerate(EDGES):
        con.execute("INSERT INTO edges VALUES (?, ?, 'biolink:has_phenotype', ?, ?, NULL)", [f"e{i}", s, o, cat])
    con.execute("CREATE TABLE nodes (id VARCHAR, name VARCHAR)")
    con.executemany("INSERT INTO nodes VALUES (?, ?)", [[t, f"label {t}"] for t in PARENTS])
    con.close()
    return path


def tables(path):
    con = duckdb.connect(str(path), read_only=True)
    try:
        return sorted(r[0] for r in con.execute("SHOW TABLES").fetchall())
    finally:
        con.close()


def test_information_content_tables(kg):
    rows = compute_information_content_tables(kg)
    assert {r["corpus"]: r["entity_count"] for r in rows} == {"mondo_hp": 4, "mgi_mp": 4, "zfin_zp": 4}
    con = duckdb.connect(str(kg), read_only=True)
    ic = dict(con.execute(f"SELECT term, ic FROM {IC_TABLE} WHERE corpus = 'mgi_mp'").fetchall())
    assert ic["UPHENO:X"] == pytest.approx(2.0) and ic["MP:0000001"] == pytest.approx(0.0)
    assert con.execute(f"SELECT count(*) FROM {CORPUS_TABLE}").fetchone()[0] == 3
    con.close()


def test_information_content_keeps_other_corpora(kg):
    """Corpora other callers write into the shared table (monarch-ingest's search groups) survive a rerun."""
    con = duckdb.connect(str(kg))
    con.execute(f"CREATE TABLE {IC_TABLE} (corpus VARCHAR, term VARCHAR, ic DOUBLE)")
    con.execute(f"INSERT INTO {IC_TABLE} VALUES ('hgnc_hp', 'HP:1', 7.0), ('mgi_mp', 'MP:STALE', 1.0)")
    con.close()
    compute_information_content_tables(kg)
    con = duckdb.connect(str(kg), read_only=True)
    corpora = dict(con.execute(f"SELECT corpus, count(*) FROM {IC_TABLE} GROUP BY corpus").fetchall())
    stale = con.execute(f"SELECT count(*) FROM {IC_TABLE} WHERE term = 'MP:STALE'").fetchone()[0]
    con.close()
    assert corpora["hgnc_hp"] == 1 and stale == 0
    assert set(corpora) == {"hgnc_hp", "mondo_hp", "mgi_mp", "zfin_zp"}


def test_extra_corpora_survive_a_rerun_in_both_tables(kg):
    """A caller's own corpora (monarch-ingest's search groups) stay registered when the release's are rebuilt."""
    extra = Corpus(key="mgi_hp_decoy", categories=[GENE], subject_prefixes=["MGI"], object_prefixes=["MP"],
                   description="extra corpus")
    compute_information_content_tables(kg)
    compute_information_content_tables(kg, corpora=[extra])
    compute_information_content_tables(kg)  # the release's corpora again, as `pheno-comparisons information-content`
    con = duckdb.connect(str(kg), read_only=True)
    registered = sorted(r[0] for r in con.execute(f"SELECT corpus FROM {CORPUS_TABLE}").fetchall())
    with_ic = sorted(r[0] for r in con.execute(f"SELECT DISTINCT corpus FROM {IC_TABLE}").fetchall())
    con.close()
    assert registered == with_ic == ["mgi_hp_decoy", "mgi_mp", "mondo_hp", "zfin_zp"]


def test_corpus_without_annotations_fails(kg):
    empty = Corpus(key="wb_wbphenotype", categories=[GENE], subject_prefixes=["WB"], object_prefixes=["WBPhenotype"])
    with pytest.raises(RuntimeError, match="wb_wbphenotype .* no annotated entities"):
        compute_information_content_tables(kg, corpora=[empty])
    con = duckdb.connect(str(kg), read_only=True)
    assert not con.execute("SELECT count(*) FROM duckdb_tables() WHERE table_name = ?", [CORPUS_TABLE]).fetchone()[0]
    con.close()


def test_negated_annotations_are_excluded(kg):
    con = duckdb.connect(str(kg))
    con.execute("INSERT INTO edges VALUES ('neg', 'MGI:5', 'biolink:has_phenotype', 'MP:1', ?, 'True')", [GENE])
    con.close()
    rows = compute_information_content_tables(kg)
    assert {r["corpus"]: r["entity_count"] for r in rows}["mgi_mp"] == 4


def test_build_release(kg, tmp_path):
    compute_information_content_tables(kg)
    before = tables(kg)
    out = tmp_path / "pheno-comparisons"
    versions = {"phenio": "v2026-09-01", "hp": "2026-06-23", "mp": "2026-08-25", "zp": "2024-04-18"}
    tarballs = build_release(kg, out, "2026-09-04", versions=versions, build_date="20261005")

    assert [t.name for t in tarballs] == [
        "HP_vs_HP_semsimian_phenio_kg-2026-09-04.tsv.tar.gz",
        "HP_vs_MP_semsimian_phenio_kg-2026-09-04.tsv.tar.gz",
        "HP_vs_ZP_semsimian_phenio_kg-2026-09-04.tsv.tar.gz",
    ]
    assert sorted(p.name for p in out.iterdir()) == sorted(t.name for t in tarballs)  # no leftovers
    assert tables(kg) == before  # KG only read

    with tarfile.open(out / "HP_vs_MP_semsimian_phenio_kg-2026-09-04.tsv.tar.gz") as tf:
        names = tf.getnames()
        stem = "HP_vs_MP_semsimian_phenio_kg-2026-09-04_20261005"
        assert sorted(names) == sorted([f"{stem}.tsv", f"{stem}_log.yaml", "mpa_ic.tsv"])
        lines = tf.extractfile(f"{stem}.tsv").read().decode().splitlines()
        log = yaml.safe_load(tf.extractfile(f"{stem}_log.yaml"))
        ic_lines = tf.extractfile("mpa_ic.tsv").read().decode().splitlines()

    assert tuple(lines[0].split("\t")) == RELEASE_COLUMNS
    rows = [dict(zip(RELEASE_COLUMNS, line.split("\t"))) for line in lines[1:]]
    # only HP:1 x MP:1 shares an ancestor (UPHENO:X, IC 2.0) above 1.5
    assert [(r["subject_id"], r["object_id"], r["ancestor_id"]) for r in rows] == [("HP:1", "MP:1", "UPHENO:X")]
    r = rows[0]
    assert float(r["ancestor_information_content"]) == pytest.approx(2.0)
    # anc(HP:1) = {HP:1, HP:0000118, UPHENO:X}, anc(MP:1) = {MP:1, MP:0000001, UPHENO:X}: 1/5
    assert float(r["jaccard_similarity"]) == pytest.approx(0.2)
    assert float(r["phenodigm_score"]) == pytest.approx((2.0 * 0.2) ** 0.5)
    assert (r["subject_label"], r["object_label"], r["ancestor_label"], r["cosine_similarity"]) == (
        "label HP:1", "label MP:1", "None", "None")

    assert log["kg"] == {"name": "monarch-kg", "version": "2026-09-04"}
    assert log["versions"] == {"hp": "2026-06-23", "mp": "2026-08-25", "phenio": "v2026-09-01"}
    assert log["annotations"]["entities"] == 4 and log["rows"] == 1 and log["rows_without_labels"] == 0
    assert log["terms"]["subjects"] == 3 and log["terms"]["objects"] == 3
    assert "UPHENO:X\t2.0" in ic_lines
    assert sorted(line.split("\t")[0] for line in ic_lines) == ["MP:0000001", "MP:1", "MP:2", "UPHENO:X"]
    assert (log["annotations"]["ic_table"], log["annotations"]["ic_corpus"]) == (IC_TABLE, "mgi_mp")


def test_build_requires_information_content(kg, tmp_path):
    with pytest.raises(RuntimeError, match="information-content"):
        build_release(kg, tmp_path / "out", "2026-09-04")


def test_ontology_versions():
    sources = [
        {"id": "alliance-ingest", "version": "9.1.0", "sources": [{"id": "infores:mgi", "version": "x"}]},
        {"id": "kg-phenio", "version": "v2026-09-01", "sources": [
            {"id": "phenio", "version": "v2026-09-01", "sources": [
                {"id": "infores:hp", "version": "2026-06-23"},
                {"id": "infores:mp", "version": "2026-08-25"},
                {"id": "infores:zp", "version": "2024-04-18"},
            ]},
            {"id": "infores:upheno-cross-species", "version": "2026-08-30"},
        ]},
        {"id": "monarch-phenotype-profile-ingest", "sources": [{"id": "infores:hp", "version": "other"}]},
    ]
    assert ontology_versions(sources) == {
        "phenio": "v2026-09-01", "hp": "2026-06-23", "mp": "2026-08-25", "zp": "2024-04-18"}


def test_ontology_versions_skips_malformed_documents():
    """An empty or non-YAML release-metadata download must not abort the build: versions are log-only."""
    sources = [None, "<html>not yaml</html>", ["a", "list"],
               {"id": "kg-phenio", "sources": "oops"},
               {"id": "phenio", "version": "v1", "sources": [None, {"id": "infores:hp", "version": "h"}]}]
    assert ontology_versions(sources) == {"phenio": "v1", "hp": "h"}


def test_cli(kg, tmp_path):
    assert main(["information-content", str(kg)]) == 0
    meta = tmp_path / "metadata.yaml"
    meta.write_text(yaml.safe_dump({"sources": [{"id": "phenio", "version": "v1"}]}))
    assert main(["build", str(kg), "-o", str(tmp_path / "o"), "--kg-version", "2026-09-04",
                 "--metadata", str(meta), "--comparison", "hp-zp"]) == 0
    assert [p.name for p in (tmp_path / "o").iterdir()] == ["HP_vs_ZP_semsimian_phenio_kg-2026-09-04.tsv.tar.gz"]
