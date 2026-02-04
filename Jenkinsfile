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
                    // Get changed files since last commit
                    def changes = sh(
                        script: 'git diff --name-only HEAD~1 HEAD || echo ""',
                        returnStdout: true
                    ).trim()

                    echo "Changed files:\n${changes}"

                    def changedFiles = changes.split('\n').findAll { it.trim() }

                    // --- Determine if build is needed at all ---
                    def buildPaths = ['terraform/', 'ansible/', 'scripts/', 'Jenkinsfile']
                    env.SHOULD_BUILD = 'false'
                    for (path in buildPaths) {
                        if (changedFiles.any { it.startsWith(path) }) {
                            env.SHOULD_BUILD = 'true'
                            break
                        }
                    }

                    if (env.SHOULD_BUILD == 'false') {
                        currentBuild.description = 'Skipped: docs/non-IaC changes only'
                        echo 'No infrastructure changes detected. Skipping remaining stages.'
                        return
                    }

                    // --- Classify changes ---
                    env.NEEDS_TF_PROXMOX = changedFiles.any {
                        it.startsWith('terraform/proxmox/') || it.startsWith('terraform/modules/')
                    }.toString()
                    env.NEEDS_TF_ESXI = changedFiles.any {
                        it.startsWith('terraform/esxi/') || it.startsWith('terraform/modules/')
                    }.toString()
                    env.NEEDS_TF = (env.NEEDS_TF_PROXMOX == 'true' || env.NEEDS_TF_ESXI == 'true').toString()
                    env.NEEDS_ANSIBLE_LINT = changedFiles.any { it.startsWith('ansible/') }.toString()

                    // Broad-impact paths: only syntax-check, no auto-deploy
                    def broadImpactPrefixes = [
                        'ansible/roles/common/',
                        'ansible/roles/docker/',
                        'ansible/inventory/group_vars/',
                        'terraform/modules/',
                    ]

                    def playbooks = [] as Set
                    def unmatchedFiles = []

                    for (file in changedFiles) {
                        // Skip non-IaC files and broad-impact paths
                        if (!buildPaths.any { file.startsWith(it) }) continue
                        if (broadImpactPrefixes.any { file.startsWith(it) }) continue
                        // Skip files that don't need playbook matching
                        if (file == 'Jenkinsfile') continue
                        if (file.startsWith('scripts/')) continue
                        if (file.startsWith('ansible/inventory/group_vars/')) continue
                        if (file.startsWith('ansible/requirements.yml')) continue
                        if (file.startsWith('ansible/ansible.cfg')) continue

                        def matched = false

                        // 1. Terraform service file: <service>.tf -> deploy-<service>.yml
                        def tfMatcher = (file =~ /^terraform\/(?:proxmox|esxi)\/([^\/]+)\.tf$/)
                        def tfServiceName = tfMatcher ? tfMatcher[0][1] : null
                        tfMatcher = null  // Discard Matcher before CPS checkpoint
                        if (tfServiceName) {
                            // Skip non-service tf files
                            if (!['versions', 'provider', 'variables', 'main', 'provisioning', 'pve-cluster'].contains(tfServiceName)) {
                                def candidate = "deploy-${tfServiceName}.yml"
                                if (fileExists("ansible/playbooks/${candidate}")) {
                                    playbooks.add(candidate)
                                    matched = true
                                }
                            } else {
                                matched = true  // Infrastructure file, no playbook needed
                            }
                        }

                        // 2. Ansible role: roles/<role>/** -> deploy-<role>.yml
                        if (!matched) {
                            def roleMatcher = (file =~ /^ansible\/roles\/([^\/]+)\//)
                            def roleName = roleMatcher ? roleMatcher[0][1] : null
                            roleMatcher = null  // Discard Matcher before CPS checkpoint
                            if (roleName) {
                                def candidate = "deploy-${roleName}.yml"
                                if (fileExists("ansible/playbooks/${candidate}")) {
                                    playbooks.add(candidate)
                                    matched = true
                                }
                            }
                        }

                        // 3. Playbook file itself: deploy-*.yml
                        if (!matched) {
                            def pbMatcher = (file =~ /^ansible\/playbooks\/(deploy-[^\/]+\.yml)$/)
                            def pbName = pbMatcher ? pbMatcher[0][1] : null
                            pbMatcher = null  // Discard Matcher before CPS checkpoint
                            if (pbName) {
                                playbooks.add(pbName)
                                matched = true
                            }
                        }

                        // 4. Host vars: host_vars/<host>.yml -> deploy-<host>.yml
                        if (!matched) {
                            def hvMatcher = (file =~ /^ansible\/inventory\/host_vars\/([^\/\.]+)/)
                            def hostName = hvMatcher ? hvMatcher[0][1] : null
                            hvMatcher = null  // Discard Matcher before CPS checkpoint
                            if (hostName) {
                                def candidate = "deploy-${hostName}.yml"
                                if (fileExists("ansible/playbooks/${candidate}")) {
                                    playbooks.add(candidate)
                                    matched = true
                                }
                            }
                        }

                        if (!matched) {
                            unmatchedFiles.add(file)
                        }
                    }

                    // Set environment variables for downstream stages
                    // Note: Force unique() because CPS serialization may break Set behavior
                    env.ANSIBLE_PLAYBOOKS = playbooks.toList().unique().join(',')

                    // --- Summary ---
                    echo "=== Build Scope ==="
                    echo "Needs Terraform: ${env.NEEDS_TF}"
                    echo "Needs Ansible Lint: ${env.NEEDS_ANSIBLE_LINT}"

                    if (playbooks) {
                        echo "Playbooks to deploy: ${playbooks.join(', ')}"
                    } else {
                        echo "No specific playbooks to deploy."
                    }
                    if (unmatchedFiles) {
                        echo "WARNING: The following changed files could not be matched to a playbook:"
                        unmatchedFiles.each { echo "  - ${it}" }
                        echo "Please review and deploy manually if needed."
                    }

                    // Build description for quick visibility in build history
                    def desc = []
                    if (env.NEEDS_TF == 'true') desc.add('TF')
                    if (playbooks) desc.add(playbooks.join(', '))
                    if (unmatchedFiles) desc.add("⚠ ${unmatchedFiles.size()} unmatched")
                    if (!desc) desc.add('validate only')
                    currentBuild.description = desc.join(' | ')
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
                // Initialize Terraform providers
                // - For TF changes: only init the affected directory
                // - For Ansible deploy: both needed (dynamic inventory depends on terraform show)
                script {
                    def initProxmox = (env.NEEDS_TF_PROXMOX == 'true' || env.ANSIBLE_PLAYBOOKS?.trim())
                    def initEsxi = (env.NEEDS_TF_ESXI == 'true' || env.ANSIBLE_PLAYBOOKS?.trim())
                    if (initProxmox) {
                        dir('terraform/proxmox') { sh 'terraform init -input=false' }
                    }
                    if (initEsxi) {
                        dir('terraform/esxi') { sh 'terraform init -input=false' }
                    }
                    if (!initProxmox && !initEsxi) {
                        echo 'Skipping Terraform init: no TF changes and no playbooks to deploy.'
                    }
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
                    when { environment name: 'NEEDS_TF_PROXMOX', value: 'true' }
                    steps {
                        dir('terraform/proxmox') {
                            sh 'terraform validate'
                            sh 'terraform fmt -check -recursive || echo "Warning: Some files need formatting"'
                        }
                    }
                }
                stage('Ansible Lint') {
                    when { environment name: 'NEEDS_ANSIBLE_LINT', value: 'true' }
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
            when {
                environment name: 'SHOULD_BUILD', value: 'true'
                environment name: 'NEEDS_TF_PROXMOX', value: 'true'
            }
            steps {
                dir('terraform/proxmox') {
                    script {
                        def exitCode = sh(
                            script: 'terraform plan -out=tfplan -input=false -detailed-exitcode',
                            returnStatus: true
                        )
                        if (exitCode == 1) {
                            error 'Terraform plan failed'
                        }
                        env.HAS_TF_PLAN_CHANGES = (exitCode == 2) ? 'true' : 'false'
                        if (env.HAS_TF_PLAN_CHANGES == 'false') {
                            echo 'No infrastructure changes detected in Terraform plan.'
                        }
                    }
                }
            }
        }

        stage('Approval - Terraform Apply') {
            when {
                environment name: 'SHOULD_BUILD', value: 'true'
                environment name: 'HAS_TF_PLAN_CHANGES', value: 'true'
            }
            steps {
                input message: 'Review the Terraform plan above. Proceed with apply?',
                      ok: 'Apply'
            }
        }

        stage('Terraform Apply') {
            when {
                environment name: 'SHOULD_BUILD', value: 'true'
                environment name: 'HAS_TF_PLAN_CHANGES', value: 'true'
            }
            steps {
                dir('terraform/proxmox') {
                    sh 'terraform apply -input=false tfplan'
                }
            }
        }

        stage('Refresh Inventory') {
            when {
                environment name: 'SHOULD_BUILD', value: 'true'
                anyOf {
                    environment name: 'NEEDS_TF', value: 'true'
                    expression { env.ANSIBLE_PLAYBOOKS?.trim() }
                }
            }
            steps {
                sh './scripts/refresh-terraform-state.sh'
            }
        }

        stage('Approval - Ansible Deploy') {
            when {
                environment name: 'SHOULD_BUILD', value: 'true'
                expression { env.ANSIBLE_PLAYBOOKS?.trim() }
            }
            steps {
                script {
                    def playbookList = env.ANSIBLE_PLAYBOOKS.split(',').collect { "  - ${it}" }.join('\n')
                    input message: "The following playbooks will be executed:\n${playbookList}\n\nProceed with Ansible deployment?",
                          ok: 'Deploy'
                }
            }
        }

        stage('Ansible Deploy') {
            when {
                environment name: 'SHOULD_BUILD', value: 'true'
                expression { env.ANSIBLE_PLAYBOOKS?.trim() }
            }
            steps {
                dir('ansible') {
                    script {
                        def playbooks = env.ANSIBLE_PLAYBOOKS.split(',')
                        for (pb in playbooks) {
                            echo "Deploying: ${pb}"
                            sh "ansible-playbook playbooks/${pb}"
                        }
                    }
                }
            }
        }

        stage('Sync to Notion') {
            when {
                environment name: 'SHOULD_BUILD', value: 'true'
                expression { env.ANSIBLE_PLAYBOOKS?.trim() }
            }
            steps {
                catchError(buildResult: 'SUCCESS', stageResult: 'FAILURE') {
                    withCredentials([
                        string(credentialsId: 'notion-token', variable: 'NOTION_TOKEN'),
                        string(credentialsId: 'notion-database-id', variable: 'NOTION_DATABASE_ID')
                    ]) {
                        sh 'NOTION_DRY_RUN=false python3 scripts/sync-to-notion.py'
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
