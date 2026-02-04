pipeline {
    agent any

    environment {
        // Terraform Cloud token
        TF_TOKEN_app_terraform_io = credentials('terraform-cloud-token')
        // Ansible Vault password file path
        ANSIBLE_VAULT_PASSWORD_FILE = "${WORKSPACE}/ansible/.vault_pass"
    }

    options {
        // Keep last 10 builds
        buildDiscarder(logRotator(numToKeepStr: '10'))
        // Timeout after 30 minutes
        timeout(time: 30, unit: 'MINUTES')
        // Don't run concurrent builds
        disableConcurrentBuilds()
        // Enable ANSI color output
        ansiColor('xterm')
    }

    stages {
        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        stage('Check Changes') {
            steps {
                script {
                    // Get changed files since last successful build
                    def changes = sh(
                        script: 'git diff --name-only HEAD~1 HEAD || echo ""',
                        returnStdout: true
                    ).trim()

                    echo "Changed files:\n${changes}"

                    // Paths that should trigger a build
                    def buildPaths = ['terraform/', 'ansible/', 'scripts/', 'Jenkinsfile']
                    env.SHOULD_BUILD = 'false'

                    for (path in buildPaths) {
                        if (changes.split('\n').any { it.startsWith(path) }) {
                            env.SHOULD_BUILD = 'true'
                            break
                        }
                    }

                    if (env.SHOULD_BUILD == 'false') {
                        currentBuild.description = 'Skipped: docs/non-IaC changes only'
                        echo "No infrastructure changes detected. Skipping remaining stages."
                    } else {
                        echo "Infrastructure changes detected. Proceeding with build."
                    }
                }
            }
        }

        stage('Setup') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                // Write Ansible Vault password to file
                withCredentials([string(credentialsId: 'ansible-vault-password', variable: 'VAULT_PASS')]) {
                    sh '''
                        echo "$VAULT_PASS" > $ANSIBLE_VAULT_PASSWORD_FILE
                        chmod 600 $ANSIBLE_VAULT_PASSWORD_FILE
                    '''
                }
                // Initialize Terraform providers (needed by Ansible dynamic inventory)
                dir('terraform/proxmox') {
                    sh 'terraform init -input=false'
                }
                dir('terraform/esxi') {
                    sh 'terraform init -input=false'
                }
                // Generate Terraform secrets from Ansible Vault
                sh './scripts/get-secrets.sh'
                // Install Ansible Galaxy collections if not present
                dir('ansible') {
                    sh '''
                        if [ ! -d "collections/ansible_collections/community/docker" ] || \
                           [ ! -d "collections/ansible_collections/cloud/terraform" ]; then
                            echo "Installing Ansible Galaxy collections..."
                            ansible-galaxy collection install -r requirements.yml -p collections
                        else
                            echo "Ansible collections already installed, skipping..."
                        fi
                    '''
                }

            }
        }

        stage('Validate') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            parallel {
                stage('Terraform Validate') {
                    steps {
                        dir('terraform/proxmox') {
                            sh 'terraform validate'
                            // Check format but don't fail (warning only)
                            sh 'terraform fmt -check -recursive || echo "Warning: Some files need formatting"'
                        }
                    }
                }
                stage('Ansible Lint') {
                    steps {
                        dir('ansible') {
                            sh 'ansible-lint --version'
                            sh 'ansible-playbook playbooks/*.yml --syntax-check'
                        }
                    }
                }
            }
        }

        stage('Terraform Plan') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                dir('terraform/proxmox') {
                    sh 'terraform plan -out=tfplan -input=false'
                }
            }
        }

        stage('Approval - Terraform Apply') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                input message: 'Review the Terraform plan above. Proceed with apply?',
                      ok: 'Apply'
            }
        }

        stage('Terraform Apply') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                dir('terraform/proxmox') {
                    sh 'terraform apply -input=false tfplan'
                }
            }
        }

        stage('Refresh Inventory') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                sh './scripts/refresh_terraform_state.sh'
            }
        }

        stage('Approval - Ansible Deploy') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                input message: 'Terraform apply completed. Proceed with Ansible deployment?',
                      ok: 'Deploy'
            }
        }

        stage('Ansible Deploy') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                dir('ansible') {
                    sh 'ansible-playbook playbooks/deploy-jenkins.yml --tags verify'
                }
            }
        }

        stage('Sync to Notion') {
            when { environment name: 'SHOULD_BUILD', value: 'true' }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    withCredentials([
                        string(credentialsId: 'notion-token', variable: 'NOTION_TOKEN'),
                        string(credentialsId: 'notion-database-id', variable: 'NOTION_DATABASE_ID')
                    ]) {
                        sh 'NOTION_DRY_RUN=false python3 scripts/sync_to_notion.py'
                    }
                }
            }
        }
    }

    post {
        always {
            // Cleanup sensitive files
            sh 'rm -f $ANSIBLE_VAULT_PASSWORD_FILE'
            sh 'rm -f terraform/proxmox/secrets.auto.tfvars'
            sh 'rm -f terraform/oci/secrets.auto.tfvars'
        }
        success {
            echo 'Pipeline completed successfully!'
        }
        failure {
            echo 'Pipeline failed. Check the logs for details.'
        }
    }
}
