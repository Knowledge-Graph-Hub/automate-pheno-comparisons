#!/bin/bash
#SBATCH --partition=general
#SBATCH --time=3-00:00:00
#SBATCH --mem=180g
#SBATCH --cpus-per-task=16
#SBATCH --output=/work/users/k/s/kschaper/logs/%x-%j.log
# usage: sbatch --job-name=apc-hp-mp apc-compare.sbatch hp-mp
set -euo pipefail
source /work/users/k/s/kschaper/automate-pheno-comparisons/apc-env.sh
cd $APC
echo "### NODE=$(hostname) JOB=$SLURM_JOB_ID COMPARISON=$1 START=$(date)"
/usr/bin/time -v python run_pipeline.py --working-dir working --skip-setup --comparison "$1"
echo "### DONE END=$(date)"
