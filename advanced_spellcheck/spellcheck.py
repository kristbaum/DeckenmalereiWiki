#!/usr/bin/env python3
"""Automated proofreading of the CbDD texts via the OpenRouter API.

Two passes over the article texts in ``sources/entities.json``:

``simple``
    Mechanical errors (spelling, punctuation, typography, leftover markup),
    checked with a cheap non-thinking model.
``complex``
    Judgement calls (unclear sentences, contradictions, dangling references,
    style), checked with a reasoning model over whole articles.

Findings are appended to CSV files that mirror the columns of the manually
maintained ``Korrekturmeldungen_Datenbank.csv``, so both can be merged into one
editorial sheet. The script never edits the database - it only produces review
candidates.

The pipeline lives in the ``checker`` package next to this file; this module is
only the command line.

Usage:
    export OPENROUTER_API_KEY=sk-or-...        # or put it in .env
    uv run python advanced_spellcheck/spellcheck.py --task simple --test
    uv run python advanced_spellcheck/spellcheck.py --task simple
    uv run python advanced_spellcheck/spellcheck.py --task complex
    uv run python advanced_spellcheck/spellcheck.py --build-glossary
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import argparse

from checker import REPO_ROOT
from checker.config import DEFAULT_TOKEN_BUDGET
from checker.corpus import DataLoader, load_articles, select_articles
from checker.glossary import build_glossary
from checker.run import run_task


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--task", choices=["simple", "complex", "both"], default="simple")
    parser.add_argument("--model", help="override the default model for the task")
    parser.add_argument("--test", action="store_true", help="seeded random sample of articles")
    parser.add_argument("--test-size", type=int, default=10)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--limit", type=int, help="process only the first N articles")
    parser.add_argument("--workers", type=int, default=8, help="parallel articles in flight")
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument(
        "--reasoning",
        choices=["low", "medium", "high"],
        default="medium",
        help="reasoning effort for the complex pass",
    )
    parser.add_argument(
        "--label",
        default="",
        help="tag a test run, to compare settings of the same model side by side",
    )
    parser.add_argument(
        "--show-prompts",
        action="store_true",
        help="print every prompt and raw answer (implied by --test; forces one worker)",
    )
    parser.add_argument(
        "--no-show-prompts",
        action="store_true",
        help="suppress the prompt/answer output that --test turns on",
    )
    parser.add_argument("--dry-run", action="store_true", help="estimate cost, send nothing")
    parser.add_argument(
        "--no-glossary",
        action="store_true",
        help="send no glossary, to test whether it earns its prompt tokens",
    )
    parser.add_argument("--build-glossary", action="store_true")
    parser.add_argument("--glossary-min-count", type=int, default=10)
    parser.add_argument("--glossary-limit", type=int, default=600)
    parser.add_argument(
        "--dictionary",
        help="German wordlist for filtering the glossary "
        "(default: /usr/share/dict/ngerman if present)",
    )
    args = parser.parse_args()

    loader = DataLoader(str(REPO_ROOT / "sources"))
    loader.load_data()
    articles = load_articles(loader)
    print(f"Prepared {len(articles)} article(s)")

    if args.build_glossary:
        build_glossary(
            articles,
            args.glossary_min_count,
            args.glossary_limit,
            Path(args.dictionary) if args.dictionary else None,
        )
        return

    selected = select_articles(
        articles,
        test=args.test,
        test_size=args.test_size,
        seed=args.seed,
        limit=args.limit,
    )
    if args.test:
        print(f"Test run: {len(selected)} article(s), seed {args.seed}")

    for task in (["simple", "complex"] if args.task == "both" else [args.task]):
        run_task(task, args, selected)


if __name__ == "__main__":
    main()
