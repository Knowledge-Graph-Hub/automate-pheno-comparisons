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
import gzip
import logging
import os
import platform
import shutil
import subprocess
import sys
import tarfile
import threading
import time
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


class PipelineConfig:
    """Configuration for the phenotype comparison pipeline."""

    def __init__(self, working_dir: Path, custom_phenio: Optional[Path] = None):
        # Convert to absolute path immediately to avoid issues with os.chdir
        self.working_dir = Path(working_dir).absolute()
        self.custom_phenio = Path(
            custom_phenio).absolute() if custom_phenio else None

        # Date-based naming
        self.build_date = datetime.now().strftime('%Y%m%d')

        # Pipeline parameters
        self.resnik_threshold = '1.5'

        # Output prefixes
        self.hp_vs_hp_prefix = "HP_vs_HP_semsimian_phenio"
        self.hp_vs_mp_prefix = "HP_vs_MP_semsimian_phenio"
        self.hp_vs_zp_prefix = "HP_vs_ZP_semsimian_phenio"

        # Output names with date
        self.hp_vs_hp_name = f"{self.hp_vs_hp_prefix}_{self.build_date}"
        self.hp_vs_mp_name = f"{self.hp_vs_mp_prefix}_{self.build_date}"
        self.hp_vs_zp_name = f"{self.hp_vs_zp_prefix}_{self.build_date}"

        # Ontology versions (will be populated during setup)
        self.hp_version: Optional[str] = None
        self.mp_version: Optional[str] = None
        self.zp_version: Optional[str] = None
        self.phenio_version: Optional[str] = None

        # Tools
        self.duckdb_path = self.working_dir / 'duckdb'
        self.yq_path = self.working_dir / 'yq'

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

    def download_file(self, url: str, output_path: Path, chunk_size: int = 8192) -> None:
        """
        Download a file from URL to output path using Python urllib.

        Args:
            url: URL to download from
            output_path: Path where to save the file
            chunk_size: Size of chunks to read at a time
        """
        logger.info(f"Downloading {url}...")
        try:
            with urllib.request.urlopen(url) as response:
                with open(output_path, 'wb') as out_file:
                    while True:
                        chunk = response.read(chunk_size)
                        if not chunk:
                            break
                        out_file.write(chunk)
            logger.debug(f"Downloaded to {output_path}")
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

        # Detect platform
        system = platform.system().lower()
        machine = platform.machine().lower()

        # Map platform to DuckDB and yq naming conventions
        if system == "darwin":
            duckdb_platform = "osx-universal"
            if machine == "arm64":
                yq_platform = "darwin_arm64"
            else:
                yq_platform = "darwin_amd64"
        elif system == "linux":
            if machine in ["x86_64", "amd64"]:
                duckdb_platform = "linux-amd64"
                yq_platform = "linux_amd64"
            elif machine in ["aarch64", "arm64"]:
                duckdb_platform = "linux-aarch64"
                yq_platform = "linux_arm64"
            else:
                raise RuntimeError(f"Unsupported architecture: {machine}")
        else:
            raise RuntimeError(f"Unsupported platform: {system}")

        # Install DuckDB
        if not self.config.duckdb_path.exists():
            logger.info(f"Downloading DuckDB for {system} ({machine})...")
            duckdb_url = f"https://github.com/duckdb/duckdb/releases/download/v0.10.3/duckdb_cli-{duckdb_platform}.zip"
            self.download_and_extract_zip(duckdb_url, self.config.working_dir)
            self.run_command(f"chmod +x {self.config.duckdb_path}")
            logger.info("DuckDB installed")
        else:
            logger.info("DuckDB already installed")

        # Install yq
        if not self.config.yq_path.exists():
            logger.info(f"Downloading yq for {system} ({machine})...")
            yq_url = f"https://github.com/mikefarah/yq/releases/download/v4.48.1/yq_{yq_platform}"
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
                f'{self.config.yq_path} eval \'.[\"owl:versionIRI\"][0]\' - > {key}_version'
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

        # Download HPOA (Human Phenotype Ontology Annotations)
        logger.info("Downloading HPOA...")
        hpoa_url = "http://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa"
        self.download_file(hpoa_url, self.config.working_dir / 'hpoa.tsv')

        # Download MPA (Mouse Phenotype Annotations)
        logger.info("Downloading MPA...")
        mpa_url = "https://data.monarchinitiative.org/dipper-kg/final/tsv/gene_associations/gene_phenotype.10090.tsv.gz"
        self.download_and_decompress_gzip(
            mpa_url, self.config.working_dir / 'mpa.tsv')

        # Download ZPA (Zebrafish Phenotype Annotations)
        logger.info("Downloading ZPA...")
        zpa_url = "https://data.monarchinitiative.org/dipper-kg/final/tsv/gene_associations/gene_phenotype.7955.tsv.gz"
        self.download_and_decompress_gzip(
            zpa_url, self.config.working_dir / 'zpa.tsv')

        # Preprocess MP and ZP to pairwise associations
        logger.info("Preprocessing association tables...")
        self.run_command(
            'cut -f1,5 mpa.tsv | grep "MP" > mpa.tsv.tmp && mv mpa.tsv.tmp mpa.tsv')
        self.run_command(
            'cut -f1,5 zpa.tsv | grep "ZP" > zpa.tsv.tmp && mv zpa.tsv.tmp zpa.tsv')

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

    def create_log_file(self, name: str, versions: Dict[str, Optional[str]], output_file: str):
        """Create YAML log file with metadata."""
        logger.info(f"Creating log file: {output_file}...")

        log_content = [
            f"name: {name}",
            f"min_ancestor_information_content: {self.config.resnik_threshold}",
            "versions:"
        ]

        for key, value in versions.items():
            if value:
                log_content.append(f"  {key}: {value}")

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

        self.create_log_file(output_name, versions, f"{output_name}_log.yaml")

        # Create tarball
        tarball_name = f"{output_prefix}.tar.gz"
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
        '--custom-phenio',
        type=str,
        help='Path to custom PHENIO Semantic SQL database file (e.g., phenio.db)'
    )

    parser.add_argument(
        '--skip-setup',
        action='store_true',
        help='Skip setup stage (use if already configured)'
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
        custom_phenio=custom_phenio_path
    )
    config.resnik_threshold = args.resnik_threshold

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
        # Run setup unless skipped
        if not args.skip_setup:
            runner.setup()
        else:
            logger.info("Skipping setup stage")
            runner.setup_working_directory()
            # Try to load versions from files if they exist
            for ont in ['hp', 'mp', 'zp', 'phenio']:
                version_file = config.working_dir / f"{ont}_version"
                if version_file.exists():
                    setattr(config, f"{ont}_version",
                            version_file.read_text().strip())

        # Run requested comparisons (skip if in test mode)
        if args.test_mode:
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
        elif args.comparison == 'hp-hp':
            runner.run_hp_vs_hp()
        elif args.comparison == 'hp-mp':
            runner.run_hp_vs_mp()
        elif args.comparison == 'hp-zp':
            runner.run_hp_vs_zp()

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
