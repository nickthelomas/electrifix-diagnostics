#!/bin/bash
#
# ElectriFix Diagnostics - Transfer to Laptop Script
# Run this on the k8 server to package for laptop deployment
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
OUTPUT_DIR="${HOME}/electrifix-diagnostics-package"
ARCHIVE_NAME="electrifix-diagnostics-$(date +%Y%m%d).tar.gz"

echo "========================================"
echo "  ElectriFix Diagnostics Packager"
echo "========================================"
echo

# Create output directory
rm -rf "$OUTPUT_DIR"
mkdir -p "$OUTPUT_DIR"

# Copy application files
echo "Copying application files..."
cp -r "$SCRIPT_DIR/backend" "$OUTPUT_DIR/"
cp -r "$SCRIPT_DIR/frontend" "$OUTPUT_DIR/"
mkdir -p "$OUTPUT_DIR/data/baselines"
mkdir -p "$OUTPUT_DIR/data/captures"
cp "$SCRIPT_DIR/run.py" "$OUTPUT_DIR/"
cp "$SCRIPT_DIR/requirements.txt" "$OUTPUT_DIR/"
cp "$SCRIPT_DIR/README.md" "$OUTPUT_DIR/"
cp "$SCRIPT_DIR/.env.example" "$OUTPUT_DIR/"

# Copy database with existing models (but clear diagnoses)
if [ -f "$SCRIPT_DIR/data/electrifix_diag.db" ]; then
    cp "$SCRIPT_DIR/data/electrifix_diag.db" "$OUTPUT_DIR/data/"
fi

# Create setup script for laptop
cat > "$OUTPUT_DIR/setup.sh" << 'SETUP'
#!/bin/bash
# ElectriFix Diagnostics - Laptop Setup Script

echo "Setting up ElectriFix Diagnostics..."
echo

# Check Python version
python3 --version > /dev/null 2>&1 || { echo "Python 3 is required. Please install it first."; exit 1; }

# Create virtual environment
echo "Creating virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Add user to dialout group for serial access
if ! groups | grep -q dialout; then
    echo
    echo "NOTE: Adding user to 'dialout' group for serial port access."
    echo "You may need to log out and back in for this to take effect."
    sudo usermod -a -G dialout $USER
fi

echo
echo "========================================"
echo "  Setup complete!"
echo "========================================"
echo
echo "To start ElectriFix Diagnostics:"
echo "  1. source venv/bin/activate"
echo "  2. python run.py"
echo "  3. Open http://localhost:3003 in your browser"
echo
SETUP

chmod +x "$OUTPUT_DIR/setup.sh"

# Create archive
echo "Creating archive..."
cd "${HOME}"
tar -czf "$ARCHIVE_NAME" -C "$OUTPUT_DIR" .

echo
echo "========================================"
echo "  Package created successfully!"
echo "========================================"
echo
echo "Package location: ${HOME}/${ARCHIVE_NAME}"
echo "Package size: $(du -h "${HOME}/${ARCHIVE_NAME}" | cut -f1)"
echo
echo "To transfer to laptop:"
echo "  scp ${HOME}/${ARCHIVE_NAME} user@laptop:~/"
echo
echo "On laptop:"
echo "  mkdir electrifix-diagnostics"
echo "  cd electrifix-diagnostics"
echo "  tar -xzf ~/${ARCHIVE_NAME}"
echo "  ./setup.sh"
echo
