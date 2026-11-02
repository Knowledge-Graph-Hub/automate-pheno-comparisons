# Running on UNC Longleaf

SLURM scripts used for the 2026-09-29 release. Paths assume the repo is synced to
`/work/users/k/s/kschaper/automate-pheno-comparisons`; edit `apc-env.sh` for another user.

| Script | Purpose |
|---|---|
| `apc-env.sh` | uv caches, `PYSTOW_HOME` (oaklib ontology cache) and the venv on `/work` scratch |
| `apc-setup.sbatch` | downloads + versions (`--test-mode`), pre-builds the shared HP term list |
| `apc-compare.sbatch <hp-hp\|hp-mp\|hp-zp>` | one semsimian comparison (`--skip-setup`); run the three in parallel after setup |
| `apc-build-kg2021.sbatch` | HP-MP and HP-ZP with `--animal-annotations monarch-kg-2021-09 --engine ducksim` |
| `apc-ducksim.sbatch`, `apc-verify.sbatch`, `apc-spotcheck.sbatch` | ducksim vs semsimian equivalence checks |

Typical run:

```bash
S=$(sbatch --parsable apc-setup.sbatch)
for c in hp-hp hp-mp hp-zp; do sbatch --dependency=afterok:$S --job-name=apc-$c apc-compare.sbatch $c; done
```

Venv: `uv venv --python 3.11 .venv && uv pip install -r requirements.txt`.
Semsimian runs single-threaded; HP-ZP peaked at 155 GB and ~6 h, so keep `--mem` >= 180g for it.
