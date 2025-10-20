# Local Pipeline Runner

This directory contains a Python script (`run_pipeline.py`) that replicates the Jenkins pipeline for running phenotype ontology semantic similarity analyses locally.

## Overview

The pipeline performs semantic similarity comparisons between:
- **HP vs HP**: Human Phenotype Ontology against itself
- **HP vs MP**: Human Phenotype vs Mammalian Phenotype (mouse)
- **HP vs ZP**: Human Phenotype vs Zebrafish Phenotype

Results include semantic similarity scores using various metrics (Jaccard, Cosine, Dice, Phenodigm) based on information content.

## Prerequisites

- Python 3.9 or higher
- Internet connection (to download ontologies, tools, and data)
- oaklib with semsimian support installed

## Installation

1. **Clone or download this repository**

2. **Install Python dependencies**:
   
   It's recommended to use a virtual environment:
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

   Then install the required packages:
   ```bash
   pip install -r requirements.txt
   ```

   Or manually:
   ```bash
   pip install "oaklib[semsimian] @ git+https://github.com/INCATools/ontology-access-kit.git"
   ```

## Usage

### Basic Usage

Run the full pipeline with all comparisons:
```bash
python run_pipeline.py
```

This will:
1. Create a `./working` directory
2. Download required tools (DuckDB, yq)
3. Download ontologies and association data
4. Run all three comparisons (HP-HP, HP-MP, HP-ZP)
5. Create result tarballs in the working directory

### Run Specific Comparisons

Run only HP vs HP:
```bash
python run_pipeline.py --comparison hp-hp
```

Run only HP vs MP:
```bash
python run_pipeline.py --comparison hp-mp
```

Run only HP vs ZP:
```bash
python run_pipeline.py --comparison hp-zp
```

### Custom Options

**Use a different working directory**:
```bash
python run_pipeline.py --working-dir /path/to/workdir
```

**Use a custom PHENIO database**:
```bash
python run_pipeline.py --custom-phenio /path/to/phenio.db
```

This allows you to use your own Semantic SQL database version of PHENIO instead of downloading the default through OAK. The file must be a SQLite database compatible with oaklib. This is useful for:
- Testing development versions of PHENIO
- Using a specific frozen version of PHENIO
- Working with modified PHENIO databases
- Ensuring reproducibility with a known PHENIO version

**Test mode** (download files but skip comparisons):
```bash
python run_pipeline.py --test-mode
```

This is useful for:
- Testing that all downloads work correctly
- Verifying network connectivity and file accessibility
- Setting up the environment without running time-consuming analyses
- Quick validation of the setup process

**Skip setup if already done** (resume from comparisons):
```bash
python run_pipeline.py --skip-setup
```

**Adjust Resnik threshold**:
```bash
python run_pipeline.py --resnik-threshold 2.0
```

**Enable debug logging**:
```bash
python run_pipeline.py --debug
```

### Full Command-Line Options

```
usage: run_pipeline.py [-h] [--working-dir WORKING_DIR] 
                       [--comparison {all,hp-hp,hp-mp,hp-zp}]
                       [--resnik-threshold RESNIK_THRESHOLD]
                       [--custom-phenio CUSTOM_PHENIO]
                       [--skip-setup] [--test-mode] [--debug]

optional arguments:
  -h, --help            show this help message and exit
  --working-dir WORKING_DIR
                        Working directory for pipeline execution (default: ./working)
  --comparison {all,hp-hp,hp-mp,hp-zp}
                        Which comparison(s) to run (default: all)
  --resnik-threshold RESNIK_THRESHOLD
                        Minimum ancestor information content threshold (default: 1.5)
  --custom-phenio CUSTOM_PHENIO
                        Path to custom PHENIO Semantic SQL database file (e.g., phenio.db)
  --skip-setup          Skip setup stage (use if already configured)
  --test-mode           Testing mode: download all files but skip similarity comparisons
  --debug               Enable debug logging
```

## Output

The pipeline creates the following outputs in the working directory:

### Result Files
- `HP_vs_HP_semsimian_phenio_YYYYMMDD.tsv` - HP vs HP similarity results
- `HP_vs_MP_semsimian_phenio_YYYYMMDD.tsv` - HP vs MP similarity results
- `HP_vs_ZP_semsimian_phenio_YYYYMMDD.tsv` - HP vs ZP similarity results

### Log Files
- `*_log.yaml` - Metadata including ontology versions and parameters

### Tarballs
- `HP_vs_HP_semsimian_phenio.tar.gz` - Compressed results for HP vs HP
- `HP_vs_MP_semsimian_phenio.tar.gz` - Compressed results for HP vs MP
- `HP_vs_ZP_semsimian_phenio.tar.gz` - Compressed results for HP vs ZP

Each tarball contains:
- The main similarity TSV file
- The log YAML file
- The information content file used for calculations

## How It Works

The pipeline performs these stages:

1. **Setup**
   - Creates working directory
   - Downloads tools (DuckDB for data processing, yq for YAML parsing)
   - Downloads ontologies (HP, MP, ZP, PHENIO) via oaklib
   - Downloads association tables (HPOA, MPA, ZPA)

2. **For each comparison (HP-HP, HP-MP, HP-ZP)**
   - Extracts ontology terms
   - Calculates information content from associations
   - Runs semantic similarity analysis using semsimian
   - Adds human-readable labels using DuckDB
   - Creates metadata log file
   - Packages results into tarball

### Progress Indicators

The pipeline includes progress timers for long-running operations:
- **Term extraction**: Shows elapsed time while extracting terms from ontologies
- **Information content calculation**: Updates every 30 seconds during IC computation
- **Similarity analysis**: Displays progress during the longest operations (can take 30-60 minutes for HP-HP)

Progress messages appear in the format:
```
  [Operation name] Still running... (elapsed: 2m 30s)
```

The timer updates automatically every 30 seconds to reassure you that the pipeline is still active.

## Differences from Jenkins Pipeline

The Python script replicates the Jenkins pipeline functionality with these changes:

- **No Docker**: Runs directly on your system (requires Python 3.9+)
- **No S3 Upload**: Results are stored locally in the working directory
- **User-managed Python environment**: You manage your own Python environment and dependencies
- **Modular execution**: Can run individual comparisons
- **Better logging**: Structured logging with progress indicators
- **Error handling**: Clearer error messages and stack traces
- **Skip options**: Can resume from specific stages

## Troubleshooting

**Issue**: Python version too old
- **Solution**: Install Python 3.9 or higher

**Issue**: `runoak` command not found
- **Solution**: Make sure you've installed oaklib with semsimian support: `pip install "oaklib[semsimian] @ git+https://github.com/INCATools/ontology-access-kit.git"`

**Issue**: Out of memory during similarity calculation
- **Solution**: The similarity calculations can be memory-intensive for large ontologies. Try running on a machine with more RAM or run individual comparisons separately.

**Issue**: oaklib installation fails
- **Solution**: Make sure you have git installed and network access to GitHub.
