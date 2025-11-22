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
    hp_ic_list: Path,
    hp_label_list: Path,
    threshold: float = 0.0,
    threshold_column: str = "default",
    batch_size: int = 100000,
    score_column: str = None,
    compute_phenodigm: bool = False,
    format: str = "psv"
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
        score_column (str): Column name to use as the phenodigm score. If None, uses 'phenodigm_score' or 'cosine_similarity'. Default: None.

    Returns:
        None

    Raises:
        IOError: If there are issues reading the input file or writing to the output file.
    """
    hp_ic_list = (
        pl.read_csv(hp_ic_list, separator="\t", has_header=False)
        .rename({"column_1": "hp_id", "column_2": "information_content"})
    )[["hp_id", "information_content"]]   # select only the columns you want

    hp_label_list = (
        pl.read_csv(hp_label_list, separator="\t", has_header=False)
        .rename({"column_1": "hp_id", "column_2": "label"})
    )[["hp_id", "label"]]

    hp_id_list = hp_label_list.join(hp_ic_list, on="hp_id", how="left")

    _write_to_file(
        input_file, subject_prefix, object_prefix, output, threshold, threshold_column, batch_size, score_column, compute_phenodigm, format, hp_id_list
    )


def _get_score(data, score_column: str = 'phenodigm_score', compute_phenodigm: bool = False):
    """Extract score from data, using specified column or prioritizing phenodigm_score over cosine_similarity

    Args:
        data (dict): row data
        score_column (str): Specific column to use for score. If None, uses default priority.

    Returns:
        float: The score value
    """
    if score_column:
        if score_column in data:
            score = data.get(score_column, 0)
            if compute_phenodigm and ('ancestor_information_content' in data) and (score_column != 'phenodigm_score'):
                aic = data.get('ancestor_information_content', 1)
                score = (score * aic) ** 0.5
            return score
    
    if compute_phenodigm and ('ancestor_information_content' not in data):
        raise ValueError(f"Asked to compute phenodigm score but 'ancestor_information_content' is missing: {data}.")
    else:
        raise ValueError(f"Valid score could not be determined from data: {data}")

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

def _get_row(mapping_id, data, subject_prefix, object_prefix, score = None):
    """format row in a exomiser database way

    Args:
        mapping_id (_type_): row sequencial id
        data (_type_): row data
        score_column (str): Column name to use as the phenodigm score
    """
    # Handle optional columns with defaults
    jaccard_similarity = data.get('jaccard_similarity', 0)
    ancestor_information_content = data.get('ancestor_information_content', 0)

    ancestor_id = _format_curie(data.get('ancestor_id', 'HP:0000000'))
    subject_id = _format_curie(data.get('subject_id', 'HP:0000000'), check_prefix = subject_prefix)
    object_id = _format_curie(data.get('object_id', 'HP:0000000'), check_prefix = object_prefix)
    
    if subject_id is None or object_id is None:
        return None
    
    if subject_id == object_id:
        # These are handled separately
        return None
    
    ancestor_label = data.get('ancestor_label', 'phenotype')

    # Truncate labels to 144 characters to fit VARCHAR(255) schema constraint
    MAX_LABEL_LENGTH = 144
    subject_label = data['subject_label'].replace("'", "")[:MAX_LABEL_LENGTH]
    object_label = data['object_label'].replace("'", "")[:MAX_LABEL_LENGTH]
    ancestor_label_safe = ancestor_label.replace("'", "")[:MAX_LABEL_LENGTH]

    # TODO:Improve string escaping. Replace this code with parametrised query
    return [mapping_id, subject_id, subject_label, object_id, object_label, jaccard_similarity, ancestor_information_content, score, ancestor_id, ancestor_label_safe]


def _prepare_rows(
    input_data: pl.DataFrame, subject_prefix: str, object_prefix: str, mapping_id=1, threshold: float = 0.0, threshold_column: str = "default", score_column: str = None, compute_phenodigm: bool = False, format: str = "psv"
) -> None:
    """This function is responsible for generate sql insertion query for each semsim profile row

    Args:
        input_data (pl.DataFrame): input data. (e.g. semantic similarity profile file)
        subject_prefix (str): subject prefix. (e.g HP)
        object_prefix (str): object prefix. (e.g MP)
        mapping_id (int, optional): MAPPING_ID.
        threshold (float, optional): Minimum SCORE threshold for filtering results.
        score_column (str): Column name to use as the phenodigm score.
    """
    stream = ""
    if mapping_id == 1 and format == "sql":
        stream += f"TRUNCATE TABLE EXOMISER.{subject_prefix}_{object_prefix}_MAPPINGS;\n"

    rows = []
    for frame in input_data.iter_rows(named=True):
        score = _get_score(frame, score_column=score_column, compute_phenodigm=compute_phenodigm)
        threshold_score = frame.get(threshold_column, 0) if threshold_column != "default" else score
        if threshold_score >= threshold:
            row = _get_row(data=frame, mapping_id=mapping_id + len(rows), subject_prefix=subject_prefix, object_prefix=object_prefix, score=score)
            if row:
                if format == "sql":
                    format_row = f"""({', '.join(['?' for _ in row])})"""
                elif format == "psv":
                    format_row = "|".join([str(item) if item is not None else '' for item in row])
                else:
                    raise ValueError(f"Unsupported format: {format}")
                rows.append(format_row)

    # Only generate INSERT statement if there are rows to insert
    if rows:
        if format == "sql":
            stream += f"""INSERT INTO EXOMISER.{subject_prefix}_{object_prefix}_MAPPINGS
    (MAPPING_ID, {subject_prefix}_ID, {subject_prefix}_TERM, {object_prefix}_ID, {object_prefix}_TERM, SIMJ, IC, SCORE, LCS_ID, LCS_TERM)
    VALUES"""
            stream += ",\n".join(rows) + ";"
        elif format == "psv":
            stream += "\n".join(rows)

    return stream


def _write_to_file(
    input_file: Path,
    subject_prefix: str,
    object_prefix: str,
    output: Path,
    threshold: float = 0.0,
    threshold_column: str = "default",
    batch_size: int = 100000,
    score_column: str = None,
    compute_phenodigm: bool = False,
    format: str = "psv",
    hp_id_list: pl.DataFrame = pl.DataFrame(),
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
        score_column (str): Column name to use as the phenodigm score
    """
    output.unlink(missing_ok=True)

    # Read the input file in batches with improved batch size
    reader = pl.read_csv_batched(input_file, separator="\t", batch_size=batch_size)

    # Estimate total rows from file size (approximate, avoids full file scan)
    file_size = input_file.stat().st_size
    # Rough estimate: ~200 bytes per row average
    estimated_rows = file_size // 200
    mapping_id = 1

    with open(output, 'w') as writer:
        if format == "psv":
            if subject_prefix == "HP" and object_prefix == "HP" and not hp_id_list.is_empty():
                rows = []
                for hp_id, hp_label, ic_score in hp_id_list.iter_rows():
                    ic_score = ic_score if ic_score is not None else 1.0
                    score = (1.0 * ic_score) ** 0.5

                    row = [
                        mapping_id,
                        hp_id,
                        hp_label,
                        hp_id,
                        hp_label,
                        1.0,
                        ic_score,
                        score,
                        "HP:0000000",
                        "",
                    ]
                    rows.append("|".join(str(x) for x in row))
                    mapping_id += 1
                writer.write("\n".join(rows) + "\n")
        with tqdm(total=estimated_rows, desc="Processing rows", unit="rows") as pbar:
            
            batches = reader.next_batches(1)

            while batches:
                input_data = batches[0]
                rows_string = _prepare_rows(input_data, subject_prefix, object_prefix, mapping_id=mapping_id, threshold=threshold, threshold_column=threshold_column, score_column=score_column, compute_phenodigm=compute_phenodigm, format=format)
                writer.write(rows_string+"\n")

                len_input_data = len(input_data)
                mapping_id += len_input_data
                pbar.update(len_input_data)

                batches = reader.next_batches(1)
