#!/bin/bash
# Smart Money System - Setup Script

echo "=========================================="
echo "Smart Money System - Setup"
echo "=========================================="

# Check Python version
echo ""
echo "Checking Python..."
python3 --version

# Create directories
echo ""
echo "Creating directories..."
mkdir -p data/candles
mkdir -p data/signals
mkdir -p logs

# Install dependencies
echo ""
echo "Installing dependencies..."
pip3 install -r requirements.txt

# Test database
echo ""
echo "Testing database..."
python3 main.py test-db

echo ""
echo "=========================================="
echo "Setup complete!"
echo "=========================================="
echo ""
echo "Next steps:"
echo "  1. Edit config/settings.py with your API keys"
echo "  2. Run: python3 main.py test"
echo "  3. Run: python3 main.py start"
