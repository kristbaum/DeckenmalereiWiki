# DeckenmalereiWiki — Agent Guidelines

MediaWiki article generator and importer for ceiling-painting (Deckenmalerei) data from `sources/` JSON files.

## Architecture

```txt
sources/          Raw JSON data (entities, relations, resources)
src/deckenmalereiwiki/
  loader.py       Loads JSON → in-memory dicts; entity/relation queries
  converter.py    HTML → MediaWiki wikitext
  citations.py    Footnote extraction and deduplication
  generator.py    Assembles templates + article wikitext
  importer.py     MediaWiki API upload via mwclient
  image_handler.py Download images and upload to wiki (ImageDownloader: download-only + metadata sidecars)
  __main__.py     CLI: `parse`, `import`, `import-images`, `download-images` (debug: download + metadata, no wiki)
output/           Generated .wiki files (created at runtime)
downloads/        Downloaded images (created at runtime)
```

## Build and Test

```bash
uv run deckenmalereiwiki               # generate output/*.wiki files (default: 5 articles)
uv run pytest tests/ -v                # run regression tests against generated output
docker compose up -d                   # local MediaWiki at http://localhost:8080
```

**After every code change, run both commands in order** — regenerate first so the tests reflect fresh output:

```bash
uv run deckenmalereiwiki && uv run pytest tests/ -v
```

## Source Data Schema

All three files are flat JSON arrays loaded into memory. The code indexes them as dicts keyed by `ID`.

### `sources/entities.json`

Array of entity objects. Common fields on every entity:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `ID` | string (UUID or numeric) | Primary key |
| `mType` | `"ENT"` | Always `"ENT"` |
| `sType` | string | Entity type (see below) |
| `appellation` | string | Human-readable name/title |
| `creationDate` | number | Unix ms timestamp |
| `modificationDate` | number | Unix ms timestamp |

**Entity types and their additional fields:**

| `sType` | Additional Fields | Role |
| --------- | ------------------- | ------ |
| `TEXT` | `shortText`, `bibliography` | Top-level article (1 174 total); each article maps to a wiki page |
| `TEXT_PART` | `text` (HTML string), `appellation` | Section of a TEXT; assembled in `relOrd` order via PART relations (12 192 total) |
| `OBJECT_ENSEMBLE` | `addressLocality`, `addressState`, `addressCountry`, `addressZip`, `locationLat`, `locationLng`, `functions[]`, `verbaleDating`, `normdata{gnd}`, `condition{damaged}` | Ensemble of buildings |
| `OBJECT_BUILDING` | same address/geo fields, plus `buildingInventoryNumber`, `moduleNumber`, `functions[]`, `verbaleDating` | Single building |
| `OBJECT_BUILDING_DIVISION` | `functions[]`, `verbaleDating` | Wing or division of a building |
| `OBJECT_ROOM` | `verbaleDating` | Room |
| `OBJECT_ROOM_SEQUENCE` | `verbaleDating` | Sequence of rooms |
| `OBJECT_PICTURE_CYCLE` | — | Group of thematically related paintings |
| `OBJECT_PAINTING` | `productionMethods[]`, `iconography[]` | Individual ceiling painting |
| `OBJECT_PAINTING_PART` | `iconography[]` | Part/detail of a painting |
| `ACTOR_PERSON` | `normdata{gnd}`, `gender` (`"MALE"` / `"FEMALE"`) | Historical person |
| `ACTOR_SOCIETY` | `normdata{gnd}` | Institution or society |

### `sources/relations.json`

Array of directed edges. Each relation object:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `ID` | string | **Source** entity ID |
| `relTar` | string | **Target** entity ID |
| `sType` | string | Relation type (see below) |
| `relDir` | `"->"` or `"<-"` | Direction marker; only `"->"` relations are indexed by source |
| `mType` | `"REL"` | Always `"REL"` |
| `relOrd` | number | Sort order (present on `PART` relations only) |
| `creationDate` | number | Unix ms timestamp |

**Relation types** (source → target):

