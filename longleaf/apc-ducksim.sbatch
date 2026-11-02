#!/bin/bash
#SBATCH --partition=general
#SBATCH --time=2-00:00:00
#SBATCH --mem=180g
#SBATCH --cpus-per-task=16
#SBATCH --output=/work/users/k/s/kschaper/logs/%x-%j.log
# usage: sbatch --job-name=apc-ducksim-hp-mp apc-ducksim.sbatch hp-mp
# Reads the IC / term files the matching semsimian comparison job wrote into working/.
set -euo pipefail
source /work/users/k/s/kschaper/automate-pheno-comparisons/apc-env.sh
cd $APC/working
case "$1" in
  hp-hp) IC=hpa_ic.tsv;  S2=HPO_terms.txt; LAB=HPO_terms.tsv;    NAME=HP_vs_HP ;;
  hp-mp) IC=mpa_ic.tsv;  S2=MP_terms.txt;  LAB=HPO_MP_terms.tsv; NAME=HP_vs_MP ;;
  hp-zp) IC=zpa_ic.tsv;  S2=ZP_terms.txt;  LAB=HPO_ZP_terms.tsv; NAME=HP_vs_ZP ;;
  *) echo "unknown comparison $1"; exit 2 ;;
esac
mkdir -p ducksim
echo "### NODE=$(hostname) JOB=$SLURM_JOB_ID COMPARISON=$1 START=$(date)"
/usr/bin/time -v python $APC/experimental/ducksim_all_by_all.py \
  --phenio $PYSTOW_HOME/oaklib/phenio.db --ic $IC --set1 HPO_terms.txt --set2 $S2 --labels $LAB \
  --out ducksim/${NAME}_ducksim.tsv --memory-limit 150GB --threads 16
echo "### DONE END=$(date)"
