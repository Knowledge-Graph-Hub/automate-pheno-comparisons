# -*- coding: cp936 -*-
import logging as log
from pathlib import Path

import polars as pl
from tqdm import tqdm
from curies import get_obo_converter

info_log = log.getLogger("info")
info_debug = log.getLogger("debug")
converter = get_obo_converter()

def semsim_to_exomisersql(
    input_file: Path,
    subject_prefix: str,
    object_prefix: str,
    output: Path,
    threshold: float = 0.0,
    batch_size: int = 100000
):
    """
    Convert a semantic similarity file to SQL statements for H2 database import.

    This function reads a tab-separated semantic similarity file and generates
    SQL INSERT statements that can be imported into an H2 database.

    Args:
        input_file (Path): Path to the input semantic similarity file (TSV format).
        subject_prefix (str): Prefix for the subject columns (e.g., 'HP' for Human Phenotype).
        object_prefix (str): Prefix for the object columns (e.g., 'MP' for Mouse Phenotype).
        output (Path): Path to the output SQL file.
        threshold (float): Minimum SCORE threshold for filtering results. Default: 0.0.
        batch_size (int): Number of rows to process per batch. Default: 100000.

    Returns:
        None

    Raises:
        IOError: If there are issues reading the input file or writing to the output file.
    """
    _write_to_sql_file(
        input_file, subject_prefix, object_prefix, output, threshold, batch_size
    )


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

def _format_curie(id:str, check_prefix: str = None):
    """format curie to exomiser database way

    Args:
        id (str): input id
    """
    curie = converter.compress(id, passthrough=True)
    
    if len(curie) > 10:
        #info_debug.error(f"{curie} too long!")
        return None
    
    if check_prefix and not curie.startswith(f"{check_prefix}:"):
        return None
    
    return curie

def _format_row(mapping_id, data, subject_prefix, object_prefix):
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

    ancestor_id = _format_curie(data.get('ancestor_id', 'HP:0000000'))
    subject_id = _format_curie(data.get('subject_id', 'HP:0000000'), check_prefix = subject_prefix)
    object_id = _format_curie(data.get('object_id', 'HP:0000000'), check_prefix = object_prefix)
    
    if subject_id is None or object_id is None:
        return None
    
    if subject_id == object_id:
        return None
    
    ancestor_label = data.get('ancestor_label', 'phenotype')

    # Truncate labels to 144 characters to fit VARCHAR(255) schema constraint
    MAX_LABEL_LENGTH = 144
    subject_label = data['subject_label'].replace("'", "")[:MAX_LABEL_LENGTH]
    object_label = data['object_label'].replace("'", "")[:MAX_LABEL_LENGTH]
    ancestor_label_safe = ancestor_label.replace("'", "")[:MAX_LABEL_LENGTH]

    # TODO:Improve string escaping. Replace this code with parametrised query
    return f"""({mapping_id}, '{subject_id}', '{subject_label}', '{object_id}', '{object_label}', {jaccard_similarity}, {ancestor_information_content}, {score}, '{ancestor_id}', '{ancestor_label_safe}')"""  # noqa


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

    rows = []
    for frame in input_data.iter_rows(named=True):
        # Only include rows that meet the threshold
        if _get_score(frame) >= threshold:
            row = _format_row(data=frame, mapping_id=mapping_id + len(rows), subject_prefix=subject_prefix, object_prefix=object_prefix)
            if row:
                rows.append(row)

    # Only generate INSERT statement if there are rows to insert
    if rows:
        sql += f"""INSERT INTO EXOMISER.{subject_prefix}_{object_prefix}_MAPPINGS
(MAPPING_ID, {subject_prefix}_ID, {subject_prefix}_TERM, {object_id}, {object_term}, SIMJ, IC, SCORE, LCS_ID, LCS_TERM)
VALUES"""
        sql += ",\n".join(rows) + ";"

    return sql


def _write_to_sql_file(
    input_file: Path,
    subject_prefix: str,
    object_prefix: str,
    output: Path,
    threshold: float = 0.0,
    batch_size: int = 100000
):
    """
    Generate SQL file from semantic similarity data.

    This is the optimized version with better batching for large-scale data processing.

    Args:
        input_file (Path): Input TSV file
        subject_prefix (str): Subject prefix (e.g., 'HP')
        object_prefix (str): Object prefix (e.g., 'MP')
        output (Path): Output SQL file path
        threshold (float): Minimum score threshold
        batch_size (int): Number of rows per batch
    """
    output.unlink(missing_ok=True)

    # Read the input file in batches with improved batch size
    reader = pl.read_csv_batched(input_file, separator="\t", batch_size=batch_size)

    # Estimate total rows from file size (approximate, avoids full file scan)
    file_size = input_file.stat().st_size
    # Rough estimate: ~200 bytes per row average
    estimated_rows = file_size // 200

    with open(output, 'w') as writer:
        with tqdm(total=estimated_rows, desc="Processing rows", unit="rows") as pbar:
            mapping_id = 1
            batches = reader.next_batches(1)

            while batches:
                input_data = batches[0]
                sql = _prepare_rows(input_data, object_prefix, subject_prefix, mapping_id=mapping_id, threshold=threshold)
                writer.write(sql + "\n")

                len_input_data = len(input_data)
                mapping_id += len_input_data
                pbar.update(len_input_data)

                batches = reader.next_batches(1)
