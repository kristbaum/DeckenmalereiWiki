# DeckenmalereiWiki

Parsed version of Deckenmalerei.eu texts for MediaWiki.

## Setup

1. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

2. **Start MediaWiki (optional for local testing):**

   ```bash
   docker-compose up -d
   ```

   Access MediaWiki at: <http://localhost:8080>

   Default admin credentials:
   - Username: `admin`
   - Password: `adminpass123`

## Usage

### Generate Articles Only

Parse the JSON files and save articles as `.wiki` files:

```bash
python parser.py
```

This creates an `output/` directory with all generated MediaWiki articles.

### Import to MediaWiki

Parse data and automatically import articles with images to MediaWiki:

```bash
python importer.py
```

This will:

1. Load and parse JSON data from `sources/`
2. Download images from external URLs
3. Upload images to MediaWiki
4. Create/update articles in MediaWiki

## Architecture

### Data Structure

The parser processes three JSON files:

- **entities.json** - Contains TEXT, TEXT_PART, and OBJECT_PAINTING entities
- **relations.json** - Defines relationships between entities (PART, LEAD_RESOURCE, AUTHORS, etc.)
- **resources.json** - Contains image URLs and license information

### Key Features

1. **Article Assembly** - Follows PART relations to combine TEXT_PART entities in order
2. **HTML-to-MediaWiki Conversion** - Converts HTML markup to MediaWiki syntax
3. **Infobox Generation** - Extracts metadata for structured display
4. **Image Management** - Downloads and uploads images with license info
5. **API Integration** - Creates/updates pages programmatically for easy testing

### Example Workflow

```python
from parser import DeckenmalereiParser
from importer import MediaWikiImporter

# Parse data
parser = DeckenmalereiParser()
parser.load_data()

# Generate articles
articles = parser.generate_all_articles()

# Import to MediaWiki
importer = MediaWikiImporter(host="localhost", port=8080)
if importer.login():
    importer.import_articles(articles)
```

## Configuration

Edit [docker-compose.yml](docker-compose.yml) to customize:

- Database credentials
- MediaWiki port (default: 8080)
- Admin credentials
- Site language (default: German)

Edit [importer.py](importer.py) to change:

- MediaWiki connection settings
- Download directory
- Upload behavior

## Development

The project structure:

```txt
DeckenmalereiWiki/
├── docker-compose.yml    # MediaWiki + MariaDB setup
├── parser.py             # Core JSON parser and article generator
├── importer.py           # MediaWiki API integration
├── requirements.txt      # Python dependencies
├── sources/              # Source JSON files
│   ├── entities.json
│   ├── relations.json
│   └── resources.json
├── output/               # Generated .wiki files (created by parser.py)
└── downloads/            # Downloaded images (created by importer.py)
```

## Notes

- The infobox template `{{Infobox Deckenmalerei}}` needs to be created in MediaWiki
- Images are named as `Deckenmalerei_{entity_id}.jpg`
- Articles can be re-imported/overwritten by running `importer.py` again
- Large JSON files are loaded into memory - ensure sufficient RAM
