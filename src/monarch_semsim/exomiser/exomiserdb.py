# -*- coding: cp936 -*-
import logging as log
import sqlite3
from pathlib import Path

import polars as pl
from tqdm import tqdm

info_log = log.getLogger("info")
info_debug = log.getLogger("debug")


def semsim_to_exomisersql(input_file: Path, subject_prefix: str, object_prefix: str, output: Path, threshold: float = 0.0):
    """
    Convert a semantic similarity file to SQL statements and write them to a file.

    This function reads a tab-separated semantic similarity file, generates SQL statements
    to create a table in an exomiser phenotypic table format, truncate existing data, and insert new data.
    The resulting SQL statements are written to the specified output file.

    Args:
        input_file (Path): Path to the input semantic similarity file (TSV format).
        subject_prefix (str): Prefix for the subject columns (e.g., 'HP' for Human Phenotype).
        object_prefix (str): Prefix for the object columns (e.g., 'MP' for Mouse Phenotype).
        output (Path): Path to the output SQL file.
        threshold (float): Minimum SCORE threshold for filtering results. Default: 0.0.

    Returns:
        None

    Raises:
        IOError: If there are issues reading the input file or writing to the output file.
    """

    output.unlink(missing_ok=True)
    # Read the input file in batches
    reader = pl.read_csv_batched(input_file, separator="\t")
    batch_length = 5
    batches = reader.next_batches(batch_length)
    total_rows = sum(1 for _ in open(input_file)) - 1  # Subtract 1 for header

    with tqdm(total=total_rows, desc="Processing rows") as pbar:
        mapping_id = 1
        while batches:
            input_data = pl.concat(batches)
            sql = _prepare_rows(input_data, object_prefix, subject_prefix, mapping_id=mapping_id, threshold=threshold)
            with open(output, 'a') as writer:
                writer.writelines(sql)
                len_input_data = len(input_data)
                mapping_id += len_input_data
                pbar.update(len_input_data)

                batches = reader.next_batches(batch_length)


def _get_score(data):
    """Extract score from data, prioritizing phenodigm_score over cosine_similarity

    Args:
        data (dict): row data

    Returns:
        float: The score value
    """
    if 'phenodigm_score' in data:
        return data['phenodigm_score']
    elif 'cosine_similarity' in data:
        return data['cosine_similarity']
    else:
        return 0


def _format_row(mapping_id, data):
    """format row in a exomiser database way

    Args:
        mapping_id (_type_): row sequencial id
        data (_type_): row data
    """
    # Handle optional columns with defaults
    jaccard_similarity = data.get('jaccard_similarity', 0)
    ancestor_information_content = data.get('ancestor_information_content', 0)

    # Get score using centralized function
    score = _get_score(data)

    # Handle optional ancestor_id
    ancestor_id = data.get('ancestor_id', 'HP:0000000')
    ancestor_label = data.get('ancestor_label', 'phenotype')
    ancestor_id_first = ancestor_id.split(",")[0] if ancestor_id else ''

    # TODO:Improve string escaping. Replace this code with parametrised query
    return f"""({mapping_id}, '{data['subject_id']}', '{data['subject_label'].replace("'", "")}', '{data['object_id']}', '{data['object_label'].replace("'", "")}', {jaccard_similarity}, {ancestor_information_content}, {score}, '{ancestor_id_first}', '{ancestor_label.replace("'", "")}')"""  # noqa


def _prepare_rows(
    input_data: pl.DataFrame, subject_prefix: str, object_prefix: str, mapping_id=1, threshold: float = 0.0
) -> None:
    """This function is responsible for generate sql insertion query for each semsim profile row

    Args:
        input_data (pl.DataFrame): input data. (e.g. semantic similarity profile file)
        subject_prefix (str): subject prefix. (e.g HP)
        object_prefix (str): object prefix. (e.g MP)
        mapping_id (int, optional): MAPPING_ID.
        threshold (float, optional): Minimum SCORE threshold for filtering results.
    """
    sql = ""
    if mapping_id == 1:
        sql += f"TRUNCATE TABLE EXOMISER.{subject_prefix}_{object_prefix}_MAPPINGS;\n"

    object_id = (
        f"{object_prefix}_ID_HIT" if subject_prefix == object_prefix else f"{object_prefix}_ID"
    )
    object_term = (
        f"{object_prefix}_HIT_TERM" if subject_prefix == object_prefix else f"{object_prefix}_TERM"
    )
    sql += f"""INSERT INTO EXOMISER.{subject_prefix}_{object_prefix}_MAPPINGS
(MAPPING_ID, {subject_prefix}_ID, {subject_prefix}_TERM, {object_id}, {object_term}, SIMJ, IC, SCORE, LCS_ID, LCS_TERM)
VALUES"""
    rows = []
    for frame in input_data.iter_rows(named=True):
        # Only include rows that meet the threshold
        if _get_score(frame) >= threshold:
            rows.append(_format_row(data=frame, mapping_id=mapping_id + len(rows)))

    sql += ",\n".join(rows) + ";"
    return sql
