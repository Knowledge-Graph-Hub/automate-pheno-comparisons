#!/bin/bash
#SBATCH --partition=general
#SBATCH --time=04:00:00
#SBATCH --mem=96g
#SBATCH --cpus-per-task=8
#SBATCH --output=/work/users/k/s/kschaper/logs/%x-%j.log
# usage: sbatch --job-name=apc-verify-hp-mp apc-verify.sbatch HP_vs_MP mpa_ic.tsv
set -euo pipefail
source /work/users/k/s/kschaper/automate-pheno-comparisons/apc-env.sh
cd $APC/working
/usr/bin/time -v python $APC/experimental/compare_outputs.py ${1}_semsimian_phenio_20260929.tsv ducksim/${1}_ducksim.tsv --ic $2 --workdir $APC/verify-tmp --memory-limit ${DUCK_MEM:-60GB}
