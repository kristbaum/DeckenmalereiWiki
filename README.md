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

3. **Create the Infobox template in MediaWiki:**

   Before importing articles, you need to create the infobox template:

   - Navigate to <http://localhost:8080/index.php?title=Template:Infobox_Deckenmalerei&action=edit>
   - Copy the content from [Infobox_Deckenmalerei.wiki](Infobox_Deckenmalerei.wiki)
   - Save the page

   This template will display structured metadata for each article including title, images, descriptions, and related persons (authors, painters, architects, commissioners).

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
├── docker-compose.yml             # MediaWiki + SQLite setup
├── LocalSettings.php              # MediaWiki configuration
├── parser.py                      # Core JSON parser and article generator
├── importer.py                    # MediaWiki API integration
├── requirements.txt               # Python dependencies
├── Infobox_Deckenmalerei.wiki    # MediaWiki infobox template
├── sources/                       # Source JSON files
│   ├── entities.json
│   ├── relations.json
│   └── resources.json
├── output/                        # Generated .wiki files (created by parser.py)
└── downloads/                     # Downloaded images (created by importer.py)
```

## MediaWiki Template

The [Infobox_Deckenmalerei.wiki](Infobox_Deckenmalerei.wiki) template displays structured information at the top of each article:

- **titel** - Article title
- **beschreibung** - Short description
- **bild** - Main image filename
- **lizenz** - Image license information
- **author** - Text author(s)
- **painter** - Ceiling painting artist(s)
- **architect** - Building architect(s)
- **commissioner** - Patron/commissioner(s)

All parameters are optional. The template must be created in MediaWiki before importing articles.

## Notes

- Uses SQLite database for simpler setup (no separate database container)
- By default, only 10 articles are imported for faster testing (configurable with `max_articles` parameter)
- Image processing is disabled by default (enable with `enable_images=True`)
- Images are named as `Deckenmalerei_{entity_id}.jpg`
- Articles can be re-imported/overwritten by running `importer.py` again
- Large JSON files are loaded into memory - ensure sufficient RAM
