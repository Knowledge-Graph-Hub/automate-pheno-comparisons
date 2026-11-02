#!/usr/bin/env python3
"""
Local runner for phenotype comparison pipeline.

This script replicates the Jenkins pipeline for semantic similarity analysis
between HP (Human Phenotype), MP (Mammalian Phenotype), and ZP (Zebrafish Phenotype)
ontologies using PHENIO.

Usage:
    python run_pipeline.py [options]

Examples:
    # Run full pipeline with all comparisons
    python run_pipeline.py

    # Run only HP vs HP comparison
    python run_pipeline.py --comparison hp-hp

    # Use custom PHENIO database
    python run_pipeline.py --custom-phenio /path/to/phenio.db

    # Test mode: download files but skip comparisons
    python run_pipeline.py --test-mode

    # Use custom working directory
    python run_pipeline.py --working-dir /path/to/workdir
"""

import argparse
import hashlib
import gzip
import http.client
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ProgressTimer:
    """A simple timer that prints elapsed time periodically for long-running operations."""

    def __init__(self, operation_name: str, update_interval: int = 30):
        """
        Initialize the progress timer.

        Args:
            operation_name: Name of the operation being timed
            update_interval: Seconds between progress updates (default: 30)
        """
        self.operation_name = operation_name
        self.update_interval = update_interval
        self.start_time = None
        self.stop_flag = threading.Event()
        self.thread = None

    def _format_elapsed(self, seconds: float) -> str:
        """Format elapsed seconds into a readable string."""
        if seconds < 60:
            return f"{int(seconds)}s"
        elif seconds < 3600:
            mins = int(seconds / 60)
            secs = int(seconds % 60)
            return f"{mins}m {secs}s"
        else:
            hours = int(seconds / 3600)
            mins = int((seconds % 3600) / 60)
            return f"{hours}h {mins}m"

    def _print_progress(self):
        """Print progress updates until stopped."""
        while not self.stop_flag.wait(self.update_interval):
            if self.start_time is not None:
                elapsed = time.time() - self.start_time
                logger.info(
                    f"  [{self.operation_name}] Still running... (elapsed: {self._format_elapsed(elapsed)})")

    def start(self):
        """Start the progress timer."""
        self.start_time = time.time()
        self.stop_flag.clear()
        self.thread = threading.Thread(
            target=self._print_progress, daemon=True)
        self.thread.start()
        logger.info(f"Starting: {self.operation_name}")

    def stop(self):
        """Stop the progress timer and log final elapsed time."""
        if self.thread and self.thread.is_alive():
            self.stop_flag.set()
            self.thread.join(timeout=1)

        if self.start_time is not None:
            elapsed = time.time() - self.start_time
            logger.info(
                f"Completed: {self.operation_name} (took {self._format_elapsed(elapsed)})")

    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()
        return False


# Mouse (MP) and zebrafish (ZP) gene-phenotype annotations used for information content.
# Output names for HP-MP / HP-ZP carry a "kg-<release>" tag naming the KG the annotations came from.
ANNOTATION_SOURCES = {
    # Current Monarch KG export (Biolink TSV: subject=col 1, negated=col 6, object=col 8).
    'monarch-kg': {
        'base_url': 'https://data.monarchinitiative.org/monarch-kg/latest/tsv/gene_associations/',
        'metadata_url': 'https://data.monarchinitiative.org/monarch-kg/latest/metadata.yaml',
        'legacy_format': False,
        'tag': None,  # resolved at setup from the KG release metadata, e.g. kg-2026-09-04
        'archive': None,
    },
    # Final dipper-era Monarch KG (2021-09), frozen. Byte-identical to
    # gs://monarch-archive/202109/tsv/gene_associations/ (that bucket is not public).
    # Legacy TSV: subject=col 1, object=col 5.
    'monarch-kg-2021-09': {
        'base_url': 'https://data.monarchinitiative.org/dipper-kg/final/tsv/gene_associations/',
        'metadata_url': None,
        'legacy_format': True,
        'tag': 'kg-2021-09',
        'archive': 'gs://monarch-archive/202109/tsv/gene_associations/',
    },
}

ENGINES = ('semsimian', 'ducksim')
DUCKSIM_SCRIPT = Path(__file__).resolve().parent / 'experimental' / 'ducksim_all_by_all.py'


