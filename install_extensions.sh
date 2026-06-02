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
mkdir -p sources
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

# Fix permissions on the SQLite data directory so www-data can create lock files
echo ""
echo "Fixing permissions on /var/www/data..."
sudo docker compose exec mediawiki chown -R www-data:www-data /var/www/data
echo "✓ Permissions fixed"

# Create admin user account
echo ""
echo "Creating admin user account..."
sudo docker compose exec mediawiki php ./maintenance/run.php createAndPromote --bureaucrat --sysop --force admin adminpass123
echo "✓ Admin user created (username: admin, password: adminpass123)"

