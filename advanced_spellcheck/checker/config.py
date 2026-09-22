"""Paths, models and constants shared across the checker."""


from checker import REPO_ROOT

HERE = REPO_ROOT / "advanced_spellcheck"
GLOSSARY_FILE = HERE / "glossary.txt"
PROGRESS_DIR = HERE / ".progress"
OUTPUT_FILES = {
    "simple": HERE / "Korrekturmeldungen_Datenbank_llm_einfach.csv",
    "complex": HERE / "Korrekturmeldungen_Datenbank_llm_complex.csv",
}

ENV_FILE = REPO_ROOT / ".env"

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_MODELS_URL = "https://openrouter.ai/api/v1/models"

DEFAULT_MODELS = {
    "simple": "mistralai/mistral-small-3.2-24b-instruct",
    "complex": "openai/gpt-oss-120b",
}
# USD per million tokens (prompt, completion). Only a fallback for the cost
# estimate - the real numbers are fetched live from OpenRouter when possible.
FALLBACK_PRICES = {
    "mistralai/mistral-small-3.2-24b-instruct": (0.094, 0.25),
    "openai/gpt-oss-120b": (0.15, 0.60),
}

# German averages ~3 characters per token across the tokenizers in use here.
CHARS_PER_TOKEN = 3
# Text tokens per request. Sections of one article are packed up to this budget;
# articles are never mixed, so a finding can always be attributed to one article.
DEFAULT_TOKEN_BUDGET = 6000
# Quoted passages longer than this are historical transcriptions, not prose the
# editors wrote, and get masked out before the text is sent.
QUOTE_MASK_MIN_LENGTH = 40
# Terms injected into the prompt so the model stops reporting them as typos.
GLOSSARY_PROMPT_LIMIT = 300

PORTAL_URL = "https://www.deckenmalerei.eu/"

CSV_COLUMNS = [
    "Festgestellt am",
    "Bauwerk",
    "Link zum Bauwerk",
    "Korrekturvorschlag (Datierung, Ikonografie, etc....)",
    "ggf. Quelle für Korrektur (Literatur, Link, etc.)",
    "Status",
    "bearbeitet am",
    "bearbeitet von",
    "ggf. redaktioneller Kommentar BearbeiterIn",
    # Added by this script, beyond the manual sheet's schema:
    "Kategorie",
    "Betroffene Artikel",
    "Weitere Fundstellen",
    "Fund-ID",
]