class PipelineConfig:
    """Configuration for the phenotype comparison pipeline."""

    def __init__(self, working_dir: Path, custom_phenio: Optional[Path] = None,
                 animal_annotations: str = 'monarch-kg', engine: str = 'semsimian'):
        # Convert to absolute path immediately to avoid issues with os.chdir
        self.working_dir = Path(working_dir).absolute()
        self.custom_phenio = Path(
            custom_phenio).absolute() if custom_phenio else None

        # Date-based naming
        self.build_date = datetime.now().strftime('%Y%m%d')
        self.release_date = datetime.now().strftime('%Y-%m-%d')

        # Pipeline parameters
        self.resnik_threshold = '1.5'
        if animal_annotations not in ANNOTATION_SOURCES:
            raise ValueError(f"unknown animal annotation source {animal_annotations!r}")
        if engine not in ENGINES:
            raise ValueError(f"unknown engine {engine!r}")
        self.animal_annotations = animal_annotations
        self.engine = engine
        # provenance of each downloaded annotation file: {'hpoa'|'mpa'|'zpa': {...}}
        self.annotation_provenance: Dict[str, Dict[str, str]] = {}

        # Output names. HP-HP uses no KG annotations, so it is untagged; HP-MP / HP-ZP
        # get "_kg-<release>" once the annotation tag is known (see apply_annotation_tag).
        self.annotation_tag: Optional[str] = ANNOTATION_SOURCES[animal_annotations]['tag']
        self.hp_vs_hp_prefix = "HP_vs_HP_semsimian_phenio"
        self.hp_vs_hp_name = f"{self.hp_vs_hp_prefix}_{self.build_date}"
        self.apply_annotation_tag(self.annotation_tag)

        # Ontology versions (will be populated during setup)
        self.hp_version: Optional[str] = None
        self.mp_version: Optional[str] = None
        self.zp_version: Optional[str] = None
        self.phenio_version: Optional[str] = None

        # Tools
        self.duckdb_path = self.working_dir / 'duckdb'
        self.yq_path = self.working_dir / 'yq'

    def apply_annotation_tag(self, tag: Optional[str]) -> None:
        """Set HP-MP / HP-ZP output names from the annotation-source tag (e.g. kg-2026-09-04)."""
        self.annotation_tag = tag
        suffix = f"_{tag}" if tag else ""
        self.hp_vs_mp_prefix = f"HP_vs_MP_semsimian_phenio{suffix}"
        self.hp_vs_zp_prefix = f"HP_vs_ZP_semsimian_phenio{suffix}"
        self.hp_vs_mp_name = f"{self.hp_vs_mp_prefix}_{self.build_date}"
        self.hp_vs_zp_name = f"{self.hp_vs_zp_prefix}_{self.build_date}"

    def save_annotation_state(self) -> None:
        """Persist the tag and provenance so --skip-setup / --upload-only runs reuse them."""
        state = {'animal_annotations': self.animal_annotations, 'annotation_tag': self.annotation_tag,
                 'provenance': self.annotation_provenance}
        (self.working_dir / 'annotation_sources.json').write_text(json.dumps(state, indent=2) + '\n')

    def load_annotation_state(self) -> None:
        path = self.working_dir / 'annotation_sources.json'
        if not path.exists():
            raise RuntimeError(f"{path} not found; run setup for this working directory first")
        state = json.loads(path.read_text())
        if state['animal_annotations'] != self.animal_annotations:
            raise RuntimeError(
                f"working dir was set up with --animal-annotations {state['animal_annotations']}, "
                f"not {self.animal_annotations}; use a separate --working-dir per source")
        self.annotation_provenance = state.get('provenance', {})
        self.apply_annotation_tag(state['annotation_tag'])

    def get_ducksim_phenio_path(self) -> Path:
        """Local PHENIO SQLite file for ducksim (the custom file, or oaklib's pystow cache)."""
        if self.custom_phenio:
            return self.custom_phenio
        import pystow  # oaklib dependency; honors PYSTOW_HOME
        return pystow.join('oaklib') / 'phenio.db'

    def get_phenio_identifier(self) -> str:
        """
        Get the oaklib identifier for PHENIO.

        Returns:
            String identifier for use with runoak -i flag
        """
        if self.custom_phenio:
            # Use custom PHENIO database file
            return f"sqlite:{self.custom_phenio}"
        else:
            # Use default OBO PHENIO
            return "sqlite:obo:phenio"

    def get_semsimian_phenio_identifier(self) -> str:
        """
        Get the semsimian oaklib identifier for PHENIO.

        Returns:
            String identifier for use with runoak -i flag in similarity analysis
        """
        if self.custom_phenio:
            # Use custom PHENIO database file with semsimian
            return f"semsimian:sqlite:{self.custom_phenio}"
        else:
            # Use default OBO PHENIO with semsimian
            return "semsimian:sqlite:obo:phenio"


