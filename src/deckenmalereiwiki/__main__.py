"""CLI entry point: python -m deckenmalereiwiki [parse|import]"""

import sys
from pathlib import Path

from deckenmalereiwiki.loader import DataLoader
from deckenmalereiwiki.generator import ArticleGenerator, title_to_filename
from deckenmalereiwiki.importer import MediaWikiImporter
from deckenmalereiwiki.image_handler import ImageDownloader


def parse_command():
    """Parse data and save articles as .wiki files."""
    loader = DataLoader()
    loader.load_data()
    ArticleGenerator(loader).save_articles_to_files()
    print("\nDone!")


def import_command():
    """Upload pre-generated .wiki files from output/ to MediaWiki."""
    importer = MediaWikiImporter()
    if importer.login():
        importer.import_from_output_folder()
        print("\n✓ Import complete!")
    else:
        print("\n✗ Import failed - could not login")


def import_images_command():
    """Download and upload images for all articles to MediaWiki."""
    loader = DataLoader()
    loader.load_data()

    importer = MediaWikiImporter()
    if not importer.login():
        print("\n✗ Import failed - could not login")
        return

    text_entities = loader.get_text_entities()[: importer.max_articles]
    print(f"\n=== Processing images for {len(text_entities)} articles ===")
    for entity in text_entities:
        title = entity.get("appellation", f"Untitled_{entity['ID']}")
        print(f"\nProcessing images for: {title}")
        importer._process_entity_images(loader, entity)
    print("\n✓ Image import complete!")


def download_images_command(output_dir: str = "output"):
    """Download (no upload) images for the articles in *output_dir*.

    Debugging aid: requires no MediaWiki connection. For every ``.wiki`` file
    in the output folder it downloads the associated images into ``downloads/``
    and writes a ``{entity_id}.json`` metadata sidecar next to each one.
    """
    output_path = Path(output_dir)
    wiki_stems = {p.stem for p in output_path.glob("*.wiki")}
    if not wiki_stems:
        print(f"No .wiki files found in {output_path}/ — run 'parse' first.")
        return

    loader = DataLoader()
    loader.load_data()

    downloads_dir = Path("downloads")
    downloads_dir.mkdir(exist_ok=True)
    downloader = ImageDownloader(loader, downloads_dir)

    entities = [
        e
        for e in loader.get_text_entities()
        if title_to_filename(e.get("appellation", f"Untitled_{e['ID']}")) in wiki_stems
    ]
    print(
        f"\n=== Downloading images for {len(entities)} article(s) from {output_path}/ ==="
    )
    for entity in entities:
        title = entity.get("appellation", f"Untitled_{entity['ID']}")
        print(f"\nDownloading images for: {title}")
        downloader.download_entity_images(entity)
    print("\n✓ Image download complete!")


def main():
    """Main entry point with subcommand support."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "parse":
            parse_command()
        elif command == "import":
            import_command()
        elif command == "import-images":
            import_images_command()
        elif command == "download-images":
            download_images_command()
        else:
            print(f"Unknown command: {command}")
            print(
                "Usage: python -m deckenmalereiwiki "
                "[parse|import|import-images|download-images]"
            )
            sys.exit(1)
    else:
        # Default: parse only (no wiki upload). Resolving image extensions may
        # query the BADW EasyDB API for not-yet-downloaded images; bildindex
        # images and already-downloaded files resolve offline.
        parse_command()


if __name__ == "__main__":
    main()
