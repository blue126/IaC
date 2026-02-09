# Jenkins Job Configuration: Webhook-Router

## Prerequisites

- **Generic Webhook Trigger Plugin** >= 1.86.0 (required for `tokenCredentialId` support)
  - If using an older version, either upgrade the plugin or temporarily replace `tokenCredentialId` with `token` in the Jenkinsfile
- **Pipeline Plugin** (standard Jenkins installation)
- **Git Plugin** (standard Jenkins installation)

## Manual Configuration Steps (Jenkins UI)

### Step 1: Create Webhook Token Credential

1. Navigate to Jenkins: http://192.168.1.107:8080/credentials/
2. Select the appropriate domain (or "Global")
3. Click "Add Credentials"
4. **Kind**: Secret text
5. **Secret**: Enter your chosen webhook token value (e.g., a random string)
6. **ID**: `netbox-webhook-token`
7. **Description**: `Token for NetBox webhook trigger`
8. Click "Create"

> This credential is referenced by `tokenCredentialId` in the Jenkinsfile.  
> The same token value must be configured in the NetBox Event Rule URL.

### Step 2: Create New Pipeline Job

1. Navigate to Jenkins: http://192.168.1.107:8080
2. Click "New Item"
3. Enter item name: **Webhook-Router**
4. Select: **Pipeline**
5. Click OK

### Step 3: General Settings

- **Description**: `NetBox Webhook Router Pipeline - Routes VM/Device events to platform-specific pipelines`
- **Discard old builds**: ✅ Enabled
  - Strategy: Log Rotation
  - Days to keep builds: 30
  - Max # of builds to keep: 50

### Step 4: Build Triggers

⚠️ **Important**: Do NOT check "Generic Webhook Trigger" in the UI trigger section.  
The trigger is configured **inside the Jenkinsfile** using the `triggers {}` block.

### Step 5: Pipeline Configuration

- **Definition**: Pipeline script from SCM
- **SCM**: Git
- **Repository URL**: `git@github.com:blue126/IaC.git`
- **Credentials**: Select appropriate Git credentials
- **Branches to build**: `*/main` (or your default branch)
- **Script Path**: `Jenkinsfile-webhook-router`

### Step 6: Save Configuration

Click "Save" at the bottom of the page.

---

## Verification Steps

### Verify Job Exists

```bash
# Check if job is accessible via API
curl -s http://192.168.1.107:8080/job/Webhook-Router/api/json | jq -r '.name'
# Expected output: Webhook-Router
```

### Verify Git Configuration

```bash
# Check SCM configuration
curl -s http://192.168.1.107:8080/job/Webhook-Router/api/json | jq '.scm'
```

### Trigger Manual Build

```bash
# Trigger build with parameters
curl -X POST "http://192.168.1.107:8080/job/Webhook-Router/buildWithParameters?MANUAL_PLATFORM=proxmox&MANUAL_OBJECT_ID=999&MANUAL_OBJECT_NAME=test-manual"
```

---

## Jenkins Configuration as Code (JCasC)

If your Jenkins uses JCasC, add this to your `jenkins.yaml`:

```yaml
jobs:
  - script: >
      pipelineJob('Webhook-Router') {
        description('NetBox Webhook Router Pipeline - Routes VM/Device events to platform-specific pipelines')
        logRotator {
          daysToKeep(30)
          numToKeep(50)
        }
        definition {
          cpsScm {
            scm {
              git {
                remote {
                  url('git@github.com:blue126/IaC.git')
                  credentials('github-ssh-key')
                }
                branches('*/main')
              }
            }
            scriptPath('Jenkinsfile-webhook-router')
          }
        }
        parameters {
          stringParam('MANUAL_PLATFORM', '', 'Manual platform override (proxmox/esxi/physical)')
          stringParam('MANUAL_OBJECT_ID', '', 'Manual object ID for testing')
          stringParam('MANUAL_OBJECT_NAME', '', 'Manual object name for testing')
        }
      }
```

---

## Webhook URL

After job creation, the webhook endpoint will be:

```
http://192.168.1.107:8080/generic-webhook-trigger/invoke
```

**Token authentication**: The token should be sent via HTTP header (not URL query string)
to avoid exposure in access logs and proxy logs.

**NetBox Webhook configuration** (Operations > Webhooks):
- **URL**: `http://192.168.1.107:8080/generic-webhook-trigger/invoke`
- **Additional Headers**: `token: <value-from-netbox-webhook-token-credential>`

The token value is stored in Jenkins credential `netbox-webhook-token` (Step 1).  
The Generic Webhook Trigger plugin accepts the token via header, query parameter, or Bearer token.

---

## Troubleshooting

### Problem: "No valid crumb was included in the request"

**Solution**: If using API, you need to include CSRF token:

```bash
CRUMB=$(curl -s 'http://192.168.1.107:8080/crumbIssuer/api/xml?xpath=concat(//crumbRequestField,":",//crumb)')
curl -X POST -H "$CRUMB" "http://192.168.1.107:8080/job/Webhook-Router/build"
```

### Problem: Generic Webhook Trigger not firing

**Solution**: 
1. Ensure Generic Webhook Trigger plugin is installed
2. Verify trigger configuration is in Jenkinsfile (not UI)
3. Run job manually once to register the trigger
4. Check Jenkins system log for webhook events

### Problem: Cannot find Jenkinsfile

**Solution**:
1. Verify Git repository is accessible from Jenkins
2. Check Script Path is exactly: `Jenkinsfile-webhook-router`
3. Ensure file is committed to the correct branch
4. Trigger "Build Now" to force SCM poll
