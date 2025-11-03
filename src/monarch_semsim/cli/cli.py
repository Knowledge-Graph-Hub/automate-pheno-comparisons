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
def semsim_to_exomisersql_command(
    input_file: Path, object_prefix: str, subject_prefix: str, output: Path
):
    """converts semsim file as an exomiser phenotypic database SQL format

    Args:
        input_file (Path): semsim input file. e.g phenio-plus-hp-mp.0.semsimian.tsv
        object_prefix (str): object prefix. e.g. MP
        subject_prefix (str): subject prefix e.g HP
        output (Path): Path where the SQL file will be written.
    """
    semsim_to_exomisersql(input_file, object_prefix, subject_prefix, output)




cli.add_command(semsim_to_exomisersql_command)
