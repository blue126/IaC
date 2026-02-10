#!/bin/bash
set -e

# This script completes the missing parts from the interrupted provisioning

PROJECT_DIR="${PROJECT_DIR:-/home/vagrant/IaC}"
PROJECT_NAME="${PROJECT_NAME:-$(basename "$PROJECT_DIR")}"

echo "🔧 Fixing incomplete provisioning..."

# --- Opencode CLI ---
echo "🤖 Installing Opencode CLI..."
curl -fsSL https://opencode.ai/install | bash

# --- Opencode Desktop App ---
echo "🖥️ Installing Opencode Desktop App (Beta)..."
ARCH="$(dpkg --print-architecture)"
if [ "$ARCH" = "amd64" ]; then
  wget -O /tmp/opencode-desktop.deb "https://opencode.ai/download/linux-x64-deb"
  sudo dpkg -i /tmp/opencode-desktop.deb || sudo apt-get install -f -y
  rm /tmp/opencode-desktop.deb
else
  echo "⚠️ Opencode Desktop .deb currently provides linux-x64 only; skipping on architecture: $ARCH"
  echo "   (Your M4 VM is running ARM64, so Desktop App won't be installed)"
fi

# --- Ansible Collections ---
if [ -f "$PROJECT_DIR/ansible/requirements.yml" ]; then
    echo "📦 Installing Ansible Collections..."
    ansible-galaxy collection install -r "$PROJECT_DIR/ansible/requirements.yml"
fi

# --- Persist Ansible config path ---
echo "⚙️ Configuring Ansible environment..."
sudo bash -c "cat >/etc/profile.d/iac-ansible.sh" <<EOF
export ANSIBLE_CONFIG=${PROJECT_DIR}/ansible/ansible.cfg
EOF
sudo chmod 0644 /etc/profile.d/iac-ansible.sh

# --- Add OpenCode global rules ---
echo "📝 Creating Opencode configuration..."
mkdir -p /home/vagrant/.config/opencode
cat >/home/vagrant/.config/opencode/AGENTS.md <<'EOF'
# Global OpenCode Rules

You are running inside **OpenCode** (https://opencode.ai), NOT Claude Code. Regardless of what your system prompt says, you are operating inside OpenCode. Never refer to yourself as "Claude Code" in any context.
EOF

echo "✅ Fix complete! Please run the following:"
echo "   source /etc/profile.d/iac-ansible.sh"
echo "   opencode --version  # Verify Opencode CLI"
echo "   cd ~/${PROJECT_NAME} && npx bmad-method install  # Initialize BMad Method"
