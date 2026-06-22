# DeckenmalereiWiki

Parsed version of Deckenmalerei.eu texts for MediaWiki.

## Setup

1. **Install the package:**

   ```bash
   uv sync
   ```

2. **Start MediaWiki (optional for local testing):**

   ```bash
   install_extenstions.sh
   docker-compose up -d
   ```

   Access MediaWiki at: <http://localhost:8080>

   Default admin credentials:
   - Username: `admin`
   - Password: `adminpass123`

3. **Templates**

   The MediaWiki templates live as `.wiki` files in [templates/](templates/) and are
   uploaded/updated automatically by the `import` command — no manual setup needed.
   Each file is published to `Template:<title>`, where the title is the filename stem
   with underscores turned into spaces (e.g. `Infobox_Deckenmalerei.wiki` →
   `Template:Infobox Deckenmalerei`). Dropping a new `.wiki` file into the folder is
   enough for it to be imported.

   To create or update them manually instead, copy a file's content into the matching
   `Template:` page in MediaWiki.

## Usage

### Generate Articles Only

Parse the JSON files and save articles as `.wiki` files:

```bash
uv run deckenmalereiwiki parse
```

This creates an `output/` directory with all generated MediaWiki articles.

### Import to MediaWiki

Parse data and automatically import articles with images to MediaWiki:

```bash
uv run deckenmalereiwiki import
```

This will:

1. Upload/update the templates from `templates/`
2. Load and parse JSON data from `sources/`
3. Download images from external URLs
4. Upload images to MediaWiki
5. Create/update articles in MediaWiki

### Import Categories

Create the category pages the `{{Artikel-modern}}` template expects:

```bash
uv run deckenmalereiwiki import-categories
```

This creates the static `CbDD` category, the `AutorInnen` and `Ort` group
categories (both filed under `CbDD`), plus one category per author and one per
location (the part of the title before the first comma). Per-author categories
are filed under `AutorInnen` and per-location categories under `Ort`. Existing
category pages are left untouched, so manually curated descriptions are
preserved.

### Download Images Only (debugging)

Download the images for the articles already in `output/` without touching
MediaWiki — useful for inspecting image handling:

```bash
uv run deckenmalereiwiki download-images
```

For every image referenced by an `output/*.wiki` file this downloads the file
into `downloads/{entity_id}.{ext}` and writes a `downloads/{entity_id}.json`
metadata sidecar recording the provider, license, description and rights/
originator actors that *would* be uploaded. `tests/test_images.py` validates
these against the article references.

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
from deckenmalereiwiki.parser import DeckenmalereiParser
from deckenmalereiwiki.generator import generate_all_articles
from deckenmalereiwiki.importer import MediaWikiImporter

# Parse data
parser = DeckenmalereiParser()
parser.load_data()

# Generate articles
articles = generate_all_articles(parser)

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

## MediaWiki Templates

The templates in [templates/](templates/) are uploaded automatically by the `import`
command:

- **[Infobox_Deckenmalerei.wiki](templates/Infobox_Deckenmalerei.wiki)** – structured
  metadata box at the top of each article (titel, beschreibung, bild, lizenz, author,
  painter, architect, commissioner, entity_id).
- **[Strukturdaten.wiki](templates/Strukturdaten.wiki)** – small, unobtrusive
  structured-data links per section (entity_id → deckenmalerei.eu, optional
  wikidata_qid → Wikidata).
- **[BildMeta.wiki](templates/BildMeta.wiki)** – metadata box on file description pages
  (MediaViewer-compatible).

All parameters are optional.

## Notes

- Uses SQLite database for simpler setup (no separate database container)
- By default, only 10 articles are imported for faster testing (configurable with `max_articles` parameter)
- Image processing is disabled by default (enable with `enable_images=True`)
- Images are named as `Deckenmalerei_{entity_id}.jpg`
- Articles can be re-imported/overwritten by running `importer.py` again
- Large JSON files are loaded into memory - ensure sufficient RAM
