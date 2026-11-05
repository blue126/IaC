# RemoteCC Infrastructure

Outward-facing RemoteCC VMs: employee workspaces, VM500 (HAPI control plane), the employee template and its bootstrap file, and remotecc-ops.

- HCP workspace: `iac-remotecc` (local execution).
- Driven by `wsctl` on the executor, not by Jenkins. The employee roster is runtime data on the executor (`oci-hub-workspaces.auto.tfvars.json`), not in Git.
- Internal homelab VMs stay in `../proxmox/`.
