pipeline {
    agent any

    environment {
        // Terraform Cloud token
        TF_TOKEN_app_terraform_io = credentials('terraform-cloud-token')
        // Ansible configuration
        ANSIBLE_CONFIG = "${WORKSPACE}/ansible/ansible.cfg"
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

        stage('Setup') {
            steps {
                // Write Ansible Vault password to file
                withCredentials([string(credentialsId: 'ansible-vault-password', variable: 'VAULT_PASS')]) {
                    sh '''
                        echo "$VAULT_PASS" > $ANSIBLE_VAULT_PASSWORD_FILE
                        chmod 600 $ANSIBLE_VAULT_PASSWORD_FILE
                    '''
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
            parallel {
                stage('Terraform Validate') {
                    steps {
                        dir('terraform/proxmox') {
                            sh 'terraform init -input=false'
                            sh 'terraform validate'
                            // Check format but don't fail (warning only)
                            sh 'terraform fmt -check -recursive || echo "Warning: Some files need formatting"'
                        }
                    }
                }
                stage('Ansible Lint') {
                    steps {
                        // Run from project root for relative inventory paths
                        sh 'ansible-lint --version'
                        sh 'ansible-playbook ansible/playbooks/*.yml --syntax-check'
                    }
                }
            }
        }

        stage('Terraform Plan') {
            steps {
                dir('terraform/proxmox') {
                    sh 'terraform plan -out=tfplan -input=false'
                }
            }
        }

        stage('Approval - Terraform Apply') {
            steps {
                input message: 'Review the Terraform plan above. Proceed with apply?',
                      ok: 'Apply'
            }
        }

        stage('Terraform Apply') {
            steps {
                dir('terraform/proxmox') {
                    sh 'terraform apply -input=false tfplan'
                }
            }
        }

        stage('Refresh Inventory') {
            steps {
                sh './scripts/refresh_terraform_state.sh'
            }
        }

        stage('Approval - Ansible Deploy') {
            steps {
                input message: 'Terraform apply completed. Proceed with Ansible deployment?',
                      ok: 'Deploy'
            }
        }

        stage('Ansible Deploy') {
            steps {
                // Run from project root for relative inventory paths
                sh 'ansible-playbook ansible/playbooks/deploy-jenkins.yml --tags verify'
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