class ZenodoClient:
    """Minimal Zenodo API client for creating new versions and uploading files."""

    def __init__(self, token: str, base_url: str = "https://zenodo.org/api"):
        self.token = token
        self.base_url = base_url.rstrip('/')

    def _request(self, method: str, url: str, payload: Optional[Dict] = None,
                 expect_json: bool = True) -> Optional[Dict]:
        data = None
        headers = {"Authorization": f"Bearer {self.token}"}
        if payload is not None:
            data = json.dumps(payload).encode('utf-8')
            headers["Content-Type"] = "application/json"

        request = urllib.request.Request(url, data=data,
                                         headers=headers, method=method)
        try:
            with urllib.request.urlopen(request) as response:
                body = response.read()
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode('utf-8', 'ignore')
            raise RuntimeError(
                f"Zenodo API request failed ({method} {url}): "
                f"{exc.code} {exc.reason} {error_body}"
            ) from exc

        if not expect_json:
            return None

        if not body:
            return {}
        return json.loads(body.decode('utf-8'))

    def create_new_version_draft(self, record_id: str) -> Dict:
        """Create a new version draft from an existing record."""
        response = self._request(
            "POST",
            f"{self.base_url}/deposit/depositions/{record_id}/actions/newversion"
        )
        if not response or "links" not in response or "latest_draft" not in response["links"]:
            raise RuntimeError(
                "Zenodo API did not return a latest_draft link.")

        latest_draft_url = response["links"]["latest_draft"]
        draft = self._request("GET", latest_draft_url)
        if not draft or "id" not in draft:
            raise RuntimeError("Zenodo API did not return a draft deposition.")
        return draft

    def delete_draft_files(self, draft_id: int, files: List[Dict]) -> None:
        """Delete all files copied into the draft from the previous version."""
        for file_info in files:
            file_id = file_info.get("id")
            if file_id is None:
                continue
            self._request(
                "DELETE",
                f"{self.base_url}/deposit/depositions/{draft_id}/files/{file_id}",
                expect_json=False
            )

    def update_metadata(self, draft_id: int, metadata: Dict) -> None:
        """Update draft metadata."""
        self._request(
            "PUT",
            f"{self.base_url}/deposit/depositions/{draft_id}",
            payload={"metadata": metadata}
        )

    def upload_file(self, bucket_url: str, file_path: Path) -> None:
        """Stream a file upload to the Zenodo bucket URL."""
        parsed = urllib.parse.urlparse(bucket_url)
        if parsed.scheme != "https":
            raise ValueError(f"Unexpected Zenodo bucket URL: {bucket_url}")

        target_path = parsed.path.rstrip(
            '/') + '/' + urllib.parse.quote(file_path.name)
        file_size = file_path.stat().st_size

        connection = http.client.HTTPSConnection(parsed.netloc)
        try:
            connection.putrequest("PUT", target_path)
            connection.putheader("Authorization", f"Bearer {self.token}")
            connection.putheader("Content-Type", "application/octet-stream")
            connection.putheader("Content-Length", str(file_size))
            connection.endheaders()

            with file_path.open('rb') as handle:
                while True:
                    chunk = handle.read(1024 * 1024)
                    if not chunk:
                        break
                    connection.send(chunk)

            response = connection.getresponse()
            body = response.read().decode('utf-8', 'ignore')
            if response.status >= 400:
                raise RuntimeError(
                    f"Zenodo upload failed for {file_path.name}: "
                    f"{response.status} {response.reason} {body}"
                )
        finally:
            connection.close()

    def publish(self, draft_id: int) -> None:
        """Publish the Zenodo draft deposition."""
        self._request(
            "POST",
            f"{self.base_url}/deposit/depositions/{draft_id}/actions/publish",
            expect_json=False
        )


