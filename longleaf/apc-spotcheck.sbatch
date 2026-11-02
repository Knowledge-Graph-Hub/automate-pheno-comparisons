#!/bin/bash
#SBATCH --job-name=apc-spotcheck
#SBATCH --partition=general
#SBATCH --time=06:00:00
#SBATCH --mem=128g
#SBATCH --cpus-per-task=4
#SBATCH --output=/work/users/k/s/kschaper/logs/%x-%j.log
set -euo pipefail
source /work/users/k/s/kschaper/automate-pheno-comparisons/apc-env.sh
cd $APC/working-kg-2021-09
for c in MP:mpa_ic.tsv ZP:zpa_ic.tsv; do o=${c%%:*}; ic=${c##*:}
  t=$(ls HP_vs_${o}_semsimian_phenio_kg-2021-09_2*.tsv | grep -v _log)
  echo "== $t"
  /usr/bin/time -f "elapsed=%e s maxrss=%M KB" python $APC/experimental/spotcheck_semsimian.py --phenio $PYSTOW_HOME/oaklib/phenio.db \
    --ic $ic --set1 HPO_terms.txt --set2 ${o}_terms.txt --table $t --n 300
done
