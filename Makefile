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

all-db: ontologies/phenio-default.db ontologies/phenio-equivalent.db

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
	tar -czf "$(WORKING_DIR)/$*/semsim.tar.gz" \
			-C "$(WORKING_DIR)/$*" \
			HP_vs_MP.tsv HP_vs_HP.tsv HP_vs_ZP.tsv log_sql_generation.yml
	@if [ -f "$(WORKING_DIR)/$*/semsim.tar.gz" ]; then \
		rm -f "$(WORKING_DIR)/$*/"HP_vs_{MP,HP,ZP}.tsv; \
	else \
		echo "❌ Failed to create semsim.tar.gz"; \
		exit 1; \
	fi

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
	tar -czf "$(WORKING_DIR)/semsim-ols-cosinemegatron/semsim.tar.gz" \
			-C "$(WORKING_DIR)/semsim-ols-cosinemegatron" \
			HP_vs_MP.tsv HP_vs_HP.tsv HP_vs_ZP.tsv log_sql_generation.yml
	@if [ -f "$(WORKING_DIR)/semsim-ols-cosinemegatron/semsim.tar.gz" ]; then \
		rm -f "$(WORKING_DIR)/semsim-ols-cosinemegatron/"HP_vs_{MP,HP,ZP}.tsv; \
	else \
		echo "❌ Failed to create semsim.tar.gz"; \
		exit 1; \
	fi

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
	tar -czf "$(WORKING_DIR)/semsim-ols-cosinetextsmall/semsim.tar.gz" \
			-C "$(WORKING_DIR)/semsim-ols-cosinetextsmall" \
			HP_vs_MP.tsv HP_vs_HP.tsv HP_vs_ZP.tsv log_sql_generation.yml
	@if [ -f "$(WORKING_DIR)/semsim-ols-cosinetextsmall/semsim.tar.gz" ]; then \
		rm -f "$(WORKING_DIR)/semsim-ols-cosinetextsmall/"HP_vs_{MP,HP,ZP}.tsv; \
	else \
		echo "❌ Failed to create semsim.tar.gz"; \
		exit 1; \
	fi


all-semsim: \
	semsim-phenio-default \
	semsim-phenio-equivalent \
	semsim-ols-cosinemegatron \
	semsim-ols-cosinetextsmall

# Generate SQL files from semantic similarity results
# Creates: working/<run-name>/HP_vs_*_semsimian_phenio_exomiser.sql
# Usage: make exomiser-sql-semsim-phenio-default
exomiser-sql-%: $(WORKING_DIR)/%/semsim.tar.gz
	@if [ -f "$(WORKING_DIR)/$*/sql.tar.gz" ]; then \
		echo "⚠️  Skipping: $(WORKING_DIR)/$*/sql.tar.gz already exists."; \
	else \
		echo "Unpacking semantic similarity results from $(WORKING_DIR)/$*/semsim.tar.gz..."; \
		tar -xzf "$(WORKING_DIR)/$*/semsim.tar.gz" \
			-C "$(WORKING_DIR)/$*"; \
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
		echo "📊 Checking if SQL files where correctly created..."; \
		if 	[ -f "$(WORKING_DIR)/$*/HP_vs_MP.sql" ] && \
			[ -f "$(WORKING_DIR)/$*/HP_vs_HP.sql" ] && \
			[ -f "$(WORKING_DIR)/$*/HP_vs_ZP.sql" ] && \
			[ -f "$(WORKING_DIR)/$*/log_sql_generation.yml" ]; then \
			tar -czf "$(WORKING_DIR)/$*/sql.tar.gz" \
				-C "$(WORKING_DIR)/$*" \
				HP_vs_MP.sql HP_vs_HP.sql HP_vs_ZP.sql log_sql_generation.yml; \
			rm -f "$(WORKING_DIR)/$*/"HP_vs_{MP,HP,ZP}.{sql,tsv}; \
		else \
			echo "❌ Error: One or more SQL files were not created successfully."; \
			exit 1; \
		fi; \
	fi

