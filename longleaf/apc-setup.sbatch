#!/bin/bash
#SBATCH --job-name=apc-setup
#SBATCH --partition=general
#SBATCH --time=06:00:00
#SBATCH --mem=32g
#SBATCH --cpus-per-task=4
#SBATCH --output=/work/users/k/s/kschaper/logs/apc-setup-%j.log
set -euo pipefail
source /work/users/k/s/kschaper/automate-pheno-comparisons/apc-env.sh
cd $APC
echo "### NODE=$(hostname) JOB=$SLURM_JOB_ID START=$(date)"
/usr/bin/time -v python run_pipeline.py --working-dir working --test-mode
# pre-build the HP term list shared by all three comparisons, so parallel jobs don't race on it
python - <<'PY'
from pathlib import Path
import os
from run_pipeline import PipelineConfig, PipelineRunner
cfg = PipelineConfig(working_dir=Path("working"))
os.chdir(cfg.working_dir)
PipelineRunner(cfg).get_ontology_terms("hp", "HP:0000118", "HPO")
PY
wc -l working/HPO_terms.txt working/*_version working/*.tsv
cat working/*_version
echo "### DONE END=$(date)"
