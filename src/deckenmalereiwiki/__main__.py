"""CLI entry point: python -m deckenmalereiwiki [parse|import]"""

import sys

from deckenmalereiwiki.loader import DataLoader
from deckenmalereiwiki.generator import ArticleGenerator
from deckenmalereiwiki.importer import MediaWikiImporter


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


def main():
    """Main entry point with subcommand support."""
    if len(sys.argv) > 1:
        command = sys.argv[1]
        if command == "parse":
            parse_command()
        elif command == "import":
            import_command()
        else:
            print(f"Unknown command: {command}")
            print("Usage: python -m deckenmalereiwiki [parse|import]")
            sys.exit(1)
    else:
        # Default: parse only (safe, no network needed)
        parse_command()


if __name__ == "__main__":
    main()
