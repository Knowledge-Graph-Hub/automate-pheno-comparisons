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

	    RESNIK_THRESHOLD = '4.0' // value for min-ancestor-information-content parameter

        HP_VS_HP_PREFIX = "HP_vs_HP_semsimian_"
        HP_VS_MP_PREFIX = "HP_vs_MP_semsimian_"
        HP_VS_ZP_PREFIX = "HP_vs_ZP_semsimian_"

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
                    sh './venv/bin/pip install git+https://github.com/INCATools/ontology-access-kit.git'
                    // Get metadata for PHENIO
                    sh '. venv/bin/activate && runoak -i sqlite:obo:phenio ontology-metadata --all'
                    // Retrieve association tables
                    sh 'curl -L -s http://purl.obolibrary.org/obo/hp/hpoa/phenotype.hpoa > hpoa.tsv'
                    sh 'curl -L -s https://data.monarchinitiative.org/latest/tsv/gene_associations/gene_phenotype.10090.tsv.gz | gunzip - > mpa.tsv'
                    sh 'curl -L -s https://data.monarchinitiative.org/latest/tsv/gene_associations/gene_phenotype.7955.tsv.gz | gunzip - > zpa.tsv'
                }
            }
        }

        stage('Run similarity for HP vs HP') {
            steps {
                dir('./working') {
                    sh '. venv/bin/activate && runoak -i sqlite:obo:hp descendants -p i HP:0000118 > HPO_terms.txt'
                    sh '. venv/bin/activate && runoak -g hpoa.tsv -G hpoa -i sqlite:obo:phenio information-content -p i --use-associations .all > hpoa_ic.tsv'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file hpoa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file HPO_terms.txt -O csv -o $HP_VS_HP_PREFIX-$BUILDSTARTDATE.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                }
            }
        }

        stage('Upload results for HP vs HP') {
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              
                                // upload to remote
				                sh 'tar -czvf HP_vs_HP_semsimian.tsv.tar.gz $HP_VS_HP_PREFIX-$BUILDSTARTDATE.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate HP_vs_HP_semsimian.tsv.tar.gz $S3PROJECTDIR'
                            }

                        }
                    }
                }
            }

        stage('Run similarity for HP vs MP') {
            steps {
                dir('./working') {
		            sh '. venv/bin/activate && runoak -i sqlite:obo:phenio ontology-metadata --all'
                    sh '. venv/bin/activate && runoak -i sqlite:obo:mp descendants -p i MP:0000001 > MP_terms.txt'
                    sh '. venv/bin/activate && runoak -g mpa.tsv -G hpoa_g2p -i sqlite:obo:phenio information-content -p i --use-associations .all > mpa_ic.tsv'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file mpa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file MP_terms.txt -O csv -o $HP_VS_MP_PREFIX-$BUILDSTARTDATE.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                }
            }
        }

        stage('Upload results for HP vs MP') {
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              
                                // upload to remote
				                sh 'tar -czvf HP_vs_MP_semsimian.tsv.tar.gz $HP_VS_MP_PREFIX-$BUILDSTARTDATE.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate HP_vs_MP_semsimian.tsv.tar.gz $S3PROJECTDIR'

                            }

                        }
                    }
                }
            }

        stage('Run similarity for HP vs ZP') {
            steps {
                dir('./working') {
		            sh '. venv/bin/activate && runoak -i sqlite:obo:phenio ontology-metadata --all'
                    sh '. venv/bin/activate && runoak -i sqlite:obo:zp descendants -p i ZP:0000000 > ZP_terms.txt'
                    sh '. venv/bin/activate && runoak -g zpa.tsv -G hpoa_g2p -i sqlite:obo:phenio information-content -p i --use-associations .all > zpa_ic.tsv'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel --information-content-file zpa_ic.tsv -p i --set1-file HPO_terms.txt --set2-file ZP_terms.txt -O csv -o $HP_VS_ZP_PREFIX-$BUILDSTARTDATE.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                }
            }
        }

        stage('Upload results for HP vs ZP') {
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              
                                // upload to remote
				                sh 'tar -czvf HP_vs_ZP_semsimian.tsv.tar.gz $HP_VS_ZP_PREFIX-$BUILDSTARTDATE.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate HP_vs_ZP_semsimian.tsv.tar.gz $S3PROJECTDIR'
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
