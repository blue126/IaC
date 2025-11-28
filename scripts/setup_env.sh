#!/bin/bash
set -e

# Get the project root directory
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv"

echo "Setting up environment in $PROJECT_ROOT"

# Create virtual environment if it doesn't exist
if [ ! -d "$VENV_DIR" ]; then
    echo "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    echo "Virtual environment already exists."
fi

# Activate virtual environment
source "$VENV_DIR/bin/activate"

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip

# Install dependencies
if [ -f "$PROJECT_ROOT/requirements.txt" ]; then
    echo "Installing dependencies from requirements.txt..."
    pip install -r "$PROJECT_ROOT/requirements.txt"
else
    echo "Warning: requirements.txt not found!"
fi

# Install Ansible Galaxy collections if requirements.yml exists
if [ -f "$PROJECT_ROOT/ansible/requirements.yml" ]; then
    echo "Installing Ansible Galaxy collections..."
    ansible-galaxy install -r "$PROJECT_ROOT/ansible/requirements.yml"
fi

echo "Environment setup complete."
echo "To activate the environment, run: source .venv/bin/activate"