| `sType` | Source → Target | Purpose |
| --------- | ----------------- | --------- |
| `PART` | TEXT / TEXT_PART → TEXT_PART | Ordered article sections; sort by `relOrd` |
| `DOCUMENTS` | TEXT → OBJECT_* | Links article to the objects it documents |
| `LEAD_RESOURCE` | any entity → resource | Primary display image |
| `IMAGE` | OBJECT_* → resource | Gallery images |
| `AUTHORS` | TEXT → ACTOR_PERSON | Text author(s) |
| `PAINTERS` | OBJECT_* → ACTOR_PERSON | Ceiling painter(s) |
| `ARCHITECTS` | OBJECT_* → ACTOR_PERSON | Architect(s) |
| `COMMISSIONERS` | OBJECT_* → ACTOR_PERSON/SOCIETY | Patron(s) / commissioner(s) |
| `PLASTERERS` | OBJECT_* → ACTOR_PERSON | Plasterer(s) |
| `SCULPTORS` | OBJECT_* → ACTOR_PERSON | Sculptor(s) |
| `BUILDERS` | OBJECT_* → ACTOR_PERSON | Builder(s) |
| `DESIGNERS` | OBJECT_* → ACTOR_PERSON | Designer(s) |
| `RIGHTS_HOLDERS` | resource → ACTOR_* | Image rights holder |
| `ORIGINATORS` | resource → ACTOR_* | Image originator/photographer |
| Other actor roles | OBJECT_*→ ACTOR_* | `CARPENTERS`, `CABINETMAKERS`, `TEMPLATE_PROVIDERS`, `IMAGE_CARVERS`, `CONSTRUCTION_MANAGERS`, `POLYCHROMERS`, `ILLUSIONISTIC_CEILING_PAINTERS`, `MARBLE_WORKERS`, `BURNISHERS`, `BUILDING_CRAFTSMEN`, `LANDSCAPE_ARCHITECTS`, `ARTISTS`, `RESIDENTS`, `OWNERS`, `DONORS`, `MEMBERS`, `CITIZENS`, `PEASANTS`, `REFERENCE_PERSONS`, `ASSOCIATION`, `ART_COMMISSIONS` |

### `sources/resources.json`

Array of image resource objects:

| Field | Type | Description |
| ------- | ------ | ------------- |
| `ID` | string (often numeric) | Primary key |
| `mType` | `"RES"` | Always `"RES"` |
| `sType` | `"IMAGE"` | Always `"IMAGE"` |
| `resProvider` | string (URL) | Download URL for the image |
| `resLicense` | string | License text, e.g. `"CC BY-SA 4.0"` |
| `appellation` | string | Caption / title |
| `creationDate` | number | Unix ms timestamp |
| `modificationDate` | number | Unix ms timestamp |

Images are saved locally as `downloads/{entity_ID}.{ext}` and uploaded to MediaWiki under the same name. The extension is resolved per provider (bildindex → `.jpg`; BADW EasyDB → from the API, often `.png`) by `ImageHandler`, and the generator/template use the same resolver so `File:` references always match the uploaded file. All images are downloaded regardless of license; the `{{BildMeta}}` page records a `cc` flag (`ja`/`nein`) classifying the license and a `quelle` link to the original image. `download-images` also writes a `downloads/{entity_ID}.json` metadata sidecar (incl. `source_url`) next to each image.

## Key Conventions

- **Article pipeline**: `TEXT` entity → template + `shortText` + ordered `TEXT_PART` sections (HTML converted to wikitext) + bibliography + `<references />`
- **Image lookup**: `TEXT/TEXT_PART` → `DOCUMENTS` → `OBJECT_*` → `IMAGE` → resource (not directly on TEXT entities)
- **Citation handling**: Footnote markers in `TEXT_PART.text` HTML are extracted, deduplicated across parts, and re-emitted with consistent `<ref name="…">` tags
- **Relation indexing**: `loader.py` only indexes `relDir == "->"` relations; `"<-"` relations (e.g., `RIGHTS_HOLDERS`, `ORIGINATORS`, `MEMBERS`) must be queried from the target side
- `max_articles` (default 5 in CLI, 10 in README) limits processing for testing; set to `None` for full import
