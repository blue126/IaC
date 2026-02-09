// Jenkins Job DSL Script to create Webhook-Router Pipeline Job
// Usage: Run this script via Jenkins Script Console or Job DSL plugin

pipelineJob('Webhook-Router') {
    description('NetBox Webhook Router Pipeline - Routes VM/Device events to platform-specific pipelines based on infrastructure_platform custom field')
    
    // Log rotation
    logRotator {
        daysToKeep(30)
        numToKeep(50)
        artifactDaysToKeep(-1)
        artifactNumToKeep(-1)
    }
    
    // Parameters (also defined in Jenkinsfile, but including here for UI visibility)
    parameters {
        stringParam('MANUAL_PLATFORM', '', 'Manual platform override for testing (proxmox/esxi/physical)')
        stringParam('MANUAL_OBJECT_ID', '', 'Manual NetBox object ID for testing')
        stringParam('MANUAL_OBJECT_NAME', '', 'Manual NetBox object name for testing')
    }
    
    // Pipeline definition from SCM
    definition {
        cpsScm {
            scm {
                git {
                    remote {
                        url('https://github.com/your-org/IaC.git')  // TODO: Update with actual repo URL
                        credentials('github-credentials-id')  // TODO: Update with actual credentials ID
                    }
                    branches('*/main')
                    extensions {
                        cleanBeforeCheckout()
                    }
                }
            }
            scriptPath('Jenkinsfile-webhook-router')
            lightweight(true)
        }
    }
    
    // NOTE: Generic Webhook Trigger configuration is in Jenkinsfile, not here
    // The trigger block in Jenkinsfile will auto-register the webhook endpoint
}

println "Webhook-Router job created successfully"
println "Webhook endpoint: http://192.168.1.107:8080/generic-webhook-trigger/invoke?token=netbox-webhook"
println ""
println "Next steps:"
println "1. Run this job manually once to register the Generic Webhook Trigger"
println "2. Verify webhook endpoint is accessible from NetBox"
println "3. Test with manual trigger or curl command"
