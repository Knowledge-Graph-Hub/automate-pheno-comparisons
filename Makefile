.PHONY: help


#https://github.com/exomiser/Exomiser/blob/master/exomiser-data-phenotype/src/main/resources/db/migration/h2/V3.5__Insert_hp_hp_mappings.sql 

# Default values from Jenkinsfile
WORKING_DIR ?= ./working
RUN ?= uv run
SHELL := /bin/bash -eu -o pipefail

download-phenotype-db:
	wget "https://g-879a9f.f5dc97.75bc.dn.glob.us/data/2508_phenotype.zip" -O "$(WORKING_DIR)/exomiser/current/2508_phenotype.zip"
	unzip "$(WORKING_DIR)/exomiser/current/2508_phenotype.zip" -d "$(WORKING_DIR)/exomiser/current/"

download-ontologies: prepare-phenio-default prepare-phenio-equivalent ontologies/phenio-equivalent.owl

# phenodigm threshold might be random? its not betwen 0-1. NO THRESHOLD!
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

RESNIK_THRESHOLD ?= 1.5

# Run with custom PHENIO database
semsim-phenio-%:
	$(RUN) run_pipeline.py \
		--run-name $@ \
		--working-dir $(WORKING_DIR) \
		--resnik-threshold $(RESNIK_THRESHOLD) \
		--custom-phenio ontologies/phenio-$*.db \
		--comparison all
	# TODO The next line exists so I can test changes to this goal w/o rerunning semsim pipeline
	# @tar -xzf "$(WORKING_DIR)/$@/semsim.tar.gz" -C "$(WORKING_DIR)/$@"
	@echo "🔧 Subsetting TSV files to key columns..."
	@for pair in HP_vs_MP HP_vs_HP HP_vs_ZP; do \
		$(RUN) python3 -c "import polars as pl; df = pl.read_csv('$(WORKING_DIR)/$@/$${pair}.tsv', separator='\t'); df_subset = df.select(['subject_id', 'object_id', 'ancestor_id', 'ancestor_information_content']).unique(); df_subset.write_csv('$(WORKING_DIR)/$@/$${pair}_subset.tsv', separator='\t')"; \
	done
	@echo "✅ Subset files created: HP_vs_*_subset.tsv"
	tar -czf "$(WORKING_DIR)/$@/semsim.tar.gz" \
			-C "$(WORKING_DIR)/$@" \
			HP_vs_MP.tsv HP_vs_HP.tsv HP_vs_ZP.tsv log_sql_generation.yml
	@if [ -f "$(WORKING_DIR)/$@/semsim.tar.gz" ]; then \
		rm -f "$(WORKING_DIR)/$@/"HP_vs_{MP,HP,ZP}.tsv; \
	else \
		echo "❌ Failed to create semsim.tar.gz"; \
		exit 1; \
	fi

ICSCORE_SOURCE = semsim-phenio-default

