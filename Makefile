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
semsim-phenio-%:
	$(RUN) run_pipeline.py \
		--run-name $@ \
		--working-dir $(WORKING_DIR) \
		--resnik-threshold $(RESNIK_THRESHOLD) \
		--custom-phenio ontologies/phenio-$*.db \
		--comparison all

semsim-ols-cosinemegatron:
	mkdir -p $(WORKING_DIR)/semsim-ols-cosinemegatron
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim/hp_zp__llama-embed-nemotron-8b.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_zp__llama-embed-nemotron-8b.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_zp__llama-embed-nemotron-8b.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_zp__llama-embed-nemotron-8b.tsv $(WORKING_DIR)/$@/HP_vs_ZP.tsv
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim/hp_mp__llama-embed-nemotron-8b.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_mp__llama-embed-nemotron-8b.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_mp__llama-embed-nemotron-8b.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_mp__llama-embed-nemotron-8b.tsv $(WORKING_DIR)/$@/HP_vs_MP.tsv
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim/hp_hp__llama-embed-nemotron-8b.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_hp__llama-embed-nemotron-8b.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_hp__llama-embed-nemotron-8b.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinemegatron/hp_hp__llama-embed-nemotron-8b.tsv $(WORKING_DIR)/$@/HP_vs_HP.tsv

semsim-ols-cosinetextsmall:
	mkdir -p $(WORKING_DIR)/semsim-ols-cosinetextsmall
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim_text-embedding-3-small/hp_hp__text-embedding-3-small.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_hp__text-embedding-3-small.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_hp__text-embedding-3-small.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_hp__text-embedding-3-small.tsv $(WORKING_DIR)/$@/HP_vs_HP.tsv
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim_text-embedding-3-small/hp_mp__text-embedding-3-small.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_mp__text-embedding-3-small.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_mp__text-embedding-3-small.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_mp__text-embedding-3-small.tsv $(WORKING_DIR)/$@/HP_vs_MP.tsv
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim_text-embedding-3-small/hp_zp__text-embedding-3-small.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_zp__text-embedding-3-small.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_zp__text-embedding-3-small.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinetextsmall/hp_zp__text-embedding-3-small.tsv $(WORKING_DIR)/$@/HP_vs_ZP.tsv

# TODO rename tables
# Generate SQL file from semantic similarity results
# Creates: working/<run-name>/HP_vs_MP_semsimian_phenio_exomiser.sql
sql-%: working/%/HP_vs_MP.tsv
	$(RUN) monarch-semsim semsim-to-exomisersql \
		--input-file workingc/$*/HP_vs_MP.tsv \
		--subject-prefix HP \
		--object-prefix MP \
		--threshold 0.5 \
		--output workingc/$*/HP_vs_MP_semsimian_phenio_exomiser.sql
	$(RUN) monarch-semsim semsim-to-exomisersql \
		--input-file workingc/$*/HP_vs_HP.tsv \
		--subject-prefix HP \
		--object-prefix HP \
		--threshold 0.5 \
		--output workingc/$*/HP_vs_HP_semsimian_phenio_exomiser.sql
	$(RUN) monarch-semsim semsim-to-exomisersql \
		--input-file workingc/$*/HP_vs_ZP.tsv \
		--subject-prefix HP \
		--object-prefix ZP \
		--threshold 0.5 \
		--output workingc/$*/HP_vs_ZP_semsimian_phenio_exomiser.sql
	echo "Generated Exomiser SQL files on $(date)" > workingc/$*/log_sql_generation.txt

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
	@echo "  make clean                                      # Clean up working directory"
