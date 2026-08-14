#!/bin/bash
# Wait for the pinned artifact, verify it, then perform a rollback-safe cutover.
set -euo pipefail

readonly model_dir="/data/models/DeepSeek-V4-Flash-0731"
readonly harness_dir="/opt/deepseek-v4/harness"
readonly evidence_dir="/var/lib/deepseek-v4/evidence"
readonly compose_file="/opt/deepseek-v4/docker-compose.yml"
readonly legacy_unit="llama-server@qwen3-vl-32b.service"
readonly webui_database="/opt/open-webui/data/webui.db"
readonly webui_backup="/var/backups/open-webui/deepseek-v4-flash-0731-7872f01b-webui.db"

log() { printf '[deepseek-v4-activation] %s\n' "$*"; }

while pgrep -u llm -f 'hf download deepseek-ai/DeepSeek-V4-Flash-0731' >/dev/null; do
  log 'waiting for pinned model download'
  sleep 60
done

python3 "$harness_dir/model-manifest-fetch.py" \
  --repository deepseek-ai/DeepSeek-V4-Flash-0731 \
  --revision 7872f01b1d1fe23eabc4c98b48bffcef5a386062 \
  --output "$evidence_dir/model-manifest.json"

python3 - "$model_dir" "$evidence_dir/model-manifest.json" <<'PY'
import hashlib
import json
import sys
from pathlib import Path

model_dir = Path(sys.argv[1])
manifest = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
for item in manifest:
    path = model_dir / item["path"]
    if not path.is_file() or path.stat().st_size != item["size"]:
        raise SystemExit(f"artifact size verification failed: {item['path']}")
    expected = item.get("sha256")
    if expected:
        digest_builder = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(8 * 1024 * 1024), b""):
                digest_builder.update(chunk)
        digest = digest_builder.hexdigest()
        if digest != expected:
            raise SystemExit(f"artifact checksum verification failed: {item['path']}")
index = json.loads((model_dir / "model.safetensors.index.json").read_text())
declared = {item["path"] for item in manifest}
if not set(index["weight_map"].values()).issubset(declared):
    raise SystemExit("safetensors index references an undeclared shard")
PY

rollback() {
  log 'DeepSeek readiness failed; restoring legacy Qwen'
  docker compose -f "$compose_file" --project-name deepseek-v4 down || true
  systemctl start "$legacy_unit" || true
}

set_webui_default_model() {
  install -d -m 0750 /var/backups/open-webui
  python3 "$harness_dir/sqlite-backup.py" \
    --source "$webui_database" --target "$webui_backup"
  python3 - "$webui_database" <<'PY'
import json
import sqlite3
import sys
from datetime import datetime, timezone

connection = sqlite3.connect(sys.argv[1])
row = connection.execute("SELECT id, data FROM config WHERE id = 1").fetchone()
if row is None:
    raise SystemExit("Open WebUI config row 1 is absent")
document = json.loads(row[1])
ui = document.get("ui")
if not isinstance(ui, dict):
    raise SystemExit("Open WebUI config has no ui object")
ui["default_models"] = "deepseek-v4-flash"
ui["default_pinned_models"] = "deepseek-v4-flash"
connection.execute(
    "UPDATE config SET data = ?, updated_at = ? WHERE id = ?",
    (json.dumps(document, separators=(",", ":")),
     datetime.now(timezone.utc).replace(tzinfo=None).isoformat(sep=" "), row[0]),
)
connection.commit()
connection.close()
PY
}

trap rollback ERR
systemctl stop "$legacy_unit"
systemctl daemon-reload
systemctl start deepseek-v4.service

for _ in $(seq 1 80); do
  if curl --fail --silent --show-error http://127.0.0.1:8080/v1/models \
      | grep -q 'deepseek-v4-flash'; then
    set_webui_default_model
    systemctl disable "$legacy_unit"
    # Absence is already a retired legacy switch path; do not roll back a
    # healthy DeepSeek deployment merely because there is nothing left to lock.
    if [[ -e /opt/llm-server/switch-model.sh ]]; then
      chmod 0000 /opt/llm-server/switch-model.sh
    fi
    trap - ERR
    log 'DeepSeek V4 is ready; legacy Qwen retired'
    exit 0
  fi
  sleep 15
done

false