semsim-ols-cosinenemotron8b:
	mkdir -p $(WORKING_DIR)/semsim-ols-cosinenemotron8b
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim/hp_zp__llama-embed-nemotron-8b.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_zp__llama-embed-nemotron-8b.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_zp__llama-embed-nemotron-8b.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_zp__llama-embed-nemotron-8b.tsv $(WORKING_DIR)/$@/HP_vs_ZP.tsv
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim/hp_mp__llama-embed-nemotron-8b.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_mp__llama-embed-nemotron-8b.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_mp__llama-embed-nemotron-8b.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_mp__llama-embed-nemotron-8b.tsv $(WORKING_DIR)/$@/HP_vs_MP.tsv
	wget https://ftp.ebi.ac.uk/pub/databases/spot/ols_embeddings/semsim/hp_hp__llama-embed-nemotron-8b.tsv.gz -O $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_hp__llama-embed-nemotron-8b.tsv.gz
	gunzip $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_hp__llama-embed-nemotron-8b.tsv.gz
	mv $(WORKING_DIR)/semsim-ols-cosinenemotron8b/hp_hp__llama-embed-nemotron-8b.tsv $(WORKING_DIR)/$@/HP_vs_HP.tsv
	# TODO The next line exists so I can test changes to this goal w/o rerunning semsim pipeline
	#@tar -xzf "$(WORKING_DIR)/$@/semsim.tar.gz" -C "$(WORKING_DIR)/$@"
	@echo "🔧 Enriching TSV files with ancestor information from $(ICSCORE_SOURCE)..."
	@for pair in HP_vs_ZP; do \
		if [ -f "$(WORKING_DIR)/$(ICSCORE_SOURCE)/$${pair}_subset.tsv" ]; then \
			$(RUN) python3 -c "import polars as pl; \
				df_main = pl.read_csv('$(WORKING_DIR)/$@/$${pair}.tsv', separator='\t'); \
				df_subset = pl.read_csv('$(WORKING_DIR)/$(ICSCORE_SOURCE)/$${pair}_subset.tsv', separator='\t'); \
				df_enriched = df_main.join(df_subset, on=['subject_id', 'object_id'], how='left'); \
				df_enriched = df_enriched.with_columns([ \
					pl.col('ancestor_id').fill_null('HP:0000000'), \
					pl.col('ancestor_information_content').fill_null(1) \
				]); \
				df_enriched.write_csv('$(WORKING_DIR)/$@/$${pair}.tsv', separator='\t')"; \
			echo "   ✅ Enriched $${pair}.tsv"; \
		else \
			echo "   ⚠️  Warning: $(WORKING_DIR)/$(ICSCORE_SOURCE)/$${pair}_subset.tsv not found, skipping"; \
		fi; \
	done
	@echo "✅ Enrichment complete"
	tar -czf "$(WORKING_DIR)/semsim-ols-cosinenemotron8b/semsim.tar.gz" \
			-C "$(WORKING_DIR)/semsim-ols-cosinenemotron8b" \
			HP_vs_MP.tsv HP_vs_HP.tsv HP_vs_ZP.tsv log_sql_generation.yml
	@if [ -f "$(WORKING_DIR)/semsim-ols-cosinenemotron8b/semsim.tar.gz" ]; then \
		rm -f "$(WORKING_DIR)/semsim-ols-cosinenemotron8b/"HP_vs_{MP,HP,ZP}.tsv; \
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
	@echo "🔧 Enriching TSV files with ancestor information from $(ICSCORE_SOURCE)..."
	@for pair in HP_vs_MP HP_vs_HP HP_vs_ZP; do \
		if [ -f "$(WORKING_DIR)/$(ICSCORE_SOURCE)/$${pair}_subset.tsv" ]; then \
			$(RUN) python3 -c "import polars as pl; \
				df_main = pl.read_csv('$(WORKING_DIR)/$@/$${pair}.tsv', separator='\t'); \
				df_subset = pl.read_csv('$(WORKING_DIR)/$(ICSCORE_SOURCE)/$${pair}_subset.tsv', separator='\t'); \
				df_enriched = df_main.join(df_subset, on=['subject_id', 'object_id'], how='left'); \
				df_enriched = df_enriched.with_columns([ \
					pl.col('ancestor_id').fill_null('HP:0000000'), \
					pl.col('ancestor_information_content').fill_null(1) \
				]); \
				df_enriched.write_csv('$(WORKING_DIR)/$@/$${pair}.tsv', separator='\t')"; \
			echo "   ✅ Enriched $${pair}.tsv"; \
		else \
			echo "   ⚠️  Warning: $(WORKING_DIR)/$(ICSCORE_SOURCE)/$${pair}_subset.tsv not found, skipping"; \
		fi; \
	done
	@echo "✅ Enrichment complete"
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
	semsim-ols-cosinenemotron8b \
	semsim-ols-cosinetextsmall

# Generate SQL files from semantic similarity results
# Creates: working/<run-name>/HP_vs_*_semsimian_phenio_exomiser.sql
# Usage: make exomiser-sql-semsim-phenio-default