all-sql: \
	exomiser-sql-semsim-phenio-default \
	exomiser-sql-semsim-phenio-equivalent \
	exomiser-sql-semsim-ols-cosinemegatron \
	exomiser-sql-semsim-ols-cosinetextsmall

# Import SQL files from sql.tar.gz into H2 database
# Usage: make import-h2-semsim-phenio-default H2_DB=/path/to/database.mv.db
# Requires: H2 JDBC driver jar file and Java
H2_DB ?= $(WORKING_DIR)/exomiser/current/2406_phenotype/2406_phenotype.mv.db
H2_JAR ?= $(WORKING_DIR)/h2.jar
H2_USER ?=
H2_PASSWORD ?=

h2-%: $(WORKING_DIR)/%/sql.tar.gz
	@echo "🔧 Importing SQL files from $< into H2 database"
	@if [ -f "$(WORKING_DIR)/$*/phenotype.mv.db" ]; then \
		echo "❌ Error: $(WORKING_DIR)/$*/phenotype.mv.db already exists. Please delete manually."; \
		exit 1; \
	fi
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
	@echo "🔧 Copying exomiser database from $(H2_DB) to $(WORKING_DIR)/$*/phenotype.mv.db..."
	@cp $(H2_DB) $(WORKING_DIR)/$*/phenotype.mv.db
	@echo "✅ Copying exomiser database from $(H2_DB) to $(WORKING_DIR)/$*/phenotype.mv.db..."
	@# Extract SQL files to temporary directory
	@mkdir -p $(WORKING_DIR)/$*/sql_unpacked
	@tar -xzf $< -C $(WORKING_DIR)/$*/sql_unpacked
	@echo "✅ Extracted SQL files"
	@# TEMPORARY HACK: Fix reversed table names (MP_HP -> HP_MP, ZP_HP -> HP_ZP)
	@# Only process first 3 lines (TRUNCATE and INSERT INTO statements) for speed
	@echo "🔧 Fixing reversed table names in SQL files..."
	@for sql_file in $(WORKING_DIR)/$*/sql_unpacked/*.sql; do \
		sed -i.bak '1,3s/EXOMISER\.MP_HP_MAPPINGS/EXOMISER.HP_MP_MAPPINGS/g' "$$sql_file"; \
		sed -i.bak '1,3s/EXOMISER\.ZP_HP_MAPPINGS/EXOMISER.HP_ZP_MAPPINGS/g' "$$sql_file"; \
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
	@# Compact database to reclaim space from TRUNCATE and optimize layout
	@echo "🔧 Compacting database..."
	@db_abs_path=$$(cd $(WORKING_DIR)/$* && pwd)/phenotype; \
	jdbc_url="jdbc:h2:file:$$db_abs_path"; \
	java -Xms128m -Xmx8192m -Dh2.bindAddress=127.0.0.1 \
		-cp $(H2_JAR) org.h2.tools.Shell \
		-url "$$jdbc_url" \
		-user "sa" \
		-password "" \
		-sql "SHUTDOWN COMPACT;" > /dev/null 2>&1; \
	if [ $$? -eq 0 ]; then \
		echo "✅ Database compacted successfully"; \
	else \
		echo "⚠️  Warning: Compact operation failed (non-fatal)"; \
	fi
	@echo "📊 Final database size:"
	@ls -lh $(WORKING_DIR)/$*/phenotype.mv.db
	@# Clean up temporary files (keep the tar.gz archive)
	@rm -rf $(WORKING_DIR)/$*/sql_unpacked
	@echo "🧹 Cleaned up temporary files (kept sql.tar.gz)"

all-h2: \
	h2-semsim-phenio-default \
	h2-semsim-phenio-equivalent \
	h2-semsim-ols-cosinemegatron \
	h2-semsim-ols-cosinetextsmall

# Clean working directory
clean:
	rm -rf $(WORKING_DIR)
	mkdir -p $(WORKING_DIR)
