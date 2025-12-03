# Ansible Abstraction Levels: Module vs. Role vs. Task

This note summarizes our discussion on how to refactor and abstract functionality in Ansible, specifically in the context of `tailscale serve`.

## 1. Custom Module (`library/`)
*   **What it is**: A Python script (e.g., `tailscale_serve.py`) that extends Ansible's core functionality.
*   **Location**: `library/` (project root) or `roles/<role_name>/library/`.
*   **Pros**:
    *   **Idempotency**: Can handle complex logic and state management (changed/unchanged) natively in Python.
    *   **Cleanliness**: Playbooks look very clean (`tailscale_serve: target=... state=present`).
*   **Cons**:
    *   **Complexity**: Requires writing Python code.
    *   **Overkill**: Often unnecessary if the task can be done with existing modules (`command`, `shell`, `template`).

## 2. Separate Role (`roles/tailscale_serve`)
*   **What it is**: A standalone Role dedicated to a specific function.
*   **Location**: `roles/tailscale_serve/`.
*   **Pros**:
    *   **Decoupling**: Completely separates "installing Tailscale" from "configuring Serve".
    *   **Reusability**: Can be pulled into any playbook independently.
*   **Cons**:
    *   **Fragmentation**: Related files are scattered across multiple roles (`tailscale` vs `tailscale_serve`).

## 3. Dedicated Task File (`tasks_from`)
*   **What it is**: A separate YAML file (e.g., `serve.yml`) within an existing Role.
*   **Location**: `roles/tailscale/tasks/serve.yml`.
*   **Usage**:
    ```yaml
    - include_role:
        name: tailscale
        tasks_from: serve
      vars:
        tailscale_serve_target: "..."
    ```
*   **Pros**:
    *   **Cohesion**: All Tailscale-related logic stays in one folder (`roles/tailscale/`).
    *   **Modularity**: Logic is separated from the main installation flow (`main.yml`).
    *   **Simplicity**: Uses standard YAML/Ansible syntax, no Python required.
*   **Decision**: We chose this approach for `tailscale serve` because it balances organization (keeping files together) with modularity (separating logic).