THRESHOLD ?= 0.85
THRESHOLD_COLUMN ?= default
BATCH_SIZE ?= 100000
SCORE=phenodigm_score
COMPUTE_PHENODIGM=true

tmp/hp.owl: 
	wget http://purl.obolibrary.org/obo/hp.owl -O tmp/hp.owl

tmp/hp-labels.tsv: tmp/hp.owl
	robot export -i tmp/hp.owl -f tsv --header "ID|LABEL" --export $@
	grep "^HP:" $@ > $@.tmp && mv $@.tmp $@

tmp/hpoa.tsv:
	wget http://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa -O $@

tmp/hp-ic.tsv: tmp/hpoa.tsv
	$(RUN) runoak -g tmp/hpoa.tsv -G hpoa -i sqlite:obo:hp information-content -p i --use-associations .all > $@
	tail -n +2 "$@" | grep "^HP:" > "$@.tmp" && mv "$@.tmp" "$@"

exomiser-sql-%: $(WORKING_DIR)/%/semsim.tar.gz tmp/hp-labels.tsv tmp/hp-ic.tsv
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
				--subject-prefix "$$subject" \
				--object-prefix "$$object" \
				--threshold "$(THRESHOLD)" \
				--threshold-column "$(THRESHOLD_COLUMN)" \
				--hp-ic-list "tmp/hp-ic.tsv" \
				--hp-label-list "tmp/hp-labels.tsv" \
				--score "$(SCORE)" \
				--compute-phenodigm "$(COMPUTE_PHENODIGM)" \
				--batch-size "$(BATCH_SIZE)" \
				--format psv \
				--output "$(WORKING_DIR)/$*/$${pair}.txt"; \
		done; \
		\
		logfile="$(WORKING_DIR)/$*/log_sql_generation.yml"; \
		{ \
			echo "date: $$(date)"; \
			echo "semsim_threshold: $(THRESHOLD)"; \
			echo "compute_phenodigm: $(COMPUTE_PHENODIGM)"; \
			echo "score: $(SCORE)"; \
			echo "resnik_threshold: $(RESNIK_THRESHOLD)"; \
			echo "flavour: $*"; \
			[ -f "$(WORKING_DIR)/$*/phenio_version" ] && echo "phenio: $$(cat $(WORKING_DIR)/$*/phenio_version)"; \
			[ -f "$(WORKING_DIR)/$*/hp_version" ] && echo "hp: $$(cat $(WORKING_DIR)/$*/hp_version)"; \
			[ -f "$(WORKING_DIR)/$*/mp_version" ] && echo "mp: $$(cat $(WORKING_DIR)/$*/mp_version)"; \
			[ -f "$(WORKING_DIR)/$*/zp_version" ] && echo "zp: $$(cat $(WORKING_DIR)/$*/zp_version)"; \
		} > "$$logfile"; \
		echo "$*-$(THRESHOLD)-$(SCORE)-$(COMPUTE_PHENODIGM)" > $(WORKING_DIR)/$*/run_config.txt; \
		\
		echo "✅ SQL files generated successfully in $(WORKING_DIR)/$*/"; \
		echo "📊 Checking if SQL files where correctly created..."; \
		if 	[ -f "$(WORKING_DIR)/$*/HP_vs_MP.txt" ] && \
			[ -f "$(WORKING_DIR)/$*/HP_vs_HP.txt" ] && \
			[ -f "$(WORKING_DIR)/$*/HP_vs_ZP.txt" ] && \
			[ -f "$(WORKING_DIR)/$*/log_sql_generation.yml" ]; then \
			tar -czf "$(WORKING_DIR)/$*/sql.tar.gz" \
				-C "$(WORKING_DIR)/$*" \
				HP_vs_MP.txt HP_vs_HP.txt HP_vs_ZP.txt log_sql_generation.yml; \
			rm -f "$(WORKING_DIR)/$*/"HP_vs_{MP,HP,ZP}.{txt,tsv}; \
			rm -f "$(WORKING_DIR)/$*/log_sql_generation.yml"; \
		else \
			echo "❌ Error: One or more SQL files were not created successfully."; \
			exit 1; \
		fi; \
	fi

