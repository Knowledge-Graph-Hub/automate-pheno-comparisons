from pathlib import Path

import click

from monarch_semsim.exomiser.exomiserdb import semsim_to_exomisersql


@click.group()
def cli():
    """Your CLI command description."""
    click.echo("Monarch Semantic Similarity Profile CLI command!")



@click.command("semsim-to-exomisersql")
@click.option(
    "--input-file",
    "-i",
    required=True,
    metavar="FILE",
    help="Semsim input file.",
    type=Path,
)
@click.option(
    "--object-prefix",
    required=True,
    metavar="object-prefix",
    help="Object Prefix. e.g. MP",
    type=str,
)
@click.option(
    "--subject-prefix",
    required=True,
    metavar="subject-prefix",
    help="Subject Prefix. e.g. HP",
    type=str,
)
@click.option(
    "--output",
    "-o",
    required=True,
    metavar="output",
    help="""Path where the SQL file will be written.""",
    type=Path,
)
@click.option(
    "--hp-ic-list",
    required=True,
    metavar="hp-ic-list",
    help="Path to the HP information content list file.",
    type=Path,
)
@click.option(
    "--hp-label-list",
    required=True,
    metavar="hp-label-list",
    help="Path to the HP label list file.",
    type=Path,
)
@click.option(
    "--threshold",
    "-t",
    required=False,
    default=0.0,
    metavar="threshold",
    help="Minimum SCORE threshold for filtering results. Default: 0.0",
    type=float,
)
@click.option(
    "--threshold-column",
    required=True,
    default="default",
    help="Output format: 'default' (score), jaccard_similarity, cosine_similarity'.",
    type=str,
)
@click.option(
    "--batch-size",
    "-b",
    required=False,
    default=100000,
    metavar="batch-size",
    help="Number of rows to process in each batch. Default: 100000",
    type=int,
)
@click.option(
    "--score",
    "-s",
    required=False,
    default=None,
    metavar="score",
    help="Column name to use as the phenodigm score. If not specified, uses 'phenodigm_score' or falls back to 'cosine_similarity'.",
    type=str,
)
@click.option(
    "--compute-phenodigm",
    "-c",
    required=False,
    default=False,
    help="Indicate whether to compute the phenodigm score.",
    type=bool,
)
@click.option(
    "--format",
    required=False,
    default="psv",
    help="Output format: 'psv' (default) or 'sql'.",
    type=str,
)
@click.option(
    "--random",
    required=False,
    default=None,
    help="Overwrite score values with random numbers in the specified range (e.g., '0,1' for values between 0 and 1).",
    type=str,
)
def semsim_to_exomisersql_command(
    input_file: Path, object_prefix: str, subject_prefix: str, output: Path, hp_ic_list: Path, hp_label_list: Path, threshold: float, threshold_column: str, batch_size: int, score: str, compute_phenodigm: bool, format: str, random: str
):
    """converts semsim file as an exomiser phenotypic database SQL format

    Args:
        input_file (Path): semsim input file. e.g phenio-plus-hp-mp.0.semsimian.tsv
        object_prefix (str): object prefix. e.g. MP
        subject_prefix (str): subject prefix e.g HP
        output (Path): Path where the SQL file will be written.
        threshold (float): Minimum SCORE threshold for filtering results.
        batch_size (int): Number of rows to process in each batch.
        score (str): Column name to use as the phenodigm score.
        random (str): Range for random score values (e.g., '0,1').
    """
    # Parse random parameter if provided
    random_range = None
    if random:
        try:
            parts = random.split(',')
            if len(parts) != 2:
                raise ValueError("Random parameter must be in format 'min,max'")
            random_range = (float(parts[0]), float(parts[1]))
        except (ValueError, IndexError):
            raise click.ClickException(f"Invalid --random parameter: {random}. Expected format: 'min,max' (e.g., '0,1')")

    # Call with correct parameter order: input_file, subject_prefix, object_prefix, output, hp_ic_list, hp_label_list, threshold, batch_size, score_column
    semsim_to_exomisersql(input_file, subject_prefix, object_prefix, output, hp_ic_list, hp_label_list, threshold, threshold_column, batch_size, score, compute_phenodigm, format, random_range)




cli.add_command(semsim_to_exomisersql_command)
