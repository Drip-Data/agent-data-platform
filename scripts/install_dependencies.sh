#!/bin/bash
#
# Agent Data Platform - Universal Dependency Installer
#
# This script automates the setup of the required environment by:
# 1. Detecting the Linux distribution's package manager (apt, dnf, or yum).
# 2. Installing system-level dependencies like Redis.
# 3. Creating a Python virtual environment (`venv`) if it doesn't exist.
# 4. Installing all required Python packages from `requirements.txt`.
# 5. Installing the necessary browser binaries for Playwright (used by browser_use_server).
#

# Exit immediately if a command exits with a non-zero status.
set -e

echo "🚀 Starting Agent Data Platform dependency installation..."

# --- Step 1: Install System-level Dependencies ---
echo "🔍 Detecting package manager and installing Redis..."

if command -v apt-get &> /dev/null; then
    echo "📦 Found apt-get (Debian/Ubuntu-based system)."
    sudo apt-get update
    sudo apt-get install -y redis-server
elif command -v dnf &> /dev/null; then
    echo "📦 Found dnf (Fedora/RHEL-based system)."
    sudo dnf install -y redis
elif command -v yum &> /dev/null; then
    echo "📦 Found yum (CentOS-based system)."
    sudo yum install -y redis
else
    echo "❌ Unsupported package manager. Please install Redis manually and then re-run this script."
    exit 1
fi

echo "✅ Redis server installed successfully."
echo "💡 You can manage the Redis service with 'sudo systemctl start/stop/status redis-server' (or 'redis' on some systems)."


# --- Step 2: Set up Python Virtual Environment and Pip Dependencies ---
echo "🐍 Setting up Python virtual environment..."

if [ ! -d "venv" ]; then
    echo "   - Virtual environment 'venv' not found. Creating it now..."
    python3 -m venv venv
    echo "   - Virtual environment created."
else
    echo "   - Virtual environment 'venv' already exists."
fi

echo "📦 Installing Python packages from requirements.txt..."
venv/bin/pip install -r requirements.txt

echo "✅ Python packages installed successfully."


# --- Step 3: Install Browser Binaries for Playwright ---
echo "🌐 Installing browser binaries for Playwright (for browser_use_server)..."
venv/bin/playwright install

echo "✅ Playwright browsers installed successfully."


echo "🎉 All dependencies have been installed successfully!"
echo "➡️ Next steps:"
echo "   1. Start the Redis server: sudo systemctl start redis-server"
echo "   2. Run the application: venv/bin/python3 main.py"
