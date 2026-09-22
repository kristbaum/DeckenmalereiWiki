# Advanced Spellcheck — finding trivial and complex errors in the CbDD texts

Automated proofreading of the *Corpus der barocken Deckenmalerei in Deutschland* (CbDD)
texts in [`sources/entities.json`](../sources/entities.json).
[`spellcheck.py`](spellcheck.py) sends every article through the
[OpenRouter](https://openrouter.ai) API — a cheap model for mechanical errors, a
reasoning model for substantive ones — and writes the findings into two CSV files
shaped like the manually maintained `Korrekturmeldungen_Datenbank.csv`, so both can be
merged into one editorial sheet.

The script produces **review candidates, not corrections**. It never touches the
database, and it never fills the `Quelle` column: a model citing literature for a
Baroque ceiling is guessing.

## Usage

```bash
export OPENROUTER_API_KEY=sk-or-...

uv run python advanced_spellcheck/spellcheck.py --build-glossary   # once, then prune
uv run python advanced_spellcheck/spellcheck.py --task simple --test --dry-run
uv run python advanced_spellcheck/spellcheck.py --task simple --test
uv run python advanced_spellcheck/spellcheck.py --task simple
uv run python advanced_spellcheck/spellcheck.py --task complex
```

| Option | Effect |
| ------ | ------ |
| `--task simple\|complex\|both` | which pass to run (default `simple`) |
| `--test` | seeded random sample of articles, written to a separate `*_test.csv` |
| `--test-size N` / `--seed N` | sample size (default 10) and seed (default 42) |
| `--dry-run` | print request count and a live-priced cost estimate, send nothing |
| `--model ID` | override the model for the task |
| `--limit N` | process only the first N articles |
| `--workers N` | articles in flight in parallel (default 8) |
| `--token-budget N` | text tokens per request (default 6000; ×3 for the complex pass) |
| `--reasoning low\|medium\|high` | reasoning effort for the complex pass (default `medium`) |
| `--build-glossary` | rebuild `glossary.txt` from the corpus |

A `--test` run is isolated: its findings go to `*_test.csv` and its progress is tracked
separately, so a pilot never lands in the editorial sheet and never causes the real run
to skip articles.

## The two passes

**`simple`** — spelling, typos, punctuation, German typography („…"), leftover markup
and placeholder text, inconsistent spelling of a name within one article. Runs at
`temperature = 0` on a non-thinking model, so no tokens are spent on reasoning.
Output: `Korrekturmeldungen_Datenbank_llm_einfach.csv`.

**`complex`** — unclear or garbled sentences, internal contradictions, references to
figures or ground plans that are not present, unexplained abbreviations, style. Gets a
3× token budget so whole articles fit into one request; contradictions are only visible
across sections. Output: `Korrekturmeldungen_Datenbank_llm_complex.csv`.

Each pass tells the model explicitly that the other one's territory is out of scope.

## Models

Defaults, both overridable with `--model`. Prices are USD per million tokens
(input / output) as listed on 2026-09-21; `--dry-run` fetches them live.

| Pass | Model | $/M in | $/M out |
| ---- | ----- | ------ | ------- |
| `simple` | `mistralai/mistral-small-3.2-24b-instruct` | 0.094 | 0.25 |
| `complex` | `openai/gpt-oss-120b` | 0.15 | 0.60 |

Mistral Small is Apache 2.0, dense 24 B, trained with a European-language focus — the
safest cheap option for German orthography, and it wastes nothing on reasoning.
gpt-oss-120b is Apache 2.0, 117 B MoE with 5.1 B active and a configurable reasoning
effort; it is the cheapest model of its class, which matters because reasoning tokens
dominate that bill.

Measured with `--dry-run` over the full corpus (1 366 articles, ~10 M prompt tokens
including the glossary): **~$1.15 for the simple pass, ~$4 for the complex pass.**
Inference is not the constraint — editorial review time is. A model reporting 5 000
findings at 30 % precision is worse than one reporting 800 at 80 %.

These defaults were chosen on model class, licence and price, not on a German-language
benchmark. Before a full run, pilot two candidates on the same `--test` sample (the seed
makes it identical across models) and count true against false positives by hand.
Worth comparing: `qwen/qwen3-30b-a3b-instruct-2507` (0.048/0.19) for the simple pass,
`deepseek/deepseek-v3.2` (0.27/0.40) or `qwen/qwen3-235b-a22b-thinking-2507`
(0.23/2.30) for the complex one.

## How the known problems are handled

**Historical orthography and inscriptions.** Quoted passages longer than 40 characters
and every `<blockquote>` are replaced with a `[ZITAT]` placeholder *before* the text is
sent, so the model cannot flag them at all — more reliable than asking it to ignore
them. Short quoted terms stay visible; those are ordinary vocabulary. Footnote
definitions and inline `[n]` markers are stripped too: bibliographic strings have
punctuation conventions of their own and would otherwise dominate the findings.

**Art-historical vocabulary.** `--build-glossary` counts capitalised words across the
corpus and keeps those a general German wordlist (`/usr/share/dict/ngerman`, or
`--dictionary`) does not know — which yields exactly the domain terms
(*Supraporte*, *Scheinarchitektur*, *Plafond*), mythological names (*Bacchus*,
*Aeneas*) and building parts (*Südflügel*) that models report as typos. Words the
dictionary knows are dropped; they are never falsely flagged and would only cost prompt
tokens. The result lands in `glossary.txt` for hand-pruning; the first 300 lines are
injected into every prompt. Without a system dictionary the list falls back to plain
frequency and needs more pruning.

**Duplicates.** The same boilerplate sentence recurs across many articles. Findings are
hashed on the offending passage plus the suggestion, and each distinct finding gets one
CSV row; repeats are folded into the `Betroffene Artikel` count and `Weitere
Fundstellen` links. The hash is kept in the `Fund-ID` column, so a later run recognises
findings already in the sheet.

**Interruptions.** A distinct finding is appended to the CSV the moment it arrives, so
nothing is lost on a crash; the duplicate counts are filled in by one atomic rewrite at
the end. Processed article ids are appended to `.progress/{task}.txt` — kept separate
from the CSV because a clean article writes no row, and re-querying clean articles on
every restart would be most of the cost. Re-running the same command resumes.
Failed requests are retried five times with exponential backoff, honouring
`Retry-After`; an article that still fails is logged and skipped, not fatal.

**Determinism.** `temperature = 0` everywhere, pinned model versions, and a fixed
sample seed, so two runs — or two models over the same articles — are comparable.

## Output columns

The nine columns of `Korrekturmeldungen_Datenbank.csv`, filled with the run date,
`Bauwerk`, a section-deep link (`https://www.deckenmalerei.eu/{TEXT.ID}#{TEXT_PART.ID}`),
the finding as *Zitat / Vorschlag / Begründung*, and `Status = offen`. The editor
columns are left empty. Four columns are appended beyond that schema: `Kategorie`,
`Betroffene Artikel`, `Weitere Fundstellen`, `Fund-ID`.

The model is asked for strict JSON and the CSV is written here — German prose is full of
commas, quotes and newlines, so asking a model for CSV directly does not survive contact
with the corpus.
