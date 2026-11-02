#!/bin/bash
#SBATCH --job-name=apc-build-kg2021
#SBATCH --partition=general
#SBATCH --time=06:00:00
#SBATCH --mem=128g
#SBATCH --cpus-per-task=16
#SBATCH --output=/work/users/k/s/kschaper/logs/%x-%j.log
# HP-MP and HP-ZP with mouse/zebrafish annotations from the final dipper-era KG (2021-09), ducksim engine.
set -euo pipefail
source /work/users/k/s/kschaper/automate-pheno-comparisons/apc-env.sh
cd $APC
export DUCKSIM_MEMORY_LIMIT=100GB DUCKSIM_THREADS=16
WD=working-kg-2021-09
COMMON="--working-dir $WD --animal-annotations monarch-kg-2021-09 --engine ducksim"
echo "### NODE=$(hostname) JOB=$SLURM_JOB_ID START=$(date)"
/usr/bin/time -v python run_pipeline.py $COMMON --test-mode
/usr/bin/time -v python run_pipeline.py $COMMON --skip-setup --comparison hp-mp
/usr/bin/time -v python run_pipeline.py $COMMON --skip-setup --comparison hp-zp
ls -la $WD/*.tar.gz; cat $WD/*_log.yaml; cat $WD/annotation_sources.json
echo "### DONE END=$(date)"
