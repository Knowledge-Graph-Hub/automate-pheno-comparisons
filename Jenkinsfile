pipeline {
    agent {
        docker {
            reuseNode false
            image 'caufieldjh/kg-idg:4'
        }
    }
    //triggers{
    //    cron('H H 1 1-12 *')
    //}
    parameters {
        password(name: 'ZENODO_TOKEN', defaultValue: '', description: 'Zenodo API token (passed at build time)')
        string(name: 'ZENODO_RECORD_ID', defaultValue: '18474576', description: 'Zenodo record ID to version')
    }
    environment {
        BUILDSTARTDATE = sh(script: "echo `date +%Y%m%d`", returnStdout: true).trim()
        ZENODO_VERSION = sh(script: "echo `date +%F`", returnStdout: true).trim()
        ZENODO_BASE_URL = 'https://zenodo.org/api'
        ZENODO_TOKEN = "${params.ZENODO_TOKEN}"
        ZENODO_RECORD_ID = "${params.ZENODO_RECORD_ID}"

	    RESNIK_THRESHOLD = '1.5' // value for min-ancestor-information-content parameter

        HP_VS_HP_PREFIX = "HP_vs_HP_semsimian_phenio"
        HP_VS_MP_PREFIX = "HP_vs_MP_semsimian_phenio"
        HP_VS_ZP_PREFIX = "HP_vs_ZP_semsimian_phenio"

        HP_VS_HP_NAME = "${HP_VS_HP_PREFIX}_${BUILDSTARTDATE}"
        HP_VS_MP_NAME = "${HP_VS_MP_PREFIX}_${BUILDSTARTDATE}"
        HP_VS_ZP_NAME = "${HP_VS_ZP_PREFIX}_${BUILDSTARTDATE}"

    }
    options {
        timestamps()
        disableConcurrentBuilds()
    }
    stages {
        stage('Ready and clean') {
            steps {
                // Give us a minute to cancel if we want.
                sleep time: 30, unit: 'SECONDS'
            }
        }

        stage('Initialize') {
            steps {
                // print some info
                dir('./working') {
                    sh 'env > env.txt'
                    sh 'echo $BRANCH_NAME > branch.txt'
                    sh 'echo "$BRANCH_NAME"'
                    sh 'cat env.txt'
                    sh 'cat branch.txt'
                    sh 'echo "$BUILDSTARTDATE"'
                    sh "python3.9 --version"
                    sh "id"
                    sh "whoami" // this should be jenkinsuser
                    // if the above fails, then the docker host didn't start the docker
                    // container as a user that this image knows about. This will
                    // likely cause lots of problems (like trying to write to $HOME
                    // directory that doesn't exist, etc), so we should fail here and
                    // have the user fix this


                }
            }
        }

        stage('Setup') {
            steps {
                dir('./working') {
                	sh '/usr/bin/python3.9 -m venv venv'
			        sh '. venv/bin/activate'
                    sh './venv/bin/pip install "oaklib[semsimian] @ git+https://github.com/INCATools/ontology-access-kit.git"'
                    // Install duckdb
                    sh 'wget https://github.com/duckdb/duckdb/releases/download/v0.10.3/duckdb_cli-linux-amd64.zip'
                    sh '. venv/bin/activate && python -m zipfile -e duckdb_cli-linux-amd64.zip ./'
                    sh 'chmod +x duckdb'
                    // Install yq
                    sh 'wget https://github.com/mikefarah/yq/releases/download/v4.2.0/yq_linux_amd64 -O yq && chmod +x yq'
                    // Get metadata for all ontologies, including PHENIO
                    sh '. venv/bin/activate && runoak -i sqlite:obo:hp ontology-metadata --all | ./yq eval \'.[\"owl:versionIRI\"][0]\' - > hp_version'
                    sh '. venv/bin/activate && runoak -i sqlite:obo:mp ontology-metadata --all | ./yq eval \'.[\"owl:versionIRI\"][0]\' - > mp_version'
                    sh '. venv/bin/activate && runoak -i sqlite:obo:zp ontology-metadata --all | ./yq eval \'.[\"owl:versionIRI\"][0]\' - > zp_version'
                    sh '. venv/bin/activate && runoak -i sqlite:obo:phenio ontology-metadata --all | ./yq eval \'.[\"owl:versionIRI\"][0]\' - > phenio_version'
                    script {
                        HP_VERSION = readFile('hp_version').trim()
                        MP_VERSION = readFile('mp_version').trim()
                        ZP_VERSION = readFile('zp_version').trim()
                        PHENIO_VERSION = readFile('phenio_version').trim()
                    }
                    // Retrieve association tables
                    sh 'curl -L -s http://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa > hpoa.tsv'
                    sh 'curl -L -s https://data.monarchinitiative.org/dipper-kg/final/tsv/gene_associations/gene_phenotype.10090.tsv.gz | gunzip - > mpa.tsv'
                    sh 'curl -L -s https://data.monarchinitiative.org/dipper-kg/final/tsv/gene_associations/gene_phenotype.7955.tsv.gz | gunzip - > zpa.tsv'
                    // MP and ZP need to be preprocessed to pairwise associations
                    sh 'cut -f1,5 mpa.tsv | grep "MP" > "mpa.tsv.tmp" && mv "mpa.tsv.tmp" "mpa.tsv"'
                    sh 'cut -f1,5 zpa.tsv | grep "ZP" > "zpa.tsv.tmp" && mv "zpa.tsv.tmp" "zpa.tsv"'
                }
            }
        }

        stage('Run similarity for HP vs HP through PHENIO') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:hp descendants -p i HP:0000118 > HPO_terms.txt && sed "s/ [!] /\t/g" HPO_terms.txt > HPO_terms.tsv'
                    sh '. venv/bin/activate && runoak -g hpoa.tsv -G hpoa -i sqlite:obo:phenio information-content -p i --use-associations .all > hpoa_ic.tsv && tail -n +2 "hpoa_ic.tsv" > "hpoa_ic.tsv.tmp" && mv "hpoa_ic.tsv.tmp" "hpoa_ic.tsv"'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file hpoa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file HPO_terms.txt -O csv -o ${HP_VS_HP_NAME}.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                    sh '. venv/bin/activate && ./duckdb -c "CREATE TABLE semsim AS SELECT * FROM read_csv(\'${HP_VS_HP_NAME}.tsv\', header=TRUE); CREATE TABLE labels AS SELECT * FROM read_csv(\'HPO_terms.tsv\', header=FALSE); CREATE TABLE labeled1 AS SELECT * FROM semsim n JOIN labels r ON (subject_id = column0); CREATE TABLE labeled2 AS SELECT * FROM labeled1 n JOIN labels r ON (object_id = r.column0); ALTER TABLE labeled2 DROP subject_label; ALTER TABLE labeled2 DROP object_label; ALTER TABLE labeled2 RENAME column1 TO subject_label; ALTER TABLE labeled2 RENAME column1_1 TO object_label; ALTER TABLE labeled2 DROP column0; ALTER TABLE labeled2 DROP column0_1; COPY (SELECT subject_id, subject_label, subject_source, object_id, object_label, object_source, ancestor_id, ancestor_label, ancestor_source, object_information_content, subject_information_content, ancestor_information_content, jaccard_similarity, cosine_similarity, dice_similarity, phenodigm_score FROM labeled2) TO \'${HP_VS_HP_NAME}.tsv.tmp\' WITH (HEADER true, DELIMITER \'\t\')" && mv "${HP_VS_HP_NAME}.tsv.tmp" "${HP_VS_HP_NAME}.tsv"'
                    // sh '. venv/bin/activate && SHORTHIST=$(history | tail -6 | head -5 | cut -c 8-)'                    
                    sh 'echo "name: ${HP_VS_HP_NAME}" > ${HP_VS_HP_NAME}_log.yaml'
                    sh 'echo "min_ancestor_information_content: $RESNIK_THRESHOLD" >> ${HP_VS_HP_NAME}_log.yaml'
                    sh 'echo "versions:" >> ${HP_VS_HP_NAME}_log.yaml'
                    sh 'echo "  hp: ${HP_VERSION}" >> ${HP_VS_HP_NAME}_log.yaml'
                    sh 'echo "  phenio: ${PHENIO_VERSION}" >> ${HP_VS_HP_NAME}_log.yaml'
                    // sh '. venv/bin/activate && printf "%s\n" "${SHORTHIST}" >> $HP_VS_HP_PREFIX_$BUILDSTARTDATE_log.yaml'
                }
            }
        }

        stage('Prepare Zenodo Draft') {
            steps {
                dir('./working') {
                    script {
                        if (!env.ZENODO_TOKEN?.trim()) {
                            error('ZENODO_TOKEN parameter is required')
                        }
                        if (!env.ZENODO_RECORD_ID?.trim()) {
                            error('ZENODO_RECORD_ID parameter is required')
                        }
                        def draftInfo = sh(script: '''
                            python3.9 - <<'PY'
import json
import os
import urllib.error
import urllib.request

token = os.environ.get("ZENODO_TOKEN")
record_id = os.environ.get("ZENODO_RECORD_ID")
base_url = os.environ.get("ZENODO_BASE_URL", "https://zenodo.org/api").rstrip("/")
version = os.environ.get("ZENODO_VERSION")

headers = {"Authorization": f"Bearer {token}"}

def request(method, url, payload=None, expect_json=True):
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req_headers = dict(headers)
    if payload is not None:
        req_headers["Content-Type"] = "application/json"
    request_obj = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(request_obj) as response:
            body = response.read()
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", "ignore")
        raise SystemExit(f"Zenodo API error {exc.code} {exc.reason}: {error_body}")
    if not expect_json:
        return None
    return json.loads(body.decode("utf-8")) if body else {}

response = request("POST", f"{base_url}/deposit/depositions/{record_id}/actions/newversion")
draft_url = response["links"]["latest_draft"]
draft = request("GET", draft_url)
draft_id = draft["id"]

for file_info in draft.get("files", []):
    file_id = file_info.get("id")
    if file_id is None:
        continue
    request("DELETE", f"{base_url}/deposit/depositions/{draft_id}/files/{file_id}", expect_json=False)

metadata = draft.get("metadata", {})
if version:
    metadata["version"] = version
request("PUT", f"{base_url}/deposit/depositions/{draft_id}", payload={"metadata": metadata})

print(json.dumps({"draft_id": draft_id, "bucket": draft["links"]["bucket"]}))
PY
                        ''', returnStdout: true).trim()
                        def info = new groovy.json.JsonSlurper().parseText(draftInfo)
                        env.ZENODO_DRAFT_ID = info.draft_id.toString()
                        env.ZENODO_BUCKET_URL = info.bucket.toString()
                    }
                }
            }
        }

        stage('Upload results for HP vs HP through PHENIO') {
            steps {
                dir('./working') {
                    sh 'tar -czvf $HP_VS_HP_PREFIX.tsv.tar.gz ${HP_VS_HP_NAME}.tsv ${HP_VS_HP_NAME}_log.yaml hpoa_ic.tsv'
                    sh 'curl -fSs -H "Authorization: Bearer $ZENODO_TOKEN" --upload-file $HP_VS_HP_PREFIX.tsv.tar.gz "$ZENODO_BUCKET_URL/$HP_VS_HP_PREFIX.tsv.tar.gz"'
                }
            }
        }

        stage('Run similarity for HP vs MP through PHENIO') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:mp descendants -p i MP:0000001 > MP_terms.txt && sed "s/ [!] /\t/g" MP_terms.txt > MP_terms.tsv'
                    sh 'cat HPO_terms.tsv MP_terms.tsv > HP_MP_terms.tsv'
                    sh '. venv/bin/activate && runoak -g mpa.tsv -G g2t -i sqlite:obo:phenio information-content -p i --use-associations .all > mpa_ic.tsv && tail -n +2 "mpa_ic.tsv" > "mpa_ic.tsv.tmp" && mv "mpa_ic.tsv.tmp" "mpa_ic.tsv"'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file mpa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file MP_terms.txt -O csv -o ${HP_VS_MP_NAME}.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                    sh '. venv/bin/activate && ./duckdb -c "CREATE TABLE semsim AS SELECT * FROM read_csv(\'${HP_VS_MP_NAME}.tsv\', header=TRUE); CREATE TABLE labels AS SELECT * FROM read_csv(\'HP_MP_terms.tsv\', header=FALSE); CREATE TABLE labeled1 AS SELECT * FROM semsim n JOIN labels r ON (subject_id = column0); CREATE TABLE labeled2 AS SELECT * FROM labeled1 n JOIN labels r ON (object_id = r.column0); ALTER TABLE labeled2 DROP subject_label; ALTER TABLE labeled2 DROP object_label; ALTER TABLE labeled2 RENAME column1 TO subject_label; ALTER TABLE labeled2 RENAME column1_1 TO object_label; ALTER TABLE labeled2 DROP column0; ALTER TABLE labeled2 DROP column0_1; COPY (SELECT subject_id, subject_label, subject_source, object_id, object_label, object_source, ancestor_id, ancestor_label, ancestor_source, object_information_content, subject_information_content, ancestor_information_content, jaccard_similarity, cosine_similarity, dice_similarity, phenodigm_score FROM labeled2) TO \'${HP_VS_MP_NAME}.tsv.tmp\' WITH (HEADER true, DELIMITER \'\t\')" && mv "${HP_VS_MP_NAME}.tsv.tmp" "${HP_VS_MP_NAME}.tsv"'
                    // sh '. venv/bin/activate && SHORTHIST=$(history | tail -7 | head -6 | cut -c 8-)'                    
                    sh 'echo "name: ${HP_VS_MP_NAME}" > ${HP_VS_MP_NAME}_log.yaml'
                    sh 'echo "min_ancestor_information_content: $RESNIK_THRESHOLD" >> ${HP_VS_MP_NAME}_log.yaml'
                    sh 'echo "versions: " >> ${HP_VS_MP_NAME}_log.yaml'
                    sh 'echo "  hp: ${HP_VERSION}" >> ${HP_VS_MP_NAME}_log.yaml'
                    sh 'echo "  mp: ${MP_VERSION}" >> ${HP_VS_MP_NAME}_log.yaml'
                    sh 'echo "  phenio: ${PHENIO_VERSION}" >> ${HP_VS_MP_NAME}_log.yaml'
                    // sh '. venv/bin/activate && printf "%s\n" "${SHORTHIST}" >> ${HP_VS_MP_NAME}_log.yaml'
                }
            }
        }

        stage('Upload results for HP vs MP through PHENIO') {
            steps {
                dir('./working') {
                    sh 'tar -czvf $HP_VS_MP_PREFIX.tsv.tar.gz ${HP_VS_MP_NAME}.tsv ${HP_VS_MP_NAME}_log.yaml mpa_ic.tsv'
                    sh 'curl -fSs -H "Authorization: Bearer $ZENODO_TOKEN" --upload-file $HP_VS_MP_PREFIX.tsv.tar.gz "$ZENODO_BUCKET_URL/$HP_VS_MP_PREFIX.tsv.tar.gz"'
                }
            }
        }

        stage('Run similarity for HP vs ZP through PHENIO') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:zp descendants -p i ZP:0000000 > ZP_terms.txt && sed "s/ [!] /\t/g" ZP_terms.txt > ZP_terms.tsv'
                    sh 'cat HPO_terms.tsv ZP_terms.tsv > HP_ZP_terms.tsv'
                    sh '. venv/bin/activate && runoak -g zpa.tsv -G g2t -i sqlite:obo:phenio information-content -p i --use-associations .all > zpa_ic.tsv && tail -n +2 "zpa_ic.tsv" > "zpa_ic.tsv.tmp" && mv "zpa_ic.tsv.tmp" "zpa_ic.tsv"'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file zpa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file ZP_terms.txt -O csv -o ${HP_VS_ZP_NAME}.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                    sh '. venv/bin/activate && ./duckdb -c "CREATE TABLE semsim AS SELECT * FROM read_csv(\'${HP_VS_ZP_NAME}.tsv\', header=TRUE); CREATE TABLE labels AS SELECT * FROM read_csv(\'HP_ZP_terms.tsv\', header=FALSE); CREATE TABLE labeled1 AS SELECT * FROM semsim n JOIN labels r ON (subject_id = column0); CREATE TABLE labeled2 AS SELECT * FROM labeled1 n JOIN labels r ON (object_id = r.column0); ALTER TABLE labeled2 DROP subject_label; ALTER TABLE labeled2 DROP object_label; ALTER TABLE labeled2 RENAME column1 TO subject_label; ALTER TABLE labeled2 RENAME column1_1 TO object_label; ALTER TABLE labeled2 DROP column0; ALTER TABLE labeled2 DROP column0_1; COPY (SELECT subject_id, subject_label, subject_source, object_id, object_label, object_source, ancestor_id, ancestor_label, ancestor_source, object_information_content, subject_information_content, ancestor_information_content, jaccard_similarity, cosine_similarity, dice_similarity, phenodigm_score FROM labeled2) TO \'${HP_VS_ZP_NAME}.tsv.tmp\' WITH (HEADER true, DELIMITER \'\t\')" && mv "${HP_VS_ZP_NAME}.tsv.tmp" "${HP_VS_ZP_NAME}.tsv"'
                    // sh '. venv/bin/activate && SHORTHIST=$(history | tail -7 | head -6 | cut -c 8-)'                    
                    sh 'echo "name: ${HP_VS_ZP_NAME}" > ${HP_VS_ZP_NAME}_log.yaml'
                    sh 'echo "min_ancestor_information_content: $RESNIK_THRESHOLD" >> ${HP_VS_ZP_NAME}_log.yaml'
                    sh 'echo "versions: " >> ${HP_VS_ZP_NAME}_log.yaml'
                    sh 'echo "  hp: ${HP_VERSION}" >> ${HP_VS_ZP_NAME}_log.yaml'
                    sh 'echo "  zp: ${ZP_VERSION}" >> ${HP_VS_ZP_NAME}_log.yaml'
                    sh 'echo "  phenio: ${PHENIO_VERSION}" >> ${HP_VS_ZP_NAME}_log.yaml'
                    // sh '. venv/bin/activate && printf "%s\n" "${SHORTHIST}" >> ${HP_VS_ZP_NAME}_log.yaml'
                }
            }
        }

        stage('Upload results for HP vs ZP through PHENIO') {
            steps {
                dir('./working') {
                    sh 'tar -czvf $HP_VS_ZP_PREFIX.tsv.tar.gz ${HP_VS_ZP_NAME}.tsv ${HP_VS_ZP_NAME}_log.yaml zpa_ic.tsv'
                    sh 'curl -fSs -H "Authorization: Bearer $ZENODO_TOKEN" --upload-file $HP_VS_ZP_PREFIX.tsv.tar.gz "$ZENODO_BUCKET_URL/$HP_VS_ZP_PREFIX.tsv.tar.gz"'
                }
            }
        }

        stage('Publish Zenodo Draft') {
            steps {
                dir('./working') {
                    script {
                        if (!env.ZENODO_DRAFT_ID?.trim()) {
                            error('Zenodo draft ID not set; cannot publish.')
                        }
                        sh '''
                            python3.9 - <<'PY'
import os
import urllib.error
import urllib.request

token = os.environ.get("ZENODO_TOKEN")
draft_id = os.environ.get("ZENODO_DRAFT_ID")
base_url = os.environ.get("ZENODO_BASE_URL", "https://zenodo.org/api").rstrip("/")

request_obj = urllib.request.Request(
    f"{base_url}/deposit/depositions/{draft_id}/actions/publish",
    headers={"Authorization": f"Bearer {token}"},
    method="POST"
)
try:
    with urllib.request.urlopen(request_obj) as response:
        response.read()
except urllib.error.HTTPError as exc:
    error_body = exc.read().decode("utf-8", "ignore")
    raise SystemExit(f"Zenodo publish failed {exc.code} {exc.reason}: {error_body}")
PY
                        '''
                    }
                }
            }
        }

    }

    post {
        always {
            echo 'In always'
            echo 'Cleaning workspace...'
            cleanWs()
        }
        success {
            echo 'I succeeded!'
        }
        unstable {
            echo 'I am unstable :/'
        }
        failure {
            echo 'I failed :('
        }
        changed {
            echo 'Things were different before...'
        }
    }
}