# Import SQL files from sql.tar.gz into H2 database
# Usage: make import-h2-semsim-phenio-default H2_DB=/path/to/database.mv.db
# Requires: H2 JDBC driver jar file and Java 
H2_DB ?= $(WORKING_DIR)/exomiser/current/2508_phenotype/2508_phenotype.mv.db
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

	@echo "🔧 Copying exomiser database..."
	@cp "$(H2_DB)" "$(WORKING_DIR)/$*/phenotype.mv.db"
	@echo "✅ Copied database."

	@mkdir -p "$(WORKING_DIR)/$*/sql_unpacked"
	@tar -xzf "$<" -C "$(WORKING_DIR)/$*/sql_unpacked"
	@echo "✅ Extracted SQL files"

	@cp "scripts/h2-exomiser-load.sql" "$(WORKING_DIR)/$*/h2-exomiser-load.sql"

	@sql_data_dir=$$(cd "$(WORKING_DIR)/$*" && pwd)/sql_unpacked; \
	sed "s|\$${import.path}|$$sql_data_dir|g" \
	    "$(WORKING_DIR)/$*/h2-exomiser-load.sql" \
	    > "$(WORKING_DIR)/$*/h2-exomiser-load.sql.tmp" && \
	mv "$(WORKING_DIR)/$*/h2-exomiser-load.sql.tmp" "$(WORKING_DIR)/$*/h2-exomiser-load.sql"

	@echo "✅ Updated SQL file with import path"

	@db_abs_path=$$(cd "$(WORKING_DIR)/$*" && pwd)/phenotype; \
	jdbc_url="jdbc:h2:file:$$db_abs_path"; \
	echo "   JDBC URL: $$jdbc_url"; \
	java -Xms512m -Xmx16384m \
		-cp "$(H2_JAR)" org.h2.tools.RunScript \
		-url "$$jdbc_url;LOCK_MODE=0;CACHE_SIZE=65536;MODE=POSTGRESQL" \
		-script "$(WORKING_DIR)/$*/h2-exomiser-load.sql" \
		-user "sa" \
		-password ""; \
	status=$$?; \
	if [ $$status -eq 0 ]; then \
		echo "   ✅ Successfully imported $(WORKING_DIR)/$*/h2-exomiser-load.sql"; \
		echo "🧹 Cleaning up temporary H2 files..."; \
		rm -rf "$(WORKING_DIR)/$*/sql_unpacked"; \
		rm -f "$(WORKING_DIR)/$*/phenotype.trace.db"; \
		rm -f "$(WORKING_DIR)/$*/phenotype.trace.db.old"; \
		rm -f "$(WORKING_DIR)/$*/phenotype.mv.db.trace.db"; \
		echo "✅ Cleanup complete"; \
	else \
		echo "   ❌ Failed to import $(WORKING_DIR)/$*/h2-exomiser-load.sql"; \
		exit $$status; \
	fi


old-h2:
	rm -f $(WORKING_DIR)/semsim-phenio-default/sql.tar.gz
	rm -f $(WORKING_DIR)/semsim-phenio-default/phenotype.mv.db
	make exomiser-sql-semsim-phenio-default THRESHOLD=0.4 BATCH_SIZE=100000 SCORE=phenodigm_score COMPUTE_PHENODIGM=false THRESHOLD_COLUMN=jaccard_similarity
	make h2-semsim-phenio-default
	gzip -k $(WORKING_DIR)/semsim-phenio-default/phenotype.mv.db
	mv $(WORKING_DIR)/semsim-phenio-default/phenotype.mv.db.gz $(WORKING_DIR)/semsim-phenio-default/phenotype-$$(tr -d '\n' < $(WORKING_DIR)/semsim-phenio-default/run_config.txt).mv.db.gz
	
	rm -f $(WORKING_DIR)/semsim-phenio-equivalent/phenotype.mv.db
	rm -f $(WORKING_DIR)/semsim-phenio-equivalent/sql.tar.gz
	make exomiser-sql-semsim-phenio-equivalent THRESHOLD=0.4 BATCH_SIZE=100000 SCORE=phenodigm_score COMPUTE_PHENODIGM=false THRESHOLD_COLUMN=jaccard_similarity
	make h2-semsim-phenio-equivalent
	gzip -k $(WORKING_DIR)/semsim-phenio-equivalent/phenotype.mv.db
	mv $(WORKING_DIR)/semsim-phenio-equivalent/phenotype.mv.db.gz $(WORKING_DIR)/semsim-phenio-equivalent/phenotype-$$(tr -d '\n' < $(WORKING_DIR)/semsim-phenio-equivalent/run_config.txt).mv.db.gz

