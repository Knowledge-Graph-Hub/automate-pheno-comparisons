.PHONY: help

# Default values from Jenkinsfile
WORKING_DIR ?= ./working
RESNIK_THRESHOLD ?= 1.5
RUN ?= uv run

help:
	@echo "Phenotype Comparison Pipeline Makefile"
	@echo "make download-ontologies: Download all configured ontologies"
	@echo "make prepare-dbs: Prepare databases from downloaded ontologies"

download-ontologies: prepare-phenio-default prepare-phenio-equivalent ontologies/phenio-equivalent.owl

prepare-phenio-default:
	mkdir -p tmp ontologies
	wget https://github.com/monarch-initiative/phenio/releases/download/v2025-10-12/phenio.owl.gz -O tmp/phenio.owl.gz
	gunzip tmp/phenio.owl.gz
	mv tmp/phenio.owl ontologies/phenio-default.owl

prepare-phenio-equivalent:
	mkdir -p tmp ontologies
	wget https://github.com/monarch-initiative/phenio/releases/download/v2025-10-12/phenio-sspo-equivalent.owl.gz -O tmp/phenio-equivalent.owl.gz
	gunzip tmp/phenio-equivalent.owl.gz
	mv tmp/phenio-equivalent.owl ontologies/phenio-equivalent.owl

%.db: %.owl
	@rm -f $*.db
	@rm -f .template.db
	@rm -f .template.db.tmp
	@rm -f $*-relation-graph.tsv.gz
	RUST_BACKTRACE=full semsql make $*.db -P config/prefixes.csv
	@rm -f .template.db
	@rm -f .template.db.tmp
	@rm -f $*-relation-graph.tsv.gz
	@test -f $*.db || (echo "Error: File not found!" && exit 1)

prepare-dbs: ontologies/phenio-default.db ontologies/phenio-equivalent.db

# Run setup only (downloads tools and data)
setup:
	$(RUN) run_pipeline.py \
		--run-name $@ \
		--working-dir $(WORKING_DIR) \
		--resnik-threshold $(RESNIK_THRESHOLD) \
		--test-mode

# Run with custom PHENIO database
custom-phenio-%:
	$(RUN) run_pipeline.py \
		--run-name $@ \
		--working-dir $(WORKING_DIR) \
		--resnik-threshold $(RESNIK_THRESHOLD) \
		--custom-phenio ontologies/phenio-$*.db \
		--comparison all

# Generate SQL file from semantic similarity results
# Creates: working/<run-name>/HP_vs_MP_semsimian_phenio_exomiser.sql
sql-%: working/%/HP_vs_MP_semsimian_phenio.tsv
	$(RUN) monarch-semsim semsim-to-exomisersql \
		--input-file working/$*/HP_vs_MP_semsimian_phenio.tsv \
		--subject-prefix HP \
		--object-prefix MP \
		--output working/$*/HP_vs_MP_semsimian_phenio_exomiser.sql
	$(RUN) monarch-semsim semsim-to-exomisersql \
		--input-file working/$*/HP_vs_HP_semsimian_phenio.tsv \
		--subject-prefix HP \
		--object-prefix HP \
		--output working/$*/HP_vs_HP_semsimian_phenio_exomiser.sql
	$(RUN) monarch-semsim semsim-to-exomisersql \
		--input-file working/$*/HP_vs_ZP_semsimian_phenio.tsv \
		--subject-prefix HP \
		--object-prefix ZP \
		--output working/$*/HP_vs_ZP_semsimian_phenio_exomiser.sql
	echo "Generated Exomiser SQL files on $(date)" > working/$*/log_sql_generation.txt

# Clean working directory
clean:
	rm -rf $(WORKING_DIR)
	mkdir -p $(WORKING_DIR)

# Display help
help:
	@echo "Phenotype Comparison Pipeline Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  download-ontologies        - Download all configured ontologies"
	@echo "  prepare-dbs                - Prepare databases from downloaded ontologies"
	@echo "  setup                      - Run setup only (downloads tools and data)"
	@echo "  custom-phenio-<name>       - Run pipeline with custom PHENIO database"
	@echo "  sql_<run-name>             - Generate Exomiser SQL from similarity results"
	@echo "  clean                      - Clean up working directory"
	@echo ""
	@echo "Variables:"
	@echo "  WORKING_DIR       - Working directory (default: ./working)"
	@echo "  RESNIK_THRESHOLD  - Min ancestor information content (default: 1.5)"
	@echo "  RUN               - Command prefix (default: uv run)"
	@echo ""
	@echo "Examples:"
	@echo "  make setup                                      # Setup tools and data"
	@echo "  make custom-phenio-default                      # Run with default PHENIO"
	@echo "  make custom-phenio-equivalent                   # Run with equivalent PHENIO"
	@echo "  make sql_custom-phenio-default                  # Generate SQL from results"
	@echo "  make RESNIK_THRESHOLD=2.0 custom-phenio-default # Use custom threshold"
	@echo "  make clean                                      # Clean up working directory"
