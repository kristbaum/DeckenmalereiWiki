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

# Download source data files (skip any that already exist)
echo ""
echo "Downloading source data files..."
mkdir -p sources
BASE_URL="https://raw.githubusercontent.com/arthist-lmu/plafond3d/main/dumps/deckenmalerei.eu/2026_04"
for f in entities.json relations.json resources.json; do
    if [ -f "sources/$f" ]; then
        echo "  sources/$f already exists, skipping"
    else
        curl -fsSL "$BASE_URL/$f" -o "sources/$f"
        echo "  Downloaded sources/$f"
    fi
done
echo "✓ Source data ready"

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
