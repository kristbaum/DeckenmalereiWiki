"""Deduplicated, crash-safe CSV output and resume bookkeeping."""

import csv
import hashlib
import os
import re
import threading
from dataclasses import dataclass, field
from pathlib import Path

from checker.config import CSV_COLUMNS, OUTPUT_FILES
from checker.corpus import Article


def model_slug(model: str) -> str:
    """Filesystem-safe short name for a model id."""
    return re.sub(r"[^a-z0-9]+", "-", model.split("/")[-1].lower()).strip("-")


def output_file(task: str, test: bool, model: str, label: str = "") -> Path:
    """Where a run writes. Test runs get their own file, one per model.

    A pilot must never land in the editorial sheet, and must never mark its
    articles as processed - otherwise the real run would skip them. Naming the
    model keeps two comparison runs over the same sample side by side instead
    of appending to each other.
    """
    path = OUTPUT_FILES[task]
    if not test:
        return path
    name = f"{path.stem}_test_{model_slug(model)}"
    if label:
        name += f"_{model_slug(label)}"
    return path.with_name(name + ".csv")


# --------------------------------------------------------------------------
# Output
# --------------------------------------------------------------------------


def finding_hash(finding: dict) -> str:
    """Identity of a finding, independent of which article it was found in.

    Boilerplate sentences recur across many articles; hashing the offending
    passage plus the suggestion collapses those into one editorial row.
    """
    key = " ".join(
        (finding.get("zitat", "") + "|" + finding.get("vorschlag", "")).lower().split()
    )
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


@dataclass
class Row:
    hash: str
    article_title: str
    url: str
    category: str
    proposal: str
    extra_urls: list[str] = field(default_factory=list)

    def to_csv(self, today: str) -> dict:
        return {
            "Festgestellt am": today,
            "Bauwerk": self.article_title,
            "Link zum Bauwerk": self.url,
            "Korrekturvorschlag (Datierung, Ikonografie, etc....)": self.proposal,
            # Deliberately empty: a model citing literature for a Baroque
            # ceiling is guessing. Sources are added by the editors.
            "ggf. Quelle für Korrektur (Literatur, Link, etc.)": "",
            "Status": "offen",
            "bearbeitet am": "",
            "bearbeitet von": "",
            "ggf. redaktioneller Kommentar BearbeiterIn": "",
            "Kategorie": self.category,
            "Betroffene Artikel": str(1 + len(self.extra_urls)),
            "Weitere Fundstellen": " ".join(self.extra_urls[:10]),
            "Fund-ID": self.hash,
        }


class FindingSink:
    """Collects findings, deduplicates them, and keeps the CSV crash-safe.

    A distinct finding is appended to the CSV as soon as it arrives, so an
    interrupted run loses nothing. Repeats of a finding already seen are kept in
    memory and folded into the "Betroffene Artikel" / "Weitere Fundstellen"
    columns by a single atomic rewrite at the end of the run.
    """

    def __init__(self, path: Path, today: str):
        self.path = path
        self.today = today
        self.rows: dict[str, Row] = {}
        self.lock = threading.Lock()
        self._load_existing()

    def _load_existing(self) -> None:
        if not self.path.exists():
            self._write_header()
            return
        with open(self.path, encoding="utf-8", newline="") as handle:
            for record in csv.DictReader(handle):
                key = record.get("Fund-ID")
                if not key:
                    continue
                extra: list[str] = [
                    str(url) for url in (record.get("Weitere Fundstellen") or "").split()
                ]
                self.rows[key] = Row(
                    hash=key,
                    article_title=record.get("Bauwerk", ""),
                    url=record.get("Link zum Bauwerk", ""),
                    category=record.get("Kategorie", ""),
                    proposal=record.get(
                        "Korrekturvorschlag (Datierung, Ikonografie, etc....)", ""
                    ),
                    extra_urls=extra,
                )
        if self.rows:
            print(f"  resuming: {len(self.rows)} finding(s) already in {self.path.name}")

    def _write_header(self) -> None:
        with open(self.path, "w", encoding="utf-8", newline="") as handle:
            csv.DictWriter(handle, fieldnames=CSV_COLUMNS).writeheader()

    def add(self, article: Article, finding: dict, context: str = "") -> bool:
        """Record one finding. Returns True if it was new."""
        key = finding_hash(finding)
        url = article.section_url(finding.get("abschnitt_id") or article.id)
        proposal = (
            f"Zitat: „{finding.get('zitat', '').strip()}“\n"
            f"Vorschlag: {finding.get('vorschlag', '').strip()}\n"
            f"Begründung: {finding.get('begruendung', '').strip()}"
        )
        if context:
            proposal += f"\nKontext: {context}"
        with self.lock:
            existing = self.rows.get(key)
            if existing:
                if url != existing.url and url not in existing.extra_urls:
                    existing.extra_urls.append(url)
                return False
            row = Row(
                hash=key,
                article_title=article.title,
                url=url,
                category=(finding.get("kategorie") or "").strip(),
                proposal=proposal,
            )
            self.rows[key] = row
            with open(self.path, "a", encoding="utf-8", newline="") as handle:
                csv.DictWriter(handle, fieldnames=CSV_COLUMNS).writerow(row.to_csv(self.today))
            return True

    def finalize(self) -> None:
        """Rewrite the CSV once, with the duplicate counts filled in."""
        temp = self.path.with_suffix(".csv.tmp")
        with open(temp, "w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=CSV_COLUMNS)
            writer.writeheader()
            for row in self.rows.values():
                writer.writerow(row.to_csv(self.today))
        os.replace(temp, self.path)


class ProgressLog:
    """Article ids already processed, so a restart skips them.

    Kept separately from the CSV because an article with no findings writes no
    row, and re-querying clean articles on every restart would be the bulk of
    the cost.
    """

    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(exist_ok=True)
        self.done: set[str] = set()
        self.lock = threading.Lock()
        if self.path.exists():
            self.done = {
                line.strip() for line in self.path.read_text(encoding="utf-8").splitlines()
            }

    def mark(self, article_id: str) -> None:
        with self.lock:
            self.done.add(article_id)
            with open(self.path, "a", encoding="utf-8") as handle:
                handle.write(article_id + "\n")
