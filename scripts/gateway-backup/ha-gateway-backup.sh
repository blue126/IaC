#!/bin/sh
# Home Assistant side of the gateway batch backup, called through shell_command:
#   shell_command:
#     gateway_backup: "/config/scripts/ha-gateway-backup.sh {{ action }} {{ run_id }}"
# A templated shell_command runs without a shell, so the token redirection lives here.
set -eu

gateway=root@192.168.1.1
key=/config/.ssh/gateway_backup_ed25519
known_hosts=/config/.ssh/gateway_backup_known_hosts
token_file=/config/.secrets/gateway_backup_pbs_token

usage() { echo 'Usage: ha-gateway-backup.sh start|status|cancel <run_id>' >&2; exit 2; }
[ "$#" -eq 2 ] || usage
action="$1"
run_id="$2"
case "${action}" in start|status|cancel) ;; *) usage;; esac
case "${run_id}" in ''|[!A-Za-z0-9]*|*[!A-Za-z0-9._-]*) usage;; esac
[ "${#run_id}" -le 64 ] || usage

# The gateway key is a forced command; it only ever receives "<action> <run_id>".
set -- -i "${key}" -o IdentitiesOnly=yes -o BatchMode=yes -o ConnectTimeout=10 \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile="${known_hosts}" "${gateway}" "${action}" "${run_id}"
if [ "${action}" = start ]; then
    [ -r "${token_file}" ] || { echo "Missing PBS token file: ${token_file}" >&2; exit 1; }
    # The token travels on stdin only: never in arguments, environment or logs.
    exec ssh "$@" <"${token_file}"
fi
exec ssh "$@" </dev/null
