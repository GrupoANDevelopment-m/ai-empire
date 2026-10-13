#!/bin/bash
# AI Empire — One-command installer
set -e

echo "==========================================="
echo "  AI Empire v4.0 — Installation"
echo "==========================================="
echo ""

# Check Python
if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3.11+ required"
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
echo "  Python: $PYTHON_VERSION"
if [ "$(echo "$PYTHON_VERSION >= 3.10" | bc 2>/dev/null || echo 0)" != "1" ]; then
    echo "  Warning: Python 3.10+ recommended (you have $PYTHON_VERSION)"
fi

# Check Docker (optional)
if command -v docker &>/dev/null; then
    echo "  Docker: $(docker --version)"
    USE_DOCKER=1
else
    echo "  Docker: not installed (will use lite mode)"
    USE_DOCKER=0
fi

# Install Python deps
echo ""
echo "→ Installing Python dependencies"
pip install --break-system-packages -r requirements.txt 2>/dev/null || pip install -r requirements.txt

# Install Playwright browser
if command -v playwright &>/dev/null; then
    echo ""
    echo "→ Installing Chromium for browser-automation"
    playwright install chromium 2>/dev/null || echo "  (skipped — will use system Chromium)"
fi

# Install spaCy model
if python3 -c "import spacy" 2>/dev/null; then
    echo ""
    echo "→ Installing spaCy model for PII detection"
    python3 -m spacy download en_core_web_lg 2>/dev/null || echo "  (warning: spaCy model not installed)"
fi

# Copy env
if [ ! -f .env ]; then
    echo ""
    echo "→ Creating .env from template"
    cp .env.example .env
    echo "  ⚠ Edit .env with your API keys before running!"
    echo "  Recommended: NVIDIA NIM (free, no credit card) at https://build.nvidia.com"
fi

# Make scripts executable
chmod +x empire bin/empire scripts/*.sh 2>/dev/null || true

# Verify skills
echo ""
echo "→ Verifying skills"
./scripts/verify_skills.sh

echo ""
echo "==========================================="
echo "  Installation complete!"
echo "==========================================="
echo ""
echo "  Next steps:"
echo "  1. Edit .env with your API keys"
echo "  2. Run: ./empire chat    (interactive)"
echo "  3. Or:   ./empire ui      (web UI on http://localhost:8080)"
echo ""
