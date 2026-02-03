# automate-pheno-comparisons
Jenkins-based automation of phenotype semantic similarity on PHENIO with Semsimian.

## Overview

This repository provides two equivalent ways to run the phenotype comparison pipeline:

- `Jenkinsfile`: CI pipeline that runs comparisons and publishes results to Zenodo.
- `run_pipeline.py`: local runner intended to mirror the Jenkins behavior.

Each run produces three comparison tarballs:

- `HP_vs_HP_semsimian_phenio.tar.gz`
- `HP_vs_MP_semsimian_phenio.tar.gz`
- `HP_vs_ZP_semsimian_phenio.tar.gz`

Each tarball includes the similarity TSV, a YAML log file, and the information-content file used.

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
