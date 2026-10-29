#!/bin/bash
# Run only on the authorized CT110 after deployment; never print secret values.
set -euo pipefail
[[ "$(id -u)" -eq 0 ]]
for identity in iac-plan iac-deploy iac-apps; do
    [[ "$(id -u "$identity")" -gt 0 ]]
    if id -nG "$identity" | tr ' ' '\n' | grep -Eq '^(sudo|docker)$'; then exit 1; fi
    [[ "$(stat -c %a "/var/lib/jenkins-agent/$identity")" == 700 ]]
    [[ "$(systemctl show "jenkins-agent@$identity" --value -p NoNewPrivileges)" == yes ]]
    [[ "$(systemctl show "jenkins-agent@$identity" --value -p ProtectControlGroups)" == yes ]]
    [[ "$(systemctl show "jenkins-agent@$identity" --value -p MemoryMax)" == 268435456 ]]
    for other in iac-plan iac-deploy iac-apps; do
        [[ "$identity" != "$other" ]] || continue
        if runuser -u "$identity" -- test -r "/var/lib/jenkins-agent/$other"; then
            exit 1
        fi
    done
done
[[ ! -e /var/run/docker.sock ]]
[[ ! -e /var/lib/jenkins-agent-control/quarantine.json ]]
printf '%s\n' 'Account and remoting boundaries passed; task namespace/abort tests require actual admitted builds.'
