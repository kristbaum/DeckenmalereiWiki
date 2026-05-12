#!/bin/bash
# Install MediaWiki extensions

set -e

EXTENSIONS_DIR="extensions"
sudo mkdir -p "$EXTENSIONS_DIR"

# Install Purge extension
echo "Installing Purge extension..."
if [ ! -d "$EXTENSIONS_DIR/Purge" ]; then
    sudo git clone https://github.com/AlPha5130/mediawiki-extensions-Purge.git "$EXTENSIONS_DIR/Purge"
    echo "✓ Purge extension installed"
else
    echo "✓ Purge extension already installed"
fi

# Download source data files
echo ""
echo "Downloading source data files..."
sudo mkdir -p sources
BASE_URL="https://raw.githubusercontent.com/arthist-lmu/plafond3d/main/dumps/deckenmalerei.eu/2025_02"
curl -fsSL "$BASE_URL/entities.json"  -o sources/entities.json
curl -fsSL "$BASE_URL/relations.json" -o sources/relations.json
curl -fsSL "$BASE_URL/resources.json" -o sources/resources.json
echo "✓ Source data downloaded"

echo ""
echo "Extensions installed successfully!"
echo "Restart MediaWiki with: sudo docker compose restart"

# Setup the database using installPreConfigured.php (MediaWiki 1.44+)
echo ""
echo "Setting up database with installPreConfigured.php..."
sudo docker compose exec mediawiki php ./maintenance/run.php installPreConfigured
echo "✓ Database setup complete"

