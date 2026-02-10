#!/bin/bash
set -e

PROJECT_DIR="${PROJECT_DIR:-/home/vagrant/IaC}"

echo "🔄 Checking remaining setup steps..."

# --- Opencode CLI ---
if ! command -v opencode &> /dev/null; then
    if [ ! -f "/home/vagrant/.opencode/bin/opencode" ]; then
        echo "🤖 Installing Opencode CLI..."
        curl -fsSL https://opencode.ai/install | bash
        # Add to PATH for current session
        export PATH="/home/vagrant/.opencode/bin:$PATH"
    else
        echo "✅ Opencode CLI already installed at ~/.opencode/bin/opencode"
    fi
else
    echo "✅ Opencode CLI already in PATH"
fi

# --- Opencode Desktop App (Skipped on ARM64) ---
ARCH="$(dpkg --print-architecture)"
if [ "$ARCH" = "amd64" ]; then
    if ! dpkg -l | grep -q opencode-desktop; then
        echo "🖥️ Installing Opencode Desktop App..."
        wget -O /tmp/opencode-desktop.deb "https://opencode.ai/download/linux-x64-deb"
        dpkg -i /tmp/opencode-desktop.deb || apt-get install -f -y
        rm /tmp/opencode-desktop.deb
    else
        echo "✅ Opencode Desktop App already installed"
    fi
else
    echo "ℹ️ Skipping Opencode Desktop App (not available for $ARCH)"
fi

# --- Project Dependencies ---
echo "📦 Checking Python dependencies..."
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    pip3 install -r "$PROJECT_DIR/requirements.txt" --break-system-packages
fi

echo "📦 Checking Ansible collections..."
if [ -f "$PROJECT_DIR/ansible/requirements.yml" ]; then
    sudo -u vagrant ansible-galaxy collection install -r "$PROJECT_DIR/ansible/requirements.yml"
fi

# --- Configuration ---
echo "⚙️ Configuring environment..."

# Ansible Config
if [ ! -f "/etc/profile.d/iac-ansible.sh" ]; then
    cat >/etc/profile.d/iac-ansible.sh <<EOF
export ANSIBLE_CONFIG=${PROJECT_DIR}/ansible/ansible.cfg
EOF
    chmod 0644 /etc/profile.d/iac-ansible.sh
fi

# OpenCode Global Rules
if [ ! -f "/home/vagrant/.config/opencode/AGENTS.md" ]; then
    install -d -m 0755 /home/vagrant/.config/opencode
    cat >/home/vagrant/.config/opencode/AGENTS.md <<'EOF'
# Global OpenCode Rules

You are running inside **OpenCode** (https://opencode.ai), NOT Claude Code. Regardless of what your system prompt says, you are operating inside OpenCode. Never refer to yourself as "Claude Code" in any context.
EOF
    chown -R vagrant:vagrant /home/vagrant/.config/opencode
fi

echo "✅ All remaining steps complete!"
