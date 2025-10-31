.PHONY: help

# Default values from Jenkinsfile
WORKING_DIR ?= ./working
RESNIK_THRESHOLD ?= 1.5
PYTHON ?= python3

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
	mkdir -p $(WORKING_DIR)
	$(PYTHON) run_pipeline.py \
		--working-dir $(WORKING_DIR) \
		--resnik-threshold $(RESNIK_THRESHOLD) \
		--test-mode

# Run with custom PHENIO database
custom-phenio-%:
	$(PYTHON) run_pipeline.py \
		--working-dir $(WORKING_DIR) \
		--resnik-threshold $(RESNIK_THRESHOLD) \
		--custom-phenio ontologies/phenio-$*.db \
		--comparison hp-mp

# Clean working directory
clean:
	rm -rf $(WORKING_DIR)

# Display help
help:
	@echo "Phenotype Comparison Pipeline Makefile"
	@echo ""
	@echo "make download-ontologies: Download all configured ontologies"
	@echo "make prepare-dbs: Prepare databases from downloaded ontologies"
	@echo ""
	@echo ""
	@echo "Variables:"
	@echo "  WORKING_DIR       - Working directory (default: ./working)"
	@echo "  RESNIK_THRESHOLD  - Min ancestor information content (default: 1.5)"
	@echo "  PYTHON            - Python interpreter (default: python3)"
	@echo "  PHENIO_DB         - Path to custom PHENIO database (for custom-phenio target)"
	@echo ""
	@echo "Examples:"
	@echo "  make                                    # Run full pipeline"
	@echo "  make hp-hp                              # Run HP vs HP only"
	@echo "  make RESNIK_THRESHOLD=2.0               # Use custom threshold"
	@echo "  make custom-phenio PHENIO_DB=my.db      # Use custom PHENIO"
	@echo "  make clean                              # Clean up working directory"
