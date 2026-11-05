#!/bin/bash
# Controller entry for the gateway batch backup: start it detached, report it, cancel it.
# Install as a Dropbear forced command so the controller key can do nothing else:
#   command="/mnt/data/gateway-backup/gateway-backup-ctl.sh",no-port-forwarding,no-agent-forwarding,no-X11-forwarding,no-pty ssh-ed25519 AAAA... ha-gateway-backup
set -eo pipefail
umask 077

backup_dir=/mnt/data/gateway-backup
backup_script="${backup_dir}/gateway-backup.sh"
runs_dir="${backup_dir}/runs"
# Must be the lock file used by gateway-backup.sh (its lock_dir plus gateway-backup.lock).
batch_lock=/var/lock/gateway-backup.lock
# Non-secret PBS settings. The token arrives on standard input with each start.
pbs_repository=''
pbs_fingerprint=''

die() { local code="$1"; shift; printf 'ERROR: %s\n' "$*" >&2; exit "${code}"; }
usage() { die 2 'Usage: gateway-backup-ctl.sh start|status|cancel <run_id> (start reads the PBS token from stdin)'; }
run_id_pattern='^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$'

if (( $# == 0 )) && [[ -n "${SSH_ORIGINAL_COMMAND+x}" ]]; then
    # Forced command: accept exactly "<verb> <run_id>", never shell syntax or internal verbs.
    ssh_pattern='^(start|status|cancel) ([A-Za-z0-9][A-Za-z0-9._-]{0,63})$'
    [[ "${SSH_ORIGINAL_COMMAND}" =~ ${ssh_pattern} ]] || usage
    set -- "${BASH_REMATCH[1]}" "${BASH_REMATCH[2]}"
fi
unset SSH_ORIGINAL_COMMAND
(( $# == 2 )) || usage
verb="$1"
run_id="$2"
[[ "${run_id}" =~ ${run_id_pattern} ]] || usage
run_dir="${runs_dir}/${run_id}"

# True when the PID recorded in $1 is alive and has $2 as one of its arguments (guards PID reuse).
proc_has_arg() {
    local pid arg args=()
    pid="$(cat "$1" 2>/dev/null)" || return 1
    [[ "${pid}" =~ ^[0-9]+$ && -r "/proc/${pid}/cmdline" ]] || return 1
    mapfile -d '' -t args 2>/dev/null <"/proc/${pid}/cmdline" || return 1
    for arg in "${args[@]}"; do [[ "${arg}" != "$2" ]] || return 0; done
    return 1
}
batch_alive() { proc_has_arg "${run_dir}/pid" "${backup_script}"; }
runner_alive() { proc_has_arg "${run_dir}/runner.pid" "${run_id}"; }

report() {
    local summary
    if [[ -f "${run_dir}/exit" ]]; then
        printf 'exit=%s\n' "$(cat "${run_dir}/exit")"
        summary="$(grep -E '^(ERROR: )?Batch (completed|finished|cancelled)' "${run_dir}/log" 2>/dev/null | tail -n 1)" || true
        [[ -n "${summary}" ]] || summary="$(grep -E '^ERROR: ' "${run_dir}/log" 2>/dev/null | tail -n 1)" || true
        [[ -z "${summary}" ]] || printf 'summary=%s\n' "${summary}"
    elif batch_alive || runner_alive; then
        printf 'running\n'
    elif [[ -d "${run_dir}" ]]; then
        printf 'unknown\nreason=no live process and no recorded exit\n'
    else
        printf 'unknown\nreason=no such run\n'
    fi
}

start() {
    local token="" attempt
    [[ -n "${pbs_repository}" ]] || die 1 'pbs_repository is not configured'
    [[ -r "${backup_script}" ]] || die 1 "Missing backup script: ${backup_script}"
    IFS= read -r token || true
    [[ -n "${token}" ]] || die 2 'Supply the PBS token on standard input'
    mkdir -p "${runs_dir}"
    # The run's processes inherit this lock and hold it until the last of them exits.
    exec 8>"${runs_dir}/.active.lock"
    flock -n 8 || die 3 'busy: an earlier controller run is still active'
    [[ ! -e "${run_dir}" ]] || die 3 "run_id already used: ${run_id}"
    # Also refuse while a manual invocation holds the backup script's own lock.
    exec 7>>"${batch_lock}"
    flock -n 7 || die 3 'busy: a gateway backup is already running'
    exec 7>&-
    mkdir "${run_dir}"
    export PBS_PASSWORD="${token}" PBS_REPOSITORY="${pbs_repository}"
    if [[ -n "${pbs_fingerprint}" ]]; then export PBS_FINGERPRINT="${pbs_fingerprint}"; fi
    # A new session with no inherited stdio keeps the run alive and lets SSH return now.
    setsid "${BASH}" "${BASH_SOURCE[0]}" _run "${run_id}" </dev/null >/dev/null 2>&1 &
    for attempt in 1 2 3 4 5 6; do
        [[ ! -s "${run_dir}/runner.pid" ]] || { printf 'started run_id=%s\n' "${run_id}"; return 0; }
        (( attempt == 6 )) || sleep 1
    done
    die 1 "Runner did not start for ${run_id}"
}

run() {
    local batch_pid rc=0
    [[ -d "${run_dir}" && ! -e "${run_dir}/runner.pid" ]] || die 1 "Not a fresh run: ${run_id}"
    printf '%s\n' "$$" >"${run_dir}/runner.pid"
    date +%s >"${run_dir}/started"
    "${BASH}" "${backup_script}" backup all </dev/null >"${run_dir}/log" 2>&1 &
    batch_pid=$!
    printf '%s\n' "${batch_pid}" >"${run_dir}/pid"
    wait "${batch_pid}" || rc=$?
    date +%s >"${run_dir}/finished"
    printf '%s\n' "${rc}" >"${run_dir}/exit.tmp"
    mv "${run_dir}/exit.tmp" "${run_dir}/exit"
}

cancel() {
    # The batch PID is written right after launch; allow that moment to pass.
    if [[ ! -f "${run_dir}/exit" ]] && ! batch_alive && runner_alive; then sleep 1; fi
    if [[ ! -f "${run_dir}/exit" ]] && batch_alive; then
        # The batch forwards TERM to the current business, which restores its containers.
        kill -TERM "$(cat "${run_dir}/pid")"
        printf 'cancelling\n'
        return 0
    fi
    report
}

case "${verb}" in
    start) start;;
    status) report;;
    cancel) cancel;;
    _run) run;;
    *) usage;;
esac
