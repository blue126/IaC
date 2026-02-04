# Notion Sync Setup Guide

## 1. Create Integration (Get Token)

1. Go to [https://www.notion.so/my-integrations](https://www.notion.so/my-integrations).
2. Click **New integration**.
3. Name it (e.g., "Homelab Sync").
4. Select the workspace.
5. Click **Submit**.
6. Copy the **"Internal Integration Secret"**. This is your `NOTION_TOKEN`.

## 2. Prepare Database

1. Create a new Page in Notion.
2. Type `/table` and select **Table view** -> **New database**.
3. Add/Rename columns to match exactly:
   - **Name** (Type: Title) -> *Stores Hostname*
   - **IP Address** (Type: Text)
   - **VMID** (Type: Number)
   - **Status** (Type: Select)
   - **Last Updated** (Type: Date)
4. **Connect Integration**:
   - Click the `...` menu at the top-right of the page.
   - Scroll to **Connections**.
   - Search for and select your integration ("Homelab Sync").
   - *If you don't do this, the script cannot access the database!*

## 3. Configure Script (Column Mapping)

The script `scripts/sync-to-notion.py` has a `COLUMN_MAPPING` section at the top. 
**You MUST match these values to your actual Notion Database column names.**

Default configuration:
```python
COLUMN_MAPPING = {
    "hostname": "Resource",       # Title property (Primary Key)
    "ip": "IP Address",           # Text property
    "vmid": "VMID",               # Number property
    "status": "Status",           # Select property
    "updated": "Last Updated"     # Date property
}
```

If your columns are named differently (e.g., "Host IP" instead of "IP Address"), edit the script to match.

## 4. Get Database ID

1. Open the database page in browser (or "Copy link to view").
2. The URL looks like: `https://www.notion.so/myworkspace/a8aec43384f447ed84390e8e42c2e089?v=...`
3. The ID is the 32-character part between `/` and `?`.
   - Example ID: `a8aec43384f447ed84390e8e42c2e089`
   - This is your `NOTION_DATABASE_ID`.

## 4. Run Manually (Test)

```bash
# 1. Install dependencies
pip install -r scripts/requirements.txt

# 2. Set env vars and run
export NOTION_TOKEN="secret_..."
export NOTION_DATABASE_ID="a8ae..."
python3 scripts/sync-to-notion.py
```

## 5. Jenkins Integration

Add this to your `Jenkinsfile` in the `post { success { ... } }` block:

```groovy
withCredentials([string(credentialsId: 'notion-token', variable: 'NOTION_TOKEN'), 
                 string(credentialsId: 'notion-db-id', variable: 'NOTION_DATABASE_ID')]) {
    sh 'pip install -r scripts/requirements.txt'
    sh 'python3 scripts/sync-to-notion.py'
}
```
*(Note: You need to add `notion-token` and `notion-db-id` to Jenkins Credentials first)*
