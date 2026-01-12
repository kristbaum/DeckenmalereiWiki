#!/bin/bash
# Install MediaWiki extensions

set -e

EXTENSIONS_DIR="extensions"
mkdir -p "$EXTENSIONS_DIR"

# Install Purge extension
echo "Installing Purge extension..."
if [ ! -d "$EXTENSIONS_DIR/Purge" ]; then
    git clone https://github.com/AlPha5130/mediawiki-extensions-Purge.git "$EXTENSIONS_DIR/Purge"
    echo "✓ Purge extension installed"
else
    echo "✓ Purge extension already installed"
fi

echo ""
echo "Extensions installed successfully!"
echo "Restart MediaWiki with: sudo docker compose restart"
