#!/bin/bash
# Back up gateway businesses sequentially with the native Proxmox Backup client.
set -eo pipefail
umask 077

# Edit non-secret settings here, or provide the PBS values through the controller.
# PBS_REPOSITORY format: user@realm!token@server:datastore
export PBS_REPOSITORY="${PBS_REPOSITORY:-}"
# Export PBS_FINGERPRINT when the server certificate needs explicit trust.
# The controller supplies the secret in PBS_PASSWORD; never store it in this file.
client_bin=proxmox-backup-client
stop_timeout=60
lock_dir=/var/lock

die() { printf 'ERROR: %s\n' "$*" >&2; exit 1; }
if [[ $# != 2 || "$1" != backup ]]; then
    printf 'Usage: %s backup <business|all>\n' "$0" >&2
    exit 2
fi
business="$2"
case "${business}" in
    all) businesses=(xiaozhi hermes open-webui codex-proxy cn-proxy youtube-mcp);;
    xiaozhi|hermes|open-webui|codex-proxy|cn-proxy|youtube-mcp|qnetd-witness) businesses=("${business}");;
    *) die "Unknown business: ${business}";;
esac
unset DOCKER_CONTEXT
export DOCKER_HOST=unix:///var/run/docker.sock
[[ -n "${PBS_REPOSITORY:-}" ]] || die 'PBS_REPOSITORY is required'
[[ -n "${PBS_PASSWORD:-}" ]] || die 'Supply the PBS token through PBS_PASSWORD'
[[ "${stop_timeout}" =~ ^[1-9][0-9]*$ ]] || die 'stop_timeout must be a positive number of seconds'
for tool in docker flock xargs "${client_bin}"; do command -v "${tool}" >/dev/null || die "Missing existing tool: ${tool}"; done
# Keep the native lock open through EXIT cleanup; never unlink its shared inode.
exec 9>"${lock_dir}/gateway-backup.lock"
flock -n 9 || die 'Another business backup is active'

cleanup() {
    local rc="$1" container
    # Finish cleanup on cancellation, then stop the batch; preserve any prior error.
    trap 'if (( rc == 0 )); then rc=130; fi' INT
    trap 'if (( rc == 0 )); then rc=143; fi' TERM
    # Capture cancellation received as the upload handler hands over to cleanup.
    if (( rc == 0 && cancel_code )); then rc="${cancel_code}"; fi
    trap - EXIT
    if (( stopping )); then
        for container in "${running[@]}"; do
            if ! (trap '' INT TERM; exec docker start "${container}") >/dev/null; then
                printf 'ERROR: Failed to restart %s; manual intervention required\n' "${container}" >&2
                if (( rc == 0 )); then rc=1; fi
            fi
        done
    fi
    if [[ -n "${metadata_dir}" ]] && ! (trap '' INT TERM; exec rm -rf -- "${metadata_dir}"); then
        printf 'ERROR: Could not remove private metadata: %s\n' "${metadata_dir}" >&2
        if (( rc == 0 )); then rc=1; fi
    fi
    if (( rc == 0 )); then
        printf 'Backup completed: host/gateway-%s. Original running containers received start requests; verify application health separately.\n' "${business}"
    else
        printf 'ERROR: Backup failed or cancelled: host/gateway-%s (exit %s); no later business will run.\n' "${business}" "${rc}" >&2
    fi
    if (( rc == 0 )); then
        trap 'exit 130' INT
        trap 'exit 143' TERM
    fi
    return "${rc}"
}
cancel_backup() {
    local signal
    if (( cancel_code == 0 )); then cancel_signal="$1"; cancel_code="$2"; fi
    if [[ -n "${backup_pid}" && -n "${cancel_signal}" ]]; then
        signal="${cancel_signal}"; cancel_signal=""
        kill -s "${signal}" "${backup_pid}" 2>/dev/null || true
    fi
}

if [[ "${business}" == all ]]; then
    printf 'Batch order: xiaozhi -> hermes -> open-webui -> codex-proxy -> cn-proxy -> youtube-mcp.\n'
    printf 'qnetd-witness is excluded from all; invoke it separately after approved quorum maintenance shutdown.\n'