all-h2:
	rm -f $(WORKING_DIR)/semsim-ols-cosinenemotron8b/sql.tar.gz
	rm -f $(WORKING_DIR)/semsim-ols-cosinenemotron8b/phenotype.mv.db
	make exomiser-sql-semsim-ols-cosinenemotron8b THRESHOLD=0.4 BATCH_SIZE=100000 SCORE=cosine_similarity COMPUTE_PHENODIGM=true
	make h2-semsim-ols-cosinenemotron8b
	gzip -k $(WORKING_DIR)/semsim-ols-cosinenemotron8b/phenotype.mv.db
	mv $(WORKING_DIR)/semsim-ols-cosinenemotron8b/phenotype.mv.db.gz $(WORKING_DIR)/semsim-ols-cosinenemotron8b/phenotype-$$(tr -d '\n' < $(WORKING_DIR)/semsim-ols-cosinenemotron8b/run_config.txt).mv.db.gz
	
	rm -f $(WORKING_DIR)/semsim-ols-cosinetextsmall/sql.tar.gz
	rm -f $(WORKING_DIR)/semsim-ols-cosinetextsmall/phenotype.mv.db
	make exomiser-sql-semsim-ols-cosinetextsmall THRESHOLD=0.4 BATCH_SIZE=100000 SCORE=cosine_similarity COMPUTE_PHENODIGM=true
	make h2-semsim-ols-cosinetextsmall
	gzip -k $(WORKING_DIR)/semsim-ols-cosinetextsmall/phenotype.mv.db
	mv $(WORKING_DIR)/semsim-ols-cosinetextsmall/phenotype.mv.db.gz $(WORKING_DIR)/semsim-ols-cosinetextsmall/phenotype-$$(tr -d '\n' < $(WORKING_DIR)/semsim-ols-cosinetextsmall/run_config.txt).mv.db.gz

unfiltered-h2:
	rm -f $(WORKING_DIR)/semsim-phenio-equivalent/sql.tar.gz
	rm -f $(WORKING_DIR)/semsim-phenio-equivalent/phenotype.mv.db
	make exomiser-sql-semsim-phenio-equivalent THRESHOLD=0.0 BATCH_SIZE=100000 SCORE=phenodigm_score COMPUTE_PHENODIGM=false THRESHOLD_COLUMN=jaccard_similarity
	make h2-semsim-phenio-equivalent
	gzip -k $(WORKING_DIR)/semsim-phenio-equivalent/phenotype.mv.db
	mv $(WORKING_DIR)/semsim-phenio-equivalent/phenotype.mv.db.gz $(WORKING_DIR)/semsim-phenio-equivalent/phenotype-$$(tr -d '\n' < $(WORKING_DIR)/semsim-phenio-equivalent/run_config.txt).mv.db.gz

cp-h2:
	@sh -c 'set -e; \
		files=$$(ls $(WORKING_DIR)/*/phenotype-*.mv.db.gz); \
		mv -f $$files "$$HOME/Dropbox/semanticly_share/exomiser-dbs/"; \
		echo "Copied: $$files"; \
	'

# Clean working directory
clean:
	rm -rf $(WORKING_DIR)
	mkdir -p $(WORKING_DIR)