class PipelineRunner:
    """Main pipeline runner class."""

    def __init__(self, config: PipelineConfig):
        self.config = config

    def run_command(self, command: str, shell: bool = True, check: bool = True) -> subprocess.CompletedProcess:
        """Run a shell command and return the result."""
        logger.info(f"Running: {command}")
        try:
            result = subprocess.run(
                command,
                shell=shell,
                check=check,
                capture_output=True,
                text=True,
                cwd=str(self.config.working_dir)
            )
            if result.stdout:
                logger.debug(f"Output: {result.stdout}")
            return result
        except subprocess.CalledProcessError as e:
            logger.error(f"Command failed: {command}")
            logger.error(f"Error output: {e.stderr}")
            raise

    def download_file(self, url: str, output_path: Path, chunk_size: int = 8192) -> Optional[str]:
        """
        Download a file from URL to output path using Python urllib.

        Args:
            url: URL to download from
            output_path: Path where to save the file
            chunk_size: Size of chunks to read at a time

        Returns:
            The server's Last-Modified header, if any (recorded as provenance)
        """
        logger.info(f"Downloading {url}...")
        try:
            with urllib.request.urlopen(url) as response:
                last_modified = response.headers.get('Last-Modified')
                with open(output_path, 'wb') as out_file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
            logger.debug(f"Downloaded to {output_path}")
            return last_modified
        except Exception as e:
            logger.error(f"Failed to download {url}: {e}")
            raise

    def download_and_extract_zip(self, url: str, extract_to: Path) -> None:
        """
        Download a zip file and extract it.

        Args:
            url: URL of the zip file
            extract_to: Directory to extract files to
        """
        zip_path = extract_to / "temp_download.zip"
        self.download_file(url, zip_path)

        logger.info(f"Extracting {zip_path.name}...")
        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)

        # Clean up zip file
        zip_path.unlink()
        logger.debug("Extraction complete")

    def download_and_decompress_gzip(self, url: str, output_path: Path) -> None:
        """
        Download a gzipped file and decompress it.

        Args:
            url: URL of the gzipped file
            output_path: Path where to save the decompressed file
        """
        logger.info(f"Downloading and decompressing {url}...")
        try:
            with urllib.request.urlopen(url) as response:
                with gzip.GzipFile(fileobj=response) as gzip_file:
                    with open(output_path, 'wb') as out_file:
                        shutil.copyfileobj(gzip_file, out_file)
            logger.debug(f"Decompressed to {output_path}")
        except Exception as e:
            logger.error(f"Failed to download and decompress {url}: {e}")
            raise

    def setup_working_directory(self):
        """Create and initialize the working directory."""
        logger.info(f"Setting up working directory: {self.config.working_dir}")
        self.config.working_dir.mkdir(parents=True, exist_ok=True)
        os.chdir(self.config.working_dir)

    def install_tools(self):
        """Download and install required command-line tools (duckdb, yq)."""
        logger.info("Installing required tools...")

        # Install DuckDB
        if not self.config.duckdb_path.exists():
            logger.info("Downloading DuckDB...")
            duckdb_url = "https://github.com/duckdb/duckdb/releases/download/v0.10.3/duckdb_cli-linux-amd64.zip"
            self.download_and_extract_zip(duckdb_url, self.config.working_dir)
            self.run_command(f"chmod +x {self.config.duckdb_path}")
            logger.info("DuckDB installed")
        else:
            logger.info("DuckDB already installed")

        # Install yq
        if not self.config.yq_path.exists():
            logger.info("Downloading yq...")
            yq_url = "https://github.com/mikefarah/yq/releases/download/v4.2.0/yq_linux_amd64"
            self.download_file(yq_url, self.config.yq_path)
            self.run_command(f"chmod +x {self.config.yq_path}")
            logger.info("yq installed")
        else:
            logger.info("yq already installed")

    def get_ontology_versions(self):
        """Retrieve version information for all ontologies."""
        logger.info("Retrieving ontology versions...")

        ontologies = {
            'hp': 'HP',
            'mp': 'MP',
            'zp': 'ZP',
            'phenio': 'PHENIO'
        }

        for key, ont_id in ontologies.items():
            logger.info(f"Getting version for {ont_id}...")

            # Use custom PHENIO identifier if provided
            if key == 'phenio':
                ont_identifier = self.config.get_phenio_identifier()
            else:
                ont_lower = ont_id.lower()
                ont_identifier = f"sqlite:obo:{ont_lower}"

            cmd = (
                f"runoak -i {ont_identifier} ontology-metadata --all | "
                f"{self.config.yq_path} eval '.[\"owl:versionIRI\"][0]' - > {key}_version"
            )
            self.run_command(cmd)

            # Read version from file
            version_file = self.config.working_dir / f"{key}_version"
            if version_file.exists():
                version = version_file.read_text().strip()
                setattr(self.config, f"{key}_version", version)
                logger.info(f"{ont_id} version: {version}")
            else:
                logger.warning(f"Could not read version for {ont_id}")

    def download_association_tables(self):
        """Download and preprocess association tables."""
        logger.info("Downloading association tables...")

        source = ANNOTATION_SOURCES[self.config.animal_annotations]
        wd = self.config.working_dir

        # Download HPOA (Human Phenotype Ontology Annotations)
        logger.info("Downloading HPOA...")
        hpoa_url = "http://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa"
        self.download_file(hpoa_url, wd / 'hpoa.tsv')
        hpoa_version = None
        with open(wd / 'hpoa.tsv') as fh:
            for line in fh:
                if not line.startswith('#'):
                    break
                if line.startswith('#version:'):
                    hpoa_version = line.split(':', 1)[1].strip()
        self.config.annotation_provenance['hpoa'] = {
            'url': hpoa_url, 'version': hpoa_version, 'md5': self.md5(wd / 'hpoa.tsv')}

        # KG release tag for the animal annotations
        if source['tag'] is None:
            meta = urllib.request.urlopen(source['metadata_url']).read().decode('utf-8')
            match = re.search(r"^version:\s*'?([0-9-]+)'?", meta, re.MULTILINE)
            if not match:
                raise RuntimeError(f"could not read KG version from {source['metadata_url']}")
            self.config.apply_annotation_tag(f"kg-{match.group(1)}")
        else:
            self.config.apply_annotation_tag(source['tag'])
        logger.info(f"Animal annotations: {self.config.animal_annotations} "
                    f"(tag {self.config.annotation_tag})")

        # Download MPA / ZPA (mouse / zebrafish gene-phenotype annotations)
        for key, taxon in (('mpa', '10090'), ('zpa', '7955')):
            url = f"{source['base_url']}gene_phenotype.{taxon}.tsv.gz"
            logger.info(f"Downloading {key.upper()} from {url}...")
            gz_path = wd / f"{key}.tsv.gz"
            last_modified = self.download_file(url, gz_path)
            prov = {'url': url, 'md5_gz': self.md5(gz_path), 'last_modified': last_modified,
                    'kg': self.config.annotation_tag}
            if source['archive']:
                prov['archive_copy'] = f"{source['archive']}gene_phenotype.{taxon}.tsv.gz"
            self.config.annotation_provenance[key] = prov
            with gzip.open(gz_path, 'rb') as src, open(wd / f"{key}.tsv", 'wb') as dst:
                shutil.copyfileobj(src, dst)
            gz_path.unlink()

        # Preprocess MP and ZP to pairwise (gene, phenotype) associations
        logger.info("Preprocessing association tables...")
        for name, prefix in (('mpa.tsv', 'MP'), ('zpa.tsv', 'ZP')):
            if source['legacy_format']:
                # dipper-era TSV: subject=col 1, object=col 5. Kept exactly as earlier builds did it.
                cmd = f'cut -f1,5 {name} | grep "{prefix}" > {name}.tmp && mv {name}.tmp {name}'
            else:
                # monarch-kg TSV: subject=col 1, negated=col 6, object=col 8; drop header + negated rows.
                cmd = (f"awk -F'\\t' 'NR > 1 && tolower($6) != \"true\" && index($8, \"{prefix}:\") == 1 "
                       f"{{print $1 \"\\t\" $8}}' {name} > {name}.tmp && mv {name}.tmp {name}")
            self.run_command(cmd)
        self.config.save_annotation_state()

    @staticmethod
    def md5(path: Path) -> str:
        h = hashlib.md5()
        with open(path, 'rb') as fh:
            for block in iter(lambda: fh.read(1 << 24), b''):
                h.update(block)
        return h.hexdigest()

    def get_ontology_terms(self, ontology: str, root_term: str, output_prefix: str):
        """Get descendant terms for an ontology."""
        cmd = (
            f"runoak -i sqlite:obo:{ontology.lower()} descendants -p i {root_term} > {output_prefix}_terms.txt && "
            f'sed "s/ [!] /\\t/g" {output_prefix}_terms.txt > {output_prefix}_terms.tsv'
        )

        with ProgressTimer(f"Extracting {ontology} terms from {root_term}"):
            self.run_command(cmd)

    def calculate_information_content(self, association_file: str, association_type: str, output_file: str, ontology: str = 'phenio'):
        """Calculate information content using associations."""
        # Use custom PHENIO if provided, otherwise use default ontology identifier
        if ontology == 'phenio':
            ontology_identifier = self.config.get_phenio_identifier()
        else:
            ontology_identifier = f"sqlite:obo:{ontology}"

        cmd = (
            f"runoak -g {association_file} -G {association_type} -i {ontology_identifier} "
            f"information-content -p i --use-associations .all > {output_file} && "
            f'tail -n +2 "{output_file}" > "{output_file}.tmp" && mv "{output_file}.tmp" "{output_file}"'
        )

        with ProgressTimer(f"Calculating information content from {association_file}"):
            self.run_command(cmd)

    def run_similarity_analysis_ducksim(self, set1_file: str, set2_file: str, ic_file: str,
                                        labels_file: str, output_file: str):
        """Same all-by-all table via DuckDB SQL (validated equal to semsimian); writes labels too."""
        cmd = (
            f"{sys.executable} {DUCKSIM_SCRIPT} --phenio {self.config.get_ducksim_phenio_path()} "
            f"--ic {ic_file} --set1 {set1_file} --set2 {set2_file} --labels {labels_file} "
            f"--out {output_file}.tmp --threshold {self.config.resnik_threshold}"
        )
        with ProgressTimer(f"Similarity analysis (ducksim) -> {output_file}"):
            self.run_command(cmd)
        self.run_command(f'mv "{output_file}.tmp" "{output_file}"')

    def run_similarity_analysis(self, set1_file: str, set2_file: str, ic_file: str, output_file: str):
        """Run semantic similarity analysis using semsimian."""
        phenio_identifier = self.config.get_semsimian_phenio_identifier()

        cmd = (
            f"runoak -i {phenio_identifier} similarity --no-autolabel "
            f"--information-content-file {ic_file} -p i "
            f"--set1-file {set1_file} --set2-file {set2_file} "
            f"-O csv -o {output_file} "
            f"--min-ancestor-information-content {self.config.resnik_threshold}"
        )

        with ProgressTimer(f"Similarity analysis -> {output_file}"):
            self.run_command(cmd)

    def add_labels_with_duckdb(self, similarity_file: str, labels_file: str, output_file: str):
        """Add human-readable labels to similarity results using DuckDB."""
        logger.info(f"Adding labels to {similarity_file}...")

        duckdb_sql = f"""
        CREATE TABLE semsim AS SELECT * FROM read_csv('{similarity_file}', header=TRUE);
        CREATE TABLE labels AS SELECT * FROM read_csv('{labels_file}', header=FALSE);
        CREATE TABLE labeled1 AS SELECT * FROM semsim n JOIN labels r ON (subject_id = column0);
        CREATE TABLE labeled2 AS SELECT * FROM labeled1 n JOIN labels r ON (object_id = r.column0);
        ALTER TABLE labeled2 DROP subject_label;
        ALTER TABLE labeled2 DROP object_label;
        ALTER TABLE labeled2 RENAME column1 TO subject_label;
        ALTER TABLE labeled2 RENAME column1_1 TO object_label;
        ALTER TABLE labeled2 DROP column0;
        ALTER TABLE labeled2 DROP column0_1;
        COPY (SELECT subject_id, subject_label, subject_source, object_id, object_label, object_source, 
              ancestor_id, ancestor_label, ancestor_source, object_information_content, 
              subject_information_content, ancestor_information_content, jaccard_similarity, 
              cosine_similarity, dice_similarity, phenodigm_score FROM labeled2) 
        TO '{output_file}.tmp' WITH (HEADER true, DELIMITER '\\t');
        """

        self.run_command(f'{self.config.duckdb_path} -c "{duckdb_sql}"')
        self.run_command(f'mv "{output_file}.tmp" "{output_file}"')

    def create_log_file(self, name: str, versions: Dict[str, Optional[str]], output_file: str,
                        annotation_key: Optional[str] = None):
        """Create YAML log file with metadata."""
        logger.info(f"Creating log file: {output_file}...")

        log_content = [
            f"name: {name}",
            f"min_ancestor_information_content: {self.config.resnik_threshold}",
            f"engine: {self.config.engine}",
            "versions:"
        ]

        for key, value in versions.items():
            if value:
                log_content.append(f"  {key}: {value}")

        prov = self.config.annotation_provenance.get(annotation_key or '', {})
        if prov:
            log_content.append("annotations:")
            for key, value in prov.items():
                if value:
                    log_content.append(f"  {key}: {json.dumps(value)}")

        log_path = self.config.working_dir / output_file
        log_path.write_text('\n'.join(log_content) + '\n')

    def create_tarball(self, output_name: str, files: List[str]):
        """Create a compressed tarball of results."""
        logger.info(f"Creating tarball: {output_name}...")

        tarball_path = self.config.working_dir / output_name
        with tarfile.open(tarball_path, 'w:gz') as tar:
            for file in files:
                file_path = self.config.working_dir / file
                if file_path.exists():
                    tar.add(file_path, arcname=file)
                    logger.info(f"  Added {file}")
                else:
                    logger.warning(f"  File not found: {file}")

        logger.info(f"Tarball created: {output_name}")

    def upload_results_to_zenodo(self, record_id: str, token: str,
                                 version_name: str, files: List[Path],
                                 base_url: str = "https://zenodo.org/api") -> None:
        """Create a new Zenodo version and upload result files."""
        existing_files = [path for path in files if path.exists()]
        if not existing_files:
            logger.warning("No result files found to upload to Zenodo.")
            return

        logger.info("Creating new Zenodo version draft...")
        client = ZenodoClient(token=token, base_url=base_url)
        draft = client.create_new_version_draft(record_id)
        draft_id = draft["id"]

        logger.info("Clearing files inherited from previous Zenodo version...")
        client.delete_draft_files(draft_id, draft.get("files", []))

        metadata = draft.get("metadata", {})
        if version_name:
            metadata["version"] = version_name

        logger.info(f"Updating Zenodo metadata version to {version_name}...")
        client.update_metadata(draft_id, metadata)

        bucket_url = draft.get("links", {}).get("bucket")
        if not bucket_url:
            raise RuntimeError(
                "Zenodo draft does not include a bucket URL for uploads.")

        for file_path in existing_files:
            logger.info(f"Uploading {file_path.name} to Zenodo...")
            client.upload_file(bucket_url, file_path)

        logger.info("Publishing Zenodo draft...")
        client.publish(draft_id)
        logger.info(f"Zenodo release published (version {version_name}).")

    def run_similarity_comparison(self, ont1: str, ont2: str,
                                  ont1_root: str, ont2_root: str,
                                  ont1_prefix: str, ont2_prefix: str,
                                  association_file: str, association_type: str):
        """
        Run semantic similarity comparison between two ontologies.

        Args:
            ont1: First ontology code (e.g., 'hp')
            ont2: Second ontology code (e.g., 'mp', 'zp', or 'hp' for self-comparison)
            ont1_root: Root term for first ontology (e.g., 'HP:0000118')
            ont2_root: Root term for second ontology (e.g., 'MP:0000001')
            ont1_prefix: Prefix for first ontology files (e.g., 'HPO')
            ont2_prefix: Prefix for second ontology files (e.g., 'MP')
            association_file: Association file for information content (e.g., 'hpoa.tsv', 'mpa.tsv')
            association_type: Association type for oaklib (e.g., 'hpoa', 'g2t')
        """
        # Determine output names from config
        comparison_key = f"{ont1}_vs_{ont2}"
        output_name = getattr(self.config, f"{comparison_key}_name")
        output_prefix = getattr(self.config, f"{comparison_key}_prefix")

        logger.info("=" * 80)
        logger.info(
            f"STAGE: {ont1.upper()} vs {ont2.upper()} Similarity Analysis")
        logger.info("=" * 80)

        # Get terms for first ontology (skip if already done)
        if not (self.config.working_dir / f"{ont1_prefix}_terms.txt").exists():
            self.get_ontology_terms(ont1, ont1_root, ont1_prefix)

        # Get terms for second ontology (if different from first)
        if ont1 != ont2:
            self.get_ontology_terms(ont2, ont2_root, ont2_prefix)
            # Combine term files for labeling
            self.run_command(
                f'cat {ont1_prefix}_terms.tsv {ont2_prefix}_terms.tsv > {ont1_prefix}_{ont2_prefix}_terms.tsv')
            labels_file = f'{ont1_prefix}_{ont2_prefix}_terms.tsv'
        else:
            labels_file = f'{ont1_prefix}_terms.tsv'

        # Calculate information content
        ic_output = f"{ont2.lower()}a_ic.tsv"
        self.calculate_information_content(
            association_file, association_type, ic_output)

        # Run similarity analysis
        similarity_output = f"{output_name}.tsv"
        if self.config.engine == 'ducksim':
            self.run_similarity_analysis_ducksim(
                f'{ont1_prefix}_terms.txt', f'{ont2_prefix}_terms.txt',
                ic_output, labels_file, similarity_output)
        else:
            self.run_similarity_analysis(
                f'{ont1_prefix}_terms.txt',
                f'{ont2_prefix}_terms.txt',
                ic_output,
                similarity_output
            )
            # Add labels
            self.add_labels_with_duckdb(
                similarity_output, labels_file, similarity_output)

        # Create log file with appropriate versions
        versions = {'hp': self.config.hp_version,
                    'phenio': self.config.phenio_version}
        if ont2 != 'hp':
            versions[ont2] = getattr(self.config, f"{ont2}_version")

        annotation_key = 'hpoa' if ont2 == 'hp' else f"{ont2.lower()}a"
        self.create_log_file(output_name, versions, f"{output_name}_log.yaml",
                             annotation_key=annotation_key)

        # Create tarball
        tarball_name = f"{output_prefix}.tsv.tar.gz"
        files = [
            f"{output_name}.tsv",
            f"{output_name}_log.yaml",
            ic_output
        ]
        self.create_tarball(tarball_name, files)

        logger.info(f"{ont1.upper()} vs {ont2.upper()} analysis complete!")

    def run_hp_vs_hp(self):
        """Run HP vs HP similarity comparison."""
        self.run_similarity_comparison(
            ont1='hp', ont2='hp',
            ont1_root='HP:0000118', ont2_root='HP:0000118',
            ont1_prefix='HPO', ont2_prefix='HPO',
            association_file='hpoa.tsv', association_type='hpoa'
        )

    def run_hp_vs_mp(self):
        """Run HP vs MP similarity comparison."""
        self.run_similarity_comparison(
            ont1='hp', ont2='mp',
            ont1_root='HP:0000118', ont2_root='MP:0000001',
            ont1_prefix='HPO', ont2_prefix='MP',
            association_file='mpa.tsv', association_type='g2t'
        )

    def run_hp_vs_zp(self):
        """Run HP vs ZP similarity comparison."""
        self.run_similarity_comparison(
            ont1='hp', ont2='zp',
            ont1_root='HP:0000118', ont2_root='ZP:0000000',
            ont1_prefix='HPO', ont2_prefix='ZP',
            association_file='zpa.tsv', association_type='g2t'
        )

    def setup(self):
        """Run all setup stages."""
        logger.info("=" * 80)
        logger.info("STAGE: Setup")
        logger.info("=" * 80)

        self.setup_working_directory()
        self.install_tools()
        self.get_ontology_versions()
        self.download_association_tables()

        logger.info("Setup complete!")

    def run_all(self):
        """Run the complete pipeline."""
        logger.info("Starting phenotype comparison pipeline...")
        logger.info(f"Working directory: {self.config.working_dir}")
        logger.info(f"Build date: {self.config.build_date}")

        try:
            self.setup()
            self.run_hp_vs_hp()
            self.run_hp_vs_mp()
            self.run_hp_vs_zp()

            logger.info("=" * 80)
            logger.info("PIPELINE COMPLETE!")
            logger.info("=" * 80)
            logger.info(f"Results are in: {self.config.working_dir}")

        except Exception as e:
            logger.error(f"Pipeline failed: {e}")
            raise


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run phenotype comparison pipeline locally",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument(
        '--working-dir',
        type=str,
        default='./working',
        help='Working directory for pipeline execution (default: ./working)'
    )

    parser.add_argument(
        '--comparison',
        type=str,
        choices=['all', 'hp-hp', 'hp-mp', 'hp-zp'],
        default='all',
        help='Which comparison(s) to run (default: all)'
    )

    parser.add_argument(
        '--resnik-threshold',
        type=str,
        default='1.5',
        help='Minimum ancestor information content threshold (default: 1.5)'
    )

    parser.add_argument(
        '--animal-annotations',
        choices=sorted(ANNOTATION_SOURCES),
        default='monarch-kg',
        help='Source of mouse/zebrafish gene-phenotype annotations used for HP-MP / HP-ZP '
             'information content: the current Monarch KG export (default), or the frozen '
             'final dipper-era KG (monarch-kg-2021-09). HP-MP/HP-ZP outputs are tagged '
             '"_kg-<release>". Use a separate --working-dir per source.'
    )
    parser.add_argument(
        '--engine',
        choices=ENGINES,
        default='semsimian',
        help='Similarity engine: semsimian via runoak (default), or ducksim, DuckDB SQL that '
             'reproduces semsimian\'s rows and scores (ties in ancestor_id may differ)'
    )
    parser.add_argument(
        '--custom-phenio',
        type=str,
        help='Path to custom PHENIO Semantic SQL database file (e.g., phenio.db)'
    )

    parser.add_argument(
        '--zenodo-record-id',
        type=str,
        help='Zenodo record ID to version and upload results into'
    )

    parser.add_argument(
        '--zenodo-token',
        type=str,
        help='Zenodo API token (pass at runtime, do not store in config)'
    )

    parser.add_argument(
        '--zenodo-version',
        type=str,
        help='Version name for Zenodo release (default: today YYYY-MM-DD)'
    )

    parser.add_argument(
        '--zenodo-base-url',
        type=str,
        default='https://zenodo.org/api',
        help='Zenodo API base URL (default: https://zenodo.org/api)'
    )

    parser.add_argument(
        '--skip-setup',
        action='store_true',
        help='Skip setup stage (use if already configured)'
    )

    parser.add_argument(
        '--upload-only',
        action='store_true',
        help='Skip setup and comparisons; upload existing tarballs for the selected '
             'comparison(s) to Zenodo (use when comparisons ran as separate jobs)'
    )
    parser.add_argument(
        '--test-mode',
        action='store_true',
        help='Testing mode: download all files but skip similarity comparisons'
    )

    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug logging'
    )

    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Create configuration
    custom_phenio_path = Path(
        args.custom_phenio) if args.custom_phenio else None
    config = PipelineConfig(
        working_dir=Path(args.working_dir),
        custom_phenio=custom_phenio_path,
        animal_annotations=args.animal_annotations,
        engine=args.engine
    )
    config.resnik_threshold = args.resnik_threshold
    zenodo_version = args.zenodo_version or config.release_date

    # Log configuration
    if config.custom_phenio:
        logger.info(f"Using custom PHENIO database: {config.custom_phenio}")
        if not config.custom_phenio.exists():
            logger.error(
                f"Custom PHENIO file not found: {config.custom_phenio}")
            sys.exit(1)

    # Create pipeline runner
    runner = PipelineRunner(config)

    try:
        comparisons_run: List[str] = []

        # Run setup unless skipped
        if args.upload_only:
            logger.info("Upload-only mode: skipping setup and comparisons")
            config.load_annotation_state()
        elif not args.skip_setup:
            runner.setup()
        else:
            logger.info("Skipping setup stage")
            runner.setup_working_directory()
            config.load_annotation_state()
            # Try to load versions from files if they exist
            for ont in ['hp', 'mp', 'zp', 'phenio']:
                version_file = config.working_dir / f"{ont}_version"
                if version_file.exists():
                    setattr(config, f"{ont}_version",
                            version_file.read_text().strip())

        # Run requested comparisons (skip if in test mode)
        if args.upload_only:
            selected = ['hp_vs_hp', 'hp_vs_mp', 'hp_vs_zp'] if args.comparison == 'all' \
                else [args.comparison.replace('-', '_vs_')]
            comparisons_run = selected
        elif args.test_mode:
            logger.info("=" * 80)
            logger.info(
                "TEST MODE: Setup complete, skipping similarity comparisons")
            logger.info("=" * 80)
            logger.info("Downloaded files are ready in the working directory.")
            logger.info(
                "To run comparisons, execute without --test-mode flag.")
        elif args.comparison == 'all':
            runner.run_hp_vs_hp()
            runner.run_hp_vs_mp()
            runner.run_hp_vs_zp()
            comparisons_run = ['hp_vs_hp', 'hp_vs_mp', 'hp_vs_zp']
        elif args.comparison == 'hp-hp':
            runner.run_hp_vs_hp()
            comparisons_run = ['hp_vs_hp']
        elif args.comparison == 'hp-mp':
            runner.run_hp_vs_mp()
            comparisons_run = ['hp_vs_mp']
        elif args.comparison == 'hp-zp':
            runner.run_hp_vs_zp()
            comparisons_run = ['hp_vs_zp']

        if args.test_mode:
            logger.info("Test mode enabled; skipping Zenodo upload.")
        elif args.zenodo_token or args.zenodo_record_id:
            if not (args.zenodo_token and args.zenodo_record_id):
                logger.error(
                    "Both --zenodo-token and --zenodo-record-id are required "
                    "to upload results to Zenodo."
                )
                sys.exit(1)

            tarballs = []
            for comparison in comparisons_run:
                prefix = getattr(config, f"{comparison}_prefix")
                tarballs.append(config.working_dir / f"{prefix}.tsv.tar.gz")

            runner.upload_results_to_zenodo(
                record_id=args.zenodo_record_id,
                token=args.zenodo_token,
                version_name=zenodo_version,
                files=tarballs,
                base_url=args.zenodo_base_url
            )
        else:
            logger.info("Zenodo upload not configured; skipping.")

        logger.info("=" * 80)
        logger.info("SUCCESS! Pipeline completed successfully.")
        logger.info("=" * 80)
        logger.info(f"Results are in: {config.working_dir}")

    except KeyboardInterrupt:
        logger.warning("Pipeline interrupted by user")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Pipeline failed: {e}", exc_info=args.debug)
        sys.exit(1)


if __name__ == '__main__':
    main()
