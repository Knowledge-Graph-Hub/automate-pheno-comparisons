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
    environment {
        BUILDSTARTDATE = sh(script: "echo `date +%Y%m%d`", returnStdout: true).trim()
        // Store similarity results at s3://kg-hub-public-data/monarch/semsim/
        S3PROJECTDIR = 's3://kg-hub-public-data/monarch/semsim/'

	    RESNIK_THRESHOLD = '1.5' // value for min-ancestor-information-content parameter

        HP_VS_HP_PREFIX = "HP_vs_HP_semsimian_phenio"
        HP_VS_HP_PREFIX_ONTOONLY = "HP_vs_HP_semsimian_hp"
        HP_VS_MP_PREFIX = "HP_vs_MP_semsimian_phenio"
        HP_VS_ZP_PREFIX = "HP_vs_ZP_semsimian_phenio"

        // Distribution ID for the AWS CloudFront for this bucket
        // used solely for invalidations
        AWS_CLOUDFRONT_DISTRIBUTION_ID = 'EUVSWXZQBXCFP'
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
                    sh 'echo "TEST BUILD ONLY"'
                    sh 'env > env.txt'
                    sh 'echo $BRANCH_NAME > branch.txt'
                    sh 'echo "$BRANCH_NAME"'
                    sh 'cat env.txt'
                    sh 'cat branch.txt'
                    sh "echo $BUILDSTARTDATE"
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
			        sh './venv/bin/pip install s3cmd'
                    sh './venv/bin/pip install "oaklib[semsimian] @ git+https://github.com/INCATools/ontology-access-kit.git"'
                    // Install duckdb
                    sh 'wget https://github.com/duckdb/duckdb/releases/download/v0.10.3/duckdb_cli-linux-amd64.zip'
                    sh 'unzip duckdb_cli-linux-amd64.zip'
                    // Get metadata for PHENIO
                    sh '. venv/bin/activate && runoak -i sqlite:obo:phenio ontology-metadata --all'
                    // Retrieve association tables
                    sh 'curl -L -s http://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa > hpoa.tsv'
                    sh 'curl -L -s https://data.monarchinitiative.org/latest/tsv/gene_associations/gene_phenotype.10090.tsv.gz | gunzip - > mpa.tsv'
                    sh 'curl -L -s https://data.monarchinitiative.org/latest/tsv/gene_associations/gene_phenotype.7955.tsv.gz | gunzip - > zpa.tsv'
                    // MP and ZP need to be preprocessed to pairwise associations
                    sh 'cut -f1,5 mpa.tsv | grep "MP" > "mpa.tsv.tmp" && mv "mpa.tsv.tmp" "mpa.tsv"'
                    sh 'cut -f1,5 zpa.tsv | grep "ZP" > "zpa.tsv.tmp" && mv "zpa.tsv.tmp" "zpa.tsv"'
                }
            }
        }

        stage('Run similarity for HP vs HP through PHENIO') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:hp descendants -p i HP:0000118 > HPO_terms.txt'
                    sh '. venv/bin/activate && runoak -g hpoa.tsv -G hpoa -i sqlite:obo:phenio information-content -p i --use-associations .all > hpoa_ic.tsv && tail -n +2 "hpoa_ic.tsv" > "hpoa_ic.tsv.tmp" && mv "hpoa_ic.tsv.tmp" "hpoa_ic.tsv"'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file hpoa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file HPO_terms.txt -O csv -o $HP_VS_HP_PREFIX_$BUILDSTARTDATE.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                    sh '. venv/bin/activate && SHORTHIST=$(history | tail -4 | head -3 | cut -c 8-)'                    
                    sh '. echo "name: $HP_VS_HP_PREFIX_$BUILDSTARTDATE" > $HP_VS_HP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "min_ancestor_information_content: $RESNIK_THRESHOLD" >> $HP_VS_HP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "commands: >> $HP_VS_HP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. venv/bin/activate && printf "%s\n" "${SHORTHIST}" >> $HP_VS_HP_PREFIX_$BUILDSTARTDATE_log.yaml'
                }
            }
        }

        stage('Upload results for HP vs HP through PHENIO') {
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              
                                // upload to remote
				                sh 'tar -czvf $HP_VS_HP_PREFIX.tsv.tar.gz $HP_VS_HP_PREFIX_$BUILDSTARTDATE.tsv $HP_VS_HP_PREFIX_$BUILDSTARTDATE_log.yaml hpoa_ic.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate $HP_VS_HP_PREFIX.tsv.tar.gz $S3PROJECTDIR'
                            }

                        }
                    }
                }
            }
        stage('Run similarity for HP vs HP through HP alone') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:hp descendants -p i HP:0000118 > HPO_terms.txt'
                    sh '. venv/bin/activate && runoak -g hpoa.tsv -G hpoa -i sqlite:obo:hp information-content -p i --use-associations .all > hpoa_ic.tsv && tail -n +2 "hpoa_ic.tsv" > "hpoa_ic.tsv.tmp" && mv "hpoa_ic.tsv.tmp" "hpoa_ic.tsv"'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:hp similarity --no-autolabel --information-content-file hpoa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file HPO_terms.txt -O csv -o $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                    sh '. venv/bin/activate && SHORTHIST=$(history | tail -4 | head -3 | cut -c 8-)'                    
                    sh '. echo "name: $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE" > $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "min_ancestor_information_content: $RESNIK_THRESHOLD" >> $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "commands: >> $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE_log.yaml'
                    sh '. venv/bin/activate && printf "%s\n" "${SHORTHIST}" >> $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE_log.yaml'
                }
            }
        }

        stage('Upload results for HP vs HP through HP alone') {
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              
                                // upload to remote
				                sh 'tar -czvf HP_VS_HP_PREFIX_ONTOONLY.tsv.tar.gz $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE.tsv $HP_VS_HP_PREFIX_ONTOONLY_$BUILDSTARTDATE_log.yaml hpoa_ic.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate $HP_VS_HP_PREFIX_ONTOONLY.tsv.tar.gz $S3PROJECTDIR'
                            }

                        }
                    }
                }
            }

        stage('Run similarity for HP vs MP through PHENIO') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:mp descendants -p i MP:0000001 > MP_terms.txt'
                    sh '. venv/bin/activate && runoak -g mpa.tsv -G g2t -i sqlite:obo:phenio information-content -p i --use-associations .all > mpa_ic.tsv && tail -n +2 "mpa_ic.tsv" > "mpa_ic.tsv.tmp" && mv "mpa_ic.tsv.tmp" "mpa_ic.tsv"'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file mpa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file MP_terms.txt -O csv -o $HP_VS_MP_PREFIX_$BUILDSTARTDATE.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                    sh '. venv/bin/activate && SHORTHIST=$(history | tail -4 | head -3 | cut -c 8-)'                    
                    sh '. echo "name: $HP_VS_MP_PREFIX_$BUILDSTARTDATE" > $HP_VS_MP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "min_ancestor_information_content: $RESNIK_THRESHOLD" >> $HP_VS_MP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "commands: >> $HP_VS_MP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. venv/bin/activate && printf "%s\n" "${SHORTHIST}" >> $HP_VS_MP_PREFIX_$BUILDSTARTDATE_log.yaml'
                }
            }
        }

        stage('Upload results for HP vs MP through PHENIO') {
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              
                                // upload to remote
				                sh 'tar -czvf $HP_VS_MP_PREFIX.tsv.tar.gz $HP_VS_MP_PREFIX_$BUILDSTARTDATE.tsv $HP_VS_MP_PREFIX_$BUILDSTARTDATE_log.yaml mpa_ic.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate $HP_VS_MP_PREFIX.tsv.tar.gz $S3PROJECTDIR'

                            }

                        }
                    }
                }
            }

        stage('Run similarity for HP vs ZP through PHENIO') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:zp descendants -p i ZP:0000000 > ZP_terms.txt'
                    sh '. venv/bin/activate && runoak -g zpa.tsv -G g2t -i sqlite:obo:phenio information-content -p i --use-associations .all > zpa_ic.tsv && tail -n +2 "zpa_ic.tsv" > "zpa_ic.tsv.tmp" && mv "zpa_ic.tsv.tmp" "zpa_ic.tsv"'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file zpa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file ZP_terms.txt -O csv -o $HP_VS_ZP_PREFIX_$BUILDSTARTDATE.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                    sh '. venv/bin/activate && SHORTHIST=$(history | tail -4 | head -3 | cut -c 8-)'                    
                    sh '. echo "name: $HP_VS_ZP_PREFIX_$BUILDSTARTDATE" > $HP_VS_ZP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "min_ancestor_information_content: $RESNIK_THRESHOLD" >> $HP_VS_ZP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. echo "commands: >> $HP_VS_ZP_PREFIX_$BUILDSTARTDATE_log.yaml'
                    sh '. venv/bin/activate && printf "%s\n" "${SHORTHIST}" >> $HP_VS_ZP_PREFIX_$BUILDSTARTDATE_log.yaml'
                }
            }
        }

        stage('Upload results for HP vs ZP through PHENIO') {
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              
                                // upload to remote
				                sh 'tar -czvf $HP_VS_ZP_PREFIX.tsv.tar.gz $HP_VS_ZP_PREFIX_$BUILDSTARTDATE.tsv $HP_VS_ZP_PREFIX_$BUILDSTARTDATE_log.yaml zpa_ic.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate $HP_VS_ZP_PREFIX.tsv.tar.gz $S3PROJECTDIR'
                            }

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
