Read `/Users/weierfu/Projects/IaC/_bmad/render/bmad-build/iac-06fe9f42bb8b/12f44ee27943d87fc07d/review-prompts/verification-gap.md` completely and follow it as your review instructions.

Review content:

diff --git a/ansible/roles/tailscale/tasks/main.yml b/ansible/roles/tailscale/tasks/main.yml
index 5bf5df6..d586ff3 100644
--- a/ansible/roles/tailscale/tasks/main.yml
+++ b/ansible/roles/tailscale/tasks/main.yml
@@ -1,40 +1,123 @@
 ---
-- name: Configure /dev/net/tun passthrough for LXC (on Proxmox Host)
+- name: Read LXC configuration for TUN cleanup
   delegate_to: "{{ proxmox_node | default(inventory_hostname) }}"
-  blockinfile:
+  slurp:
+    src: "/etc/pve/lxc/{{ proxmox_vmid }}.conf"
+  register: lxc_config
+  when:
+    - ansible_facts.virtualization_type == 'lxc'
+    - proxmox_vmid is defined
+    - proxmox_node is defined
+
+- name: Remove legacy Tailscale block markers from LXC configuration
+  delegate_to: "{{ proxmox_node | default(inventory_hostname) }}"
+  lineinfile:
     path: "/etc/pve/lxc/{{ proxmox_vmid }}.conf"
-    marker: "# {mark} ANSIBLE MANAGED BLOCK - TAILSCALE"
-    block: |
-      lxc.cgroup2.devices.allow: c 10:200 rwm
-      lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file
+    regexp: '^# (BEGIN|END) ANSIBLE MANAGED BLOCK - TAILSCALE$'
+    state: absent
+  register: lxc_marker_cleanup
+  when:
+    - ansible_facts.virtualization_type == 'lxc'
+    - proxmox_vmid is defined
+    - proxmox_node is defined
+
+- name: Remove duplicate TUN device permissions from LXC configuration
+  delegate_to: "{{ proxmox_node | default(inventory_hostname) }}"
+  lineinfile:
+    path: "/etc/pve/lxc/{{ proxmox_vmid }}.conf"
+    regexp: '^lxc\.cgroup2\.devices\.allow: c 10:200 rwm$'
+    state: absent
+  register: lxc_tun_device_cleanup
+  when:
+    - ansible_facts.virtualization_type == 'lxc'
+    - proxmox_vmid is defined
+    - proxmox_node is defined
+    - >-
+      ((lxc_config.content | b64decode).splitlines()
+      | select('equalto', 'lxc.cgroup2.devices.allow: c 10:200 rwm')
+      | list | length) > 1
+
+- name: Ensure TUN device permission in LXC configuration
+  delegate_to: "{{ proxmox_node | default(inventory_hostname) }}"
+  lineinfile:
+    path: "/etc/pve/lxc/{{ proxmox_vmid }}.conf"
+    regexp: '^lxc\.cgroup2\.devices\.allow: c 10:200 rwm$'
+    line: 'lxc.cgroup2.devices.allow: c 10:200 rwm'
+  register: lxc_tun_device_config
+  when:
+    - ansible_facts.virtualization_type == 'lxc'
+    - proxmox_vmid is defined
+    - proxmox_node is defined
+
+- name: Remove duplicate TUN mount entries from LXC configuration
+  delegate_to: "{{ proxmox_node | default(inventory_hostname) }}"
+  lineinfile:
+    path: "/etc/pve/lxc/{{ proxmox_vmid }}.conf"
+    regexp: '^lxc\.mount\.entry: /dev/net/tun dev/net/tun none bind,create=file$'
+    state: absent
+  register: lxc_tun_mount_cleanup
+  when:
+    - ansible_facts.virtualization_type == 'lxc'
+    - proxmox_vmid is defined
+    - proxmox_node is defined
+    - >-
+      ((lxc_config.content | b64decode).splitlines()
+      | select('equalto', 'lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file')
+      | list | length) > 1
+
+- name: Ensure TUN mount entry in LXC configuration
+  delegate_to: "{{ proxmox_node | default(inventory_hostname) }}"
+  lineinfile:
+    path: "/etc/pve/lxc/{{ proxmox_vmid }}.conf"
+    regexp: '^lxc\.mount\.entry: /dev/net/tun dev/net/tun none bind,create=file$'
+    line: 'lxc.mount.entry: /dev/net/tun dev/net/tun none bind,create=file'
+  register: lxc_tun_mount_config
+  when:
+    - ansible_facts.virtualization_type == 'lxc'
+    - proxmox_vmid is defined
+    - proxmox_node is defined
+
+- name: Track LXC TUN configuration changes
+  set_fact:
+    lxc_config_changed: >-
+      {{
+        (lxc_marker_cleanup.changed | default(false))
+        or (lxc_tun_device_cleanup.changed | default(false))
+        or (lxc_tun_device_config.changed | default(false))
+        or (lxc_tun_mount_cleanup.changed | default(false))
+        or (lxc_tun_mount_config.changed | default(false))
+      }}
   when:
     - ansible_facts.virtualization_type == 'lxc'
     - proxmox_vmid is defined
     - proxmox_node is defined
-  register: lxc_config_update
 
 - name: Prevent Proxmox from overwriting resolv.conf (LXC only)
   file:
     path: /etc/.pve-ignore.resolv.conf
     state: touch
+    access_time: preserve
+    modification_time: preserve
   when: ansible_facts.virtualization_type == 'lxc'
 
 - name: Ensure valid DNS resolver (LXC only)
   copy:
     dest: /etc/resolv.conf
     content: "nameserver {{ tailscale_dns_server }}"
-  when: ansible_facts.virtualization_type == 'lxc'
+  when:
+    - ansible_facts.virtualization_type == 'lxc'
+    - not (tailscale_accept_dns | bool)
 
 - name: Restart LXC container to apply changes
   delegate_to: "{{ proxmox_node | default(inventory_hostname) }}"
   command: "pct reboot {{ proxmox_vmid }}"
-  when: lxc_config_update.changed
+  when: lxc_config_changed | default(false) | bool
 
 - name: Wait for container to come back up
   wait_for_connection:
     delay: 10
     timeout: 60
-  when: lxc_config_update.changed
+  when: lxc_config_changed | default(false) | bool
 
 - name: Check if Tailscale is installed
   shell: command -v tailscale
@@ -57,7 +140,8 @@
     value: '1'
     sysctl_set: yes
     state: present
-    reload: yes
+    # LXC guests cannot reload host-only parameters such as kernel.printk.
+    reload: "{{ ansible_facts.virtualization_type != 'lxc' }}"
 
 - name: Check for /dev/net/tun
   stat:
@@ -111,5 +195,3 @@
 - name: Display Tailscale Info
   debug:
     msg: "Device: {{ inventory_hostname }} | Tailscale IP: {{ tailscale_ip.stdout }}"
-
-
diff --git a/ansible/inventory/host_vars/n8n.yml b/ansible/inventory/host_vars/n8n.yml
new file mode 100644
index 0000000..1d3c783
--- /dev/null
+++ b/ansible/inventory/host_vars/n8n.yml
@@ -0,0 +1,2 @@
+proxmox_node: pve0
+proxmox_vmid: 106

Do not invoke any skill. If the instruction file is unreadable, report that exact failure and stop. Return only the review result.
