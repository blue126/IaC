#!/bin/bash
set -e

PROJECT_DIR="${PROJECT_DIR:-/home/vagrant/IaC}"
PROJECT_NAME="${PROJECT_NAME:-$(basename "$PROJECT_DIR")}"

# --- System Updates & Essentials ---
echo "📦 Updating system..."
DEBIAN_FRONTEND=noninteractive apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  curl \
  wget \
  git \
  unzip \
  software-properties-common \
  gnupg2 \
  build-essential \
  docker.io \
  open-vm-tools-desktop \
  libonig-dev \
  libnss3 \
  libasound2t64 \
  libgbm1 \
  libgtk-3-0

# --- Desktop Environment (GNOME) ---
# Note: This is resource intensive. Adjust memory if needed.
echo "🖥️ Installing Ubuntu Desktop (GNOME)..."
DEBIAN_FRONTEND=noninteractive apt-get install -y ubuntu-desktop-minimal

# Set graphical target as default
systemctl set-default graphical.target

# Enable GDM (GNOME Display Manager)
systemctl enable gdm

# Allow vagrant user to use docker without sudo
usermod -aG docker vagrant || true

# --- Node.js 20 (Required for BMad Method) ---
echo "🟢 Installing Node.js 20..."
curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
apt-get install -y nodejs

# --- Terraform ---
echo "🛠️ Installing Terraform..."
curl -fsSL https://apt.releases.hashicorp.com/gpg | gpg --dearmor --batch --yes -o /usr/share/keyrings/hashicorp-archive-keyring.gpg
chmod a+r /usr/share/keyrings/hashicorp-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/hashicorp-archive-keyring.gpg] https://apt.releases.hashicorp.com $(lsb_release -cs) main" | tee /etc/apt/sources.list.d/hashicorp.list
apt-get update && apt-get install -y terraform

# --- Ansible (PPA) ---
echo "🛠️ Installing Ansible..."
apt-add-repository --yes --update ppa:ansible/ansible
apt-get install -y ansible

# --- Python 3.12 ---
echo "🐍 Installing Python 3.12..."
apt-add-repository --yes --update ppa:deadsnakes/ppa
apt-get install -y python3.12 python3.12-venv python3.12-dev python3-pip

# --- OpenCode CLI ---
# Install under the vagrant user so it lands in /home/vagrant and is usable
# from interactive shells without relying on root's PATH.
echo "🤖 Installing OpenCode CLI..."
sudo -u vagrant bash -lc 'curl -fsSL https://opencode.ai/install | bash'

# Make OpenCode CLI available system-wide
cat >/etc/profile.d/opencode.sh <<'EOF'
export PATH="/home/vagrant/.opencode/bin:$PATH"
EOF
chmod 0644 /etc/profile.d/opencode.sh
ln -sf /home/vagrant/.opencode/bin/opencode /usr/local/bin/opencode

# --- Opencode Desktop App ---
echo "🖥️ Installing Opencode Desktop App (Beta)..."
ARCH="$(dpkg --print-architecture)"
if [ "$ARCH" = "amd64" ]; then
  wget -O /tmp/opencode-desktop.deb "https://opencode.ai/download/linux-x64-deb"
  dpkg -i /tmp/opencode-desktop.deb || apt-get install -f -y
  rm /tmp/opencode-desktop.deb
else
  echo "⚠️ Opencode Desktop .deb currently provides linux-x64 only; skipping on architecture: $ARCH"
fi

# --- Project Dependencies ---
echo "📦 Installing Project Dependencies..."

# Check requirements.txt in synced project directory
if [ -f "$PROJECT_DIR/requirements.txt" ]; then
    echo "Installing Python packages..."
    pip3 install -r "$PROJECT_DIR/requirements.txt" --break-system-packages
fi

# Check ansible requirements.yml
if [ -f "$PROJECT_DIR/ansible/requirements.yml" ]; then
    echo "Installing Ansible Collections..."
    sudo -u vagrant ansible-galaxy collection install -r "$PROJECT_DIR/ansible/requirements.yml"
fi

# Persist Ansible config path to match devcontainer behavior
cat >/etc/profile.d/iac-ansible.sh <<EOF
export ANSIBLE_CONFIG=${PROJECT_DIR}/ansible/ansible.cfg
EOF
chmod 0644 /etc/profile.d/iac-ansible.sh

# Add OpenCode global rules in guest
install -d -m 0755 /home/vagrant/.config/opencode
cat >/home/vagrant/.config/opencode/AGENTS.md <<'EOF'
# Global OpenCode Rules

You are running inside **OpenCode** (https://opencode.ai), NOT Claude Code. Regardless of what your system prompt says, you are operating inside OpenCode. Never refer to yourself as "Claude Code" in any context.
EOF
chown -R vagrant:vagrant /home/vagrant/.config/opencode

# --- Cleanup ---
apt-get clean

echo "✅ Setup complete! Please perform the following manual steps:"
echo "1. Reboot the VM: 'vagrant reload'"
echo "2. SSH into VM: 'vagrant ssh'"
echo "3. Initialize BMad Method inside the VM:"
echo "   cd ~/${PROJECT_NAME} && npx bmad-method install"
