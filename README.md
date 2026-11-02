# automate-pheno-comparisons
Jenkins-based automation of phenotype semantic similarity on PHENIO with Semsimian.

## Overview

This repository provides two equivalent ways to run the phenotype comparison pipeline:

- `Jenkinsfile`: CI pipeline that runs comparisons and publishes results to Zenodo.
- `run_pipeline.py`: local runner intended to mirror the Jenkins behavior.

Each run produces three comparison tarballs:

- `HP_vs_HP_semsimian_phenio.tsv.tar.gz`
- `HP_vs_MP_semsimian_phenio_kg-<release>.tsv.tar.gz`
- `HP_vs_ZP_semsimian_phenio_kg-<release>.tsv.tar.gz`

Each tarball includes the similarity TSV, a YAML log file, and the information-content file used.
The log records the ontology versions, the similarity engine, and the URL, checksum and date of
the annotation file the information content was computed from.

### Annotation sources and the `kg-<release>` tag

Information content for HP-MP and HP-ZP comes from mouse and zebrafish gene-phenotype
annotations exported by the Monarch KG. The `kg-<release>` tag names the KG release those
annotations came from:

- `--animal-annotations monarch-kg` (default): the current Monarch KG export, tagged with that
  release's version, e.g. `kg-2026-09-04`. Only Biolink `Gene` subjects.
- `--animal-annotations monarch-kg-2021-09`: the final dipper-era Monarch KG (2021-09), frozen.
  Its annotations are sparser per subject (about 10 vs 15 phenotypes) and include non-gene MGI
  markers (transgenes, QTLs, chromosomal aberrations). Broad terms therefore keep a higher
  information content, more pairs clear the 1.5 cutoff, and HP-MP has ~95M rows vs ~61M.

HP-HP uses the HPO disease annotations (`phenotype.hpoa`) from HPO directly and is untagged.
Use a separate `--working-dir` per annotation source.

### Similarity engines

- `--engine semsimian` (default): `runoak similarity` with semsimian. Single-threaded.
- `--engine ducksim`: the same all-by-all table computed in DuckDB SQL
  (`experimental/ducksim_all_by_all.py`). Verified on the 2026-09-29 build to give identical rows,
  scores, labels and formatting; only `ancestor_id` can differ, where several ancestors tie for
  the maximum IC and semsimian picks one arbitrarily. About 20-35x faster. Set
  `DUCKSIM_MEMORY_LIMIT` (e.g. `100GB`) and `DUCKSIM_THREADS` under SLURM.

## Building from the Monarch KG (`pheno_comparisons` package)

The `pheno_comparisons` package builds the same tables from a closurized
`monarch-kg.duckdb`, using koza's `annotation-information-content` and
`pairwise-similarity` operations. No runoak, semsimian or PHENIO SQLite is needed.
It is what the monarch-ingest KG build runs:

```bash
uv sync
# 1. write the annotation IC into the KG's annotation_information_content table (needs write access)
uv run pheno-comparisons information-content monarch-kg.duckdb
# 2. write the tarballs (reads the KG read-only)
uv run pheno-comparisons build monarch-kg.duckdb -o pheno-comparisons \
    --kg-version 2026-09-04 --metadata metadata.yaml --memory-limit 32GB --threads 8
```

| Comparison | Information content from (KG `has_phenotype` edges) | Terms |
|---|---|---|
| HP-HP | MONDO diseases -> HP (DiseaseToPhenotypicFeatureAssociation) | HP:0000118 x HP:0000118 |
| HP-MP | MGI genes -> MP (GeneToPhenotypicFeatureAssociation) | HP:0000118 x MP:0000001 |
| HP-ZP | ZFIN genes -> ZP (GeneToPhenotypicFeatureAssociation) | HP:0000118 x ZP:0000000 |

Tarballs are named `<comparison>_kg-<release>.tsv.tar.gz`. They keep the
historical 16-column TSV layout; columns semsimian never filled are the
string `None`. On KG 2026-09-04 the HP-MP table reproduces every row and score
of the semsimian release. The few extra rows come from that release being built
later, against a standalone HP published after the KG's PHENIO. Within a KG
build, term sets, labels and closure all come from the same PHENIO. HP-HP now takes its information content from the KG's
MONDO disease annotations, not from HPO's `phenotype.hpoa` file.

## Data Releases

The results of this process are available on Zenodo:

- DOI: https://doi.org/10.5281/zenodo.18474575
- Latest record example: https://zenodo.org/records/18474576

## Zenodo Publishing Behavior

Both the Jenkins pipeline and `run_pipeline.py` publish a new Zenodo *version* on each run:

1. Create a new version draft from an existing record.
2. Remove any files inherited from the previous version.
3. Upload the new tarballs to the draft bucket.
4. Publish the draft.

The version name is set to the run date in `YYYY-MM-DD` format by default (for example `2025-07-24`).

No credentials are stored in this repository. Zenodo credentials are provided at runtime.

## Jenkins Usage

Run the Jenkins pipeline with these build parameters:

- `ZENODO_TOKEN` (required): Zenodo API token. This can be obtained from the "Applications" section of your Zenodo account menu.
- `ZENODO_RECORD_ID` (required, default `18474576`): Zenodo record ID to version.

The pipeline uses today’s date as the version name (UTC from the Jenkins host). You can change
the record ID per run by overriding `ZENODO_RECORD_ID`.

## Local Usage (`run_pipeline.py`)

The Python script mirrors the Jenkins pipeline and supports the same Zenodo publishing flow.

### Basic Run

```bash
python3 run_pipeline.py
```

### Run With Zenodo Upload

```bash
python3 run_pipeline.py \
  --zenodo-record-id 18474576 \
  --zenodo-token "$ZENODO_TOKEN"
```

### Select Comparisons

```bash
python3 run_pipeline.py --comparison hp-hp
python3 run_pipeline.py --comparison hp-mp
python3 run_pipeline.py --comparison hp-zp
```

### Custom Working Directory or PHENIO

```bash
python3 run_pipeline.py --working-dir /path/to/workdir
python3 run_pipeline.py --custom-phenio /path/to/phenio.db
```

### Test Mode (Skip Comparisons)

```bash
python3 run_pipeline.py --test-mode
```

### Zenodo Options

```bash
python3 run_pipeline.py \
  --zenodo-record-id 18474576 \
  --zenodo-token "$ZENODO_TOKEN" \
  --zenodo-version 2025-07-24 \
  --zenodo-base-url https://zenodo.org/api
```

## Runtime Arguments (Summary)

Common options for `run_pipeline.py`:

- `--working-dir`: Directory for pipeline execution (default `./working`)
- `--comparison`: `all`, `hp-hp`, `hp-mp`, or `hp-zp` (default `all`)
- `--resnik-threshold`: Minimum ancestor information content (default `1.5`)
- `--custom-phenio`: Path to a local PHENIO SQLite database
- `--skip-setup`: Skip tool downloads and data fetch
- `--test-mode`: Download data but skip comparisons
- `--zenodo-record-id`: Zenodo record ID (required to publish)
- `--zenodo-token`: Zenodo API token (required to publish)
- `--zenodo-version`: Zenodo version name (default: today `YYYY-MM-DD`)
- `--zenodo-base-url`: Zenodo API base URL (default `https://zenodo.org/api`)
