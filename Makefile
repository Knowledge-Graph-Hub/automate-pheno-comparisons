.PHONY: help

# Default values from Jenkinsfile
WORKING_DIR ?= ./working
RESNIK_THRESHOLD ?= 1.5
RUN ?= uv run
THRESHOLD ?= 0.4
BATCH_SIZE ?= 100000

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

# Generate SQL files from semantic similarity results
# Creates: working/<run-name>/HP_vs_*_semsimian_phenio_exomiser.sql
# Usage: make exomiser-sql-semsim-phenio-default
exomiser-sql-%: $(WORKING_DIR)/%/HP_vs_MP.tsv
	@if [ -f "$(WORKING_DIR)/$*/sql_generation.tar.gz" ]; then \
		echo "⚠️  Skipping: $(WORKING_DIR)/$*/sql_generation.tar.gz already exists."; \
	else \
		echo "🔧 Generating SQL files for run: $*"; \
		echo "   Using threshold: $(THRESHOLD), batch size: $(BATCH_SIZE)"; \
		\
		for pair in HP_vs_MP HP_vs_HP HP_vs_ZP; do \
			subject=$${pair%%_vs_*}; \
			object=$${pair##*_vs_}; \
			$(RUN) monarch-semsim semsim-to-exomisersql \
				--input-file "$(WORKING_DIR)/$*/$${pair}.tsv" \
				--subject-prefix "$$object" \
				--object-prefix "$$subject" \
				--threshold "$(THRESHOLD)" \
				--batch-size "$(BATCH_SIZE)" \
				--output "$(WORKING_DIR)/$*/$${pair}.sql"; \
		done; \
		\
		logfile="$(WORKING_DIR)/$*/log_sql_generation.yml"; \
		{ \
			echo "date: $$(date)"; \
			echo "semsim_threshold: $(THRESHOLD)"; \
			echo "resnik_threshold: $(RESNIK_THRESHOLD)"; \
			echo "flavour: $*"; \
			[ -f "$(WORKING_DIR)/$*/phenio_version" ] && echo "phenio: $$(cat $(WORKING_DIR)/$*/phenio_version)"; \
			[ -f "$(WORKING_DIR)/$*/hp_version" ] && echo "hp: $$(cat $(WORKING_DIR)/$*/hp_version)"; \
			[ -f "$(WORKING_DIR)/$*/mp_version" ] && echo "mp: $$(cat $(WORKING_DIR)/$*/mp_version)"; \
			[ -f "$(WORKING_DIR)/$*/zp_version" ] && echo "zp: $$(cat $(WORKING_DIR)/$*/zp_version)"; \
		} > "$$logfile"; \
		\
		echo "✅ SQL files generated successfully in $(WORKING_DIR)/$*/"; \
		tar -czf "$(WORKING_DIR)/$*/sql_generation.tar.gz" \
			-C "$(WORKING_DIR)/$*" \
			HP_vs_MP.sql HP_vs_HP.sql HP_vs_ZP.sql log_sql_generation.yml; \
		rm -f "$(WORKING_DIR)/$*/"HP_vs_{MP,HP,ZP}.sql; \
	fi



all-sql: \
	exomiser-sql-semsim-phenio-default \
	exomiser-sql-semsim-phenio-equivalent \
	exomiser-sql-semsim-ols-cosinemegatron \
	exomiser-sql-semsim-ols-cosinetextsmall

# Import SQL files from sql_generation.tar.gz into H2 database
# Usage: make import-h2-semsim-phenio-default H2_DB=/path/to/database.mv.db
# Requires: H2 JDBC driver jar file and Java
H2_DB ?= $(WORKING_DIR)/exomiser/current/2406_phenotype/2406_phenotype.mv.db
H2_JAR ?= $(WORKING_DIR)/h2.jar
H2_USER ?=
H2_PASSWORD ?=

import-h2-%: $(WORKING_DIR)/%/sql_generation.tar.gz
	@echo "🔧 Importing SQL files from $< into H2 database"
	@echo "   Root database (will copy): $(H2_DB)"
	@if [ ! -f "$(H2_JAR)" ]; then \
		echo "❌ Error: H2 JDBC driver not found at $(H2_JAR)"; \
		echo "   Download with: curl -L -o $(H2_JAR) https://repo1.maven.org/maven2/com/h2database/h2/2.2.224/h2-2.2.224.jar"; \
		exit 1; \
	fi
	@if [ ! -f "$(H2_DB)" ]; then \
		echo "❌ Error: H2 database not found at $(H2_DB)"; \
		echo "   Set H2_DB variable to point to your database file"; \
		exit 1; \
	fi
	@cp $(H2_DB) $(WORKING_DIR)/$*/phenotype.mv.db
	@# Extract SQL files to temporary directory
	@mkdir -p $(WORKING_DIR)/$*/sql_unpacked
	@tar -xzf $< -C $(WORKING_DIR)/$*/sql_unpacked
	@echo "✅ Extracted SQL files"
	@# TEMPORARY HACK: Fix reversed table names (MP_HP -> HP_MP, ZP_HP -> HP_ZP)
	@echo "🔧 Fixing reversed table names in SQL files..."
	@for sql_file in $(WORKING_DIR)/$*/sql_unpacked/*.sql; do \
		sed -i.bak 's/EXOMISER\.MP_HP_MAPPINGS/EXOMISER.HP_MP_MAPPINGS/g' "$$sql_file"; \
		sed -i.bak 's/EXOMISER\.ZP_HP_MAPPINGS/EXOMISER.HP_ZP_MAPPINGS/g' "$$sql_file"; \
		rm -f "$${sql_file}.bak"; \
	done
	@echo "✅ Table names fixed"
	@# IMPORTANT: H2 requires absolute paths in JDBC URL
	@db_abs_path=$$(cd $(WORKING_DIR)/$* && pwd)/phenotype; \
	jdbc_url="jdbc:h2:file:$$db_abs_path"; \
	echo "   JDBC URL: $$jdbc_url"; \
	echo "   Using credentials: user='sa', password='' (H2 default)"; \
	\
	for sql_file in $(WORKING_DIR)/$*/sql_unpacked/*.sql; do \
		echo "📥 Importing $$(basename $$sql_file)..."; \
		java -Xms128m -Xmx8192m -Dh2.bindAddress=127.0.0.1 \
			-cp $(H2_JAR) org.h2.tools.RunScript \
			-url "$$jdbc_url" \
			-script "$$sql_file" \
			-user "sa" \
			-password ""; \
		if [ $$? -eq 0 ]; then \
			echo "   ✅ Successfully imported $$(basename $$sql_file)"; \
		else \
			echo "   ❌ Failed to import $$(basename $$sql_file)"; \
			exit 1; \
		fi; \
	done
	@echo "✅ All SQL files imported successfully"
	@# Clean up temporary files (keep the tar.gz archive)
	@rm -rf $(WORKING_DIR)/$*/sql_unpacked
	@echo "🧹 Cleaned up temporary files (kept sql_generation.tar.gz)"

# Clean working directory
clean:
	rm -rf $(WORKING_DIR)
	mkdir -p $(WORKING_DIR)

# Display help
help:
	@echo "Phenotype Comparison Pipeline Makefile"
	@echo ""
	@echo "=== Setup Targets ==="
	@echo "  download-ontologies        - Download all configured ontologies"
	@echo "  prepare-dbs                - Prepare databases from downloaded ontologies"
	@echo "  setup                      - Run setup only (downloads tools and data)"
	@echo ""
	@echo "=== Pipeline Targets ==="
	@echo "  semsim-phenio-<name>       - Run pipeline with custom PHENIO database"
	@echo "  semsim-ols-cosinemegatron  - Download OLS cosine similarity data (nemotron)"
	@echo "  semsim-ols-cosinetextsmall - Download OLS cosine similarity data (text-small)"
	@echo ""
	@echo "=== Exomiser Integration ==="
	@echo "  exomiser-sql-<run-name>    - Generate SQL files from similarity results for H2 database import"
	@echo "  import-h2-<run-name>       - Import SQL files from sql_generation.tar.gz into H2 database"
	@echo "  all-sql                    - Generate SQL files for all runs"
	@echo ""
	@echo "=== Maintenance ==="
	@echo "  clean                      - Clean up working directory"
	@echo ""
	@echo "=== Configuration Variables ==="
	@echo "  WORKING_DIR       - Working directory (default: ./working)"
	@echo "  RESNIK_THRESHOLD  - Min ancestor information content (default: 1.5)"
	@echo "  RUN               - Command prefix (default: uv run)"
	@echo "  THRESHOLD         - Minimum score threshold for filtering (default: 0.4)"
	@echo "  BATCH_SIZE        - Number of rows per batch (default: 100000)"
	@echo "  H2_DB             - Path to H2 database file for import"
	@echo "                      (default: ./working/exomiser/current/2406_phenotype/2406_phenotype.mv.db)"
	@echo "  H2_JAR            - Path to H2 JDBC driver jar (default: ./working/h2.jar)"
	@echo "  H2_USER           - H2 database username (default: empty, no auth)"
	@echo "  H2_PASSWORD       - H2 database password (default: empty)"
	@echo ""
	@echo "=== Examples ==="
	@echo "  # Setup"
	@echo "  make setup"
	@echo ""
	@echo "  # Generate SQL files for Exomiser"
	@echo "  make exomiser-sql-semsim-phenio-default"
	@echo "  make exomiser-sql-semsim-phenio-default THRESHOLD=0.7 BATCH_SIZE=50000"
	@echo ""
	@echo "  # Import SQL files into H2 database"
	@echo "  # First, download H2 JDBC driver:"
	@echo "  curl -L -o working/h2.jar https://repo1.maven.org/maven2/com/h2database/h2/2.2.224/h2-2.2.224.jar"
	@echo ""
	@echo "  # Then import (no authentication by default):"
	@echo "  make import-h2-semsim-phenio-default"
	@echo "  make import-h2-semsim-phenio-default H2_DB=/path/to/your/database.mv.db"
	@echo ""
	@echo "  # If your database has authentication:"
	@echo "  make import-h2-semsim-phenio-default H2_USER=sa H2_PASSWORD=yourpass"
	@echo ""
	@echo "  # Clean up"
	@echo "  make clean"
	@echo ""