fi
business_index=0
for business in "${businesses[@]}"; do
    business_index=$((business_index + 1))
    containers=(); sources=(); clean_exit=(); volume_mount=(); backup_options=()
    require_stopped=false
    running=(); stopping=0; metadata_dir=""
    backup_pid=""; cancel_signal=""; cancel_code=0; backup_rc=0
    trap 'cleanup "$?"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    printf 'Backup progress %s/%s: %s\n' "${business_index}" "${#businesses[@]}" "${business}"
    # Containers are in start order; stop in reverse order.
    case "${business}" in
        xiaozhi)
            containers=(xiaozhi-esp32-server-db xiaozhi-esp32-server-redis xiaozhi-esp32-server xiaozhi-esp32-server-web xz-mqtt-gw)
            sources=(xiaozhi.pxar:/mnt/data/xiaozhi mqtt.pxar:/mnt/data/xiaozhi-mqtt-gateway)
            clean_exit=(xiaozhi-esp32-server-db xiaozhi-esp32-server-redis)
            volume_mount=(redis xiaozhi-esp32-server-redis /data)
            backup_options=(--exclude /youtube-mcp)
            ;;
        hermes)
            containers=(hermes hermes-webui)
            sources=(hermes.pxar:/mnt/data/hermes)
            volume_mount=(hermes-source hermes /opt/hermes)
            ;;
        open-webui)
            containers=(open-webui)
            sources=(open-webui.pxar:/mnt/data/open-webui)
            ;;
        codex-proxy)
            containers=(codex-proxy)
            sources=(codex-proxy.pxar:/mnt/data/codex-openai-proxy)
            ;;
        cn-proxy)
            containers=(cn-proxy)
            sources=(cn-proxy.pxar:/etc/sing-box)
            ;;
        youtube-mcp)
            containers=(youtube-mcp-youtube-mcp-1)
            sources=(youtube-mcp.pxar:/mnt/data/xiaozhi/youtube-mcp)
            ;;
        qnetd-witness)
            containers=(qnetd-witness)
            sources=(qnetd.pxar:/mnt/data/qnetd)
            require_stopped=true
            ;;
    esac
    for container in "${containers[@]}"; do
        state="$(docker inspect --format '{{.State.Running}} {{.State.Paused}} {{.State.Restarting}}' "${container}")"
        case "${state}" in
            'true false false') running+=("${container}");;
            'false false false') ;;
            *) die "Container must be running or stopped, without pause/restart: ${container}";;
        esac
    done
    if [[ "${require_stopped}" == true ]] && (( ${#running[@]} )); then
        die 'qnetd-witness must already be stopped in a separately arranged quorum maintenance window; automatic stop is forbidden'
    fi
    if (( ${#volume_mount[@]} )); then
        volume_source="$(docker inspect --format "{{range .Mounts}}{{if and (eq .Type \"volume\") (eq .Destination \"${volume_mount[2]}\")}}{{.Source}}{{end}}{{end}}" "${volume_mount[1]}")"
        [[ "${volume_source}" == /* ]] || die "Missing volume: ${volume_mount[1]} ${volume_mount[2]}"
        sources+=("${volume_mount[0]}.pxar:${volume_source}")
    fi
    for source in "${sources[@]}"; do
        path="${source#*:}"
        [[ -d "${path}" && -r "${path}" && -x "${path}" ]] || die "Unavailable backup source: ${path}"
    done
    "${client_bin}" snapshot list --output-format json >/dev/null </dev/null
    metadata_dir="$(mktemp -d "${TMPDIR:-/tmp}/gateway-backup.${business}.XXXXXXXX")"
    docker inspect "${containers[@]}" >"${metadata_dir}/docker-inspect.json"
    docker inspect --format '{{.Image}}' "${containers[@]}" | xargs docker image inspect >"${metadata_dir}/docker-images.json"
    printf '%s\n' "${running[@]}" >"${metadata_dir}/running-containers.txt"

    printf 'Stopping %s for direct unencrypted backup; downtime includes the upload.\n' "${business}"
    stopping=1
    for ((i=${#running[@]}-1; i>=0; i--)); do
        docker stop --time "${stop_timeout}" "${running[i]}" >/dev/null
    done
    for container in "${containers[@]}"; do
        [[ "$(docker inspect --format '{{.State.Running}}' "${container}")" == false ]] || die "Container did not stop: ${container}"
    done
    for container in "${clean_exit[@]}"; do
        [[ "$(docker inspect --format '{{.State.ExitCode}} {{.State.OOMKilled}}' "${container}")" == '0 false' ]] || die "Database did not exit cleanly: ${container}"
    done
    trap 'cancel_backup INT 130' INT
    trap 'cancel_backup TERM 143' TERM
    (( cancel_code == 0 )) || exit "${cancel_code}"
    # Job control keeps SIGINT deliverable to this asynchronous native client.
    set -m
    "${client_bin}" backup "${sources[@]}" "metadata.pxar:${metadata_dir}" \
        --backup-type host --backup-id "gateway-${business}" --crypt-mode none \
        "${backup_options[@]}" </dev/null &
    backup_pid=$!
    set +m
    # Replay cancellation received between fork and PID registration.
    if [[ -n "${cancel_signal}" ]]; then cancel_backup "${cancel_signal}" "${cancel_code}"; fi
    wait "${backup_pid}" || backup_rc=$?
    if (( cancel_code )); then
        trap '' INT TERM
        # An interrupted wait does not imply that the client stopped reading data.
        wait "${backup_pid}" || true
    fi
    cleanup "$((cancel_code ? cancel_code : backup_rc))"
done
