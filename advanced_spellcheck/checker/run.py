"""Driving a pass: fan out over articles, collect and report findings."""

import argparse
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

from checker.chunking import Chunk, chunk_article, estimate_tokens
from checker.client import OpenRouterClient, fetch_prices, parse_findings, read_api_key
from checker.config import (
    DEFAULT_MODELS,
    ENV_FILE,
    GLOSSARY_PROMPT_LIMIT,
    PROGRESS_DIR,
)
from checker.corpus import Article
from checker.glossary import load_glossary
from checker.output import FindingSink, ProgressLog, model_slug, output_file
from checker.prompts import SYSTEM_PROMPTS, build_user_prompt
from checker.validation import _loose, find_context, validate_finding


def report_estimate(chunks: list[Chunk], model: str, system: str, glossary: list[str]) -> None:
    overhead = estimate_tokens(system) + estimate_tokens(", ".join(glossary[:GLOSSARY_PROMPT_LIMIT]))
    prompt_tokens = sum(chunk.tokens + overhead for chunk in chunks)
    price_in, price_out = fetch_prices(model)
    # Output is a rough guess: findings are short, reasoning models are not.
    assumed_out = prompt_tokens * (0.5 if "oss" in model or "thinking" in model else 0.08)
    cost = prompt_tokens / 1e6 * price_in + assumed_out / 1e6 * price_out
    print(f"  requests:      {len(chunks)}")
    print(f"  prompt tokens: ~{prompt_tokens:,}")
    print(f"  price:         ${price_in:.3f} / ${price_out:.3f} per M tokens")
    print(f"  estimated:     ~${cost:.2f}")


# --------------------------------------------------------------------------
# Run
# --------------------------------------------------------------------------


def process_article(
    article: Article,
    chunks: list[Chunk],
    client: OpenRouterClient,
    sink: FindingSink,
    system: str,
    glossary: list[str],
    max_tokens: int,
    reasoning: str | None,
) -> tuple[int, int, Counter[str]]:
    """Query every chunk of one article.

    Returns (new findings, duplicates, rejections by reason).
    """
    new = duplicates = 0
    rejected: Counter[str] = Counter()
    for chunk in chunks:
        raw = client.complete(
            system,
            build_user_prompt(chunk, glossary),
            max_tokens=max_tokens,
            reasoning=reasoning,
        )
        known_ids = {s.id for s in chunk.sections}
        source = " ".join(s.text for s in chunk.sections)
        haystack = _loose(source)
        for finding in parse_findings(raw):
            reason = validate_finding(finding, haystack)
            if reason:
                rejected[reason] += 1
                continue
            # Keep the model from attributing a finding to a section it was
            # never shown; fall back to the article itself.
            if finding.get("abschnitt_id") not in known_ids:
                finding["abschnitt_id"] = article.id
            if sink.add(article, finding, find_context(finding["zitat"], source)):
                new += 1
            else:
                duplicates += 1
    return new, duplicates, rejected


def run_task(task: str, args: argparse.Namespace, articles: list[Article]) -> None:
    model = args.model or DEFAULT_MODELS[task]
    system = SYSTEM_PROMPTS[task]
    glossary = [] if args.no_glossary else load_glossary()
    reasoning = args.reasoning if task == "complex" else None
    # Reasoning tokens count against max_tokens, so the complex pass needs
    # far more headroom than its findings alone would suggest.
    max_tokens = 12000 if task == "complex" else 4000
    # The complex pass needs whole articles in one request to see
    # contradictions across sections; the simple pass does not.
    budget = args.token_budget * (3 if task == "complex" else 1)

    # A pilot is read by a human, so show it the prompts and the untouched
    # answers; parallel workers would interleave that output beyond use.
    echo = args.show_prompts or (args.test and not args.no_show_prompts)
    workers = 1 if echo else args.workers

    print(f"\n=== {task} pass ===")
    print(f"  model:    {model}")
    print(f"  glossary: {len(glossary)} term(s)" if glossary else "  glossary: none (run --build-glossary)")

    label = getattr(args, "label", "") or ""
    suffix = f"-test-{model_slug(model)}{'-' + model_slug(label) if label else ''}" if args.test else ""
    progress = ProgressLog(PROGRESS_DIR / f"{task}{suffix}.txt")
    pending = [a for a in articles if a.id not in progress.done]
    skipped = len(articles) - len(pending)
    if skipped:
        print(f"  skipping {skipped} article(s) already processed")

    work = [(article, chunk_article(article, budget)) for article in pending]
    all_chunks = [chunk for _, chunks in work for chunk in chunks]
    print(f"  articles: {len(pending)}")
    report_estimate(all_chunks, model, system, glossary)

    if args.dry_run:
        print("  dry run - no requests sent")
        return
    if not work:
        print("  nothing to do")
        return

    api_key = read_api_key()
    if not api_key:
        sys.exit(
            "No OpenRouter API key. Either export OPENROUTER_API_KEY, or put\n"
            f"OPENROUTER_API_KEY=sk-or-... into {ENV_FILE} (git-ignored)."
        )

    client = OpenRouterClient(api_key, model, echo=echo)
    destination = output_file(task, args.test, model, label)
    sink = FindingSink(destination, datetime.now(tz=timezone.utc).strftime("%d.%m.%Y"))
    new_total = duplicate_total = failed = 0
    rejected_total: Counter[str] = Counter()

    try:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futures = {
                pool.submit(
                    process_article,
                    article,
                    chunks,
                    client,
                    sink,
                    system,
                    glossary,
                    max_tokens,
                    reasoning,
                ): article
                for article, chunks in work
            }
            for index, future in enumerate(as_completed(futures), start=1):
                article = futures[future]
                try:
                    new, duplicates, rejected = future.result()
                except Exception as exc:  # one article must not end the run
                    failed += 1
                    print(f"  [{index}/{len(work)}] FAILED {article.title}: {exc}")
                    continue
                progress.mark(article.id)
                new_total += new
                duplicate_total += duplicates
                rejected_total.update(rejected)
                print(
                    f"  [{index}/{len(work)}] {article.title[:60]:<60} "
                    f"{new} new, {duplicates} dup"
                )
    except KeyboardInterrupt:
        print("\n  interrupted - findings so far are on disk, re-run to continue")
    finally:
        sink.finalize()

    price_in, price_out = fetch_prices(model)
    spent = (
        client.prompt_tokens / 1e6 * price_in + client.completion_tokens / 1e6 * price_out
    )
    print(f"\n  {new_total} new finding(s), {duplicate_total} duplicate(s), {failed} failure(s)")
    if rejected_total:
        detail = ", ".join(f"{count}× {reason}" for reason, count in rejected_total.most_common())
        print(f"  {sum(rejected_total.values())} rejected by validation: {detail}")
    print(f"  tokens: {client.prompt_tokens:,} in / {client.completion_tokens:,} out (~${spent:.2f})")
    print(f"  wrote {destination}")
