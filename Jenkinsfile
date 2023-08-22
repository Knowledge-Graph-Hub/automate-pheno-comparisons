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
        S3PROJECTDIR = '' // no trailing slash

	RESNIK_THRESHOLD = '4.0' // value for min-ancestor-information-content parameter

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
			sh './venv/bin/pip install oaklib s3cmd'
                }
            }
        }

        stage('Run similarity ') {
            steps {
                dir('./working') {
		    sh '. venv/bin/activate && runoak -i sqlite:obo:phenio ontology-metadata --all'
                    sh '. venv/bin/activate && runoak -i sqlite:obo:hp descendants -p i HP:0000118 > HPO_terms.txt'
                    sh '. venv/bin/activate && runoak -i sqlite:obo:mp descendants -p i MP:0000001 > MP_terms.txt'
                    sh '. venv/bin/activate && runoak -i semsimian:sqlite:obo:phenio similarity --no-autolabel -p i --set1-file HPO_terms.txt --set2-file MP_terms.txt -O csv -o HP_vs_MP_semsimian.tsv --min-ancestor-information-content $RESNIK_THRESHOLD'
                }
            }
        }

        stage('Upload result') {
            // Store similarity results at s3://kg-hub-public-data/monarch/
            steps {
                dir('./working') {
                    script {
                            withCredentials([
					            file(credentialsId: 's3cmd_kg_hub_push_configuration', variable: 'S3CMD_CFG'),
					            file(credentialsId: 'aws_kg_hub_push_json', variable: 'AWS_JSON'),
					            string(credentialsId: 'aws_kg_hub_access_key', variable: 'AWS_ACCESS_KEY_ID'),
					            string(credentialsId: 'aws_kg_hub_secret_key', variable: 'AWS_SECRET_ACCESS_KEY')]) {
                                                              

                                // upload to remote
				sh 'tar -czvf HP_vs_MP_semsimian.tsv.tar.gz HP_vs_MP_semsimian.tsv'
                                sh '. venv/bin/activate && s3cmd -c $S3CMD_CFG put -pr --acl-public --cf-invalidate HP_vs_MP_semsimian.tsv.tar.gz s3://kg-hub-public-data/monarch/'
                                // Should now appear at:
                                // https://kg-hub.berkeleybop.io/monarch/
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
