"""Exomiser's cross-species phenotype similarity tables, built from the Monarch KG.

Two steps, matching the KG build's stages:

1. :func:`compute_information_content_tables` writes the annotation IC of each
   corpus (diseases -> HP, mouse genes -> MP, zebrafish genes -> ZP) into the
   closurized KG's shared `annotation_information_content` table. It needs write
   access, so it runs in the sequential stage.
2. :func:`build_release` reads the KG read-only and writes one tarball per
   comparison (HP-HP, HP-MP, HP-ZP) in the historical semsimian release format.

The similarity math lives in koza (`annotation-information-content`,
`pairwise-similarity`); this package holds the product decisions.
"""

from pheno_comparisons.build import build_release, compute_information_content_tables, ontology_versions
from pheno_comparisons.spec import COMPARISONS, CORPORA, Comparison, Corpus

__all__ = [
    "COMPARISONS",
    "CORPORA",
    "Comparison",
    "Corpus",
    "build_release",
    "compute_information_content_tables",
    "ontology_versions",
]
