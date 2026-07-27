#!/usr/bin/env python3
"""Build the static book shelf from Goodreads' public RSS feeds."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib.request import Request, urlopen
from xml.etree import ElementTree

DEFAULT_USER_ID = "40542943"
DEFAULT_PROFILE_URL = "https://www.goodreads.com/user/show/40542943-revan"
FEED_URL = "https://www.goodreads.com/review/list_rss/{user_id}?shelf={shelf}"
USER_AGENT = "RRAirreBookshelf/1.0"


def node_text(node: ElementTree.Element, name: str) -> str:
    child = node.find(name)
    return " ".join((child.text or "").split()) if child is not None else ""


def parse_date(value: str) -> datetime | None:
    if not value:
        return None
    parsed = parsedate_to_datetime(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def fetch_feed(user_id: str, shelf: str) -> bytes:
    url = FEED_URL.format(user_id=user_id, shelf=shelf)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    with urlopen(request, timeout=30) as response:
        return response.read()


def parse_feed(content: bytes) -> tuple[list[dict[str, str]], datetime | None]:
    channel = ElementTree.fromstring(content).find("channel")
    if channel is None:
        raise ValueError("Goodreads returned an RSS feed without a channel.")

    books: list[dict[str, str]] = []
    for item in channel.findall("item"):
        books.append(
            {
                "title": node_text(item, "title"),
                "author": node_text(item, "author_name"),
                "book_id": node_text(item, "book_id"),
                "image": node_text(item, "book_large_image_url")
                or node_text(item, "book_medium_image_url"),
                "added_at": node_text(item, "user_date_added"),
                "read_at": node_text(item, "user_read_at"),
                "feed_date": node_text(item, "pubDate"),
            }
        )

    return books, parse_date(node_text(channel, "lastBuildDate"))


def sort_date(book: dict[str, str], *fields: str) -> datetime:
    for field in (*fields, "feed_date"):
        value = parse_date(book.get(field, ""))
        if value is not None:
            return value
    return datetime.min.replace(tzinfo=timezone.utc)


def book_url(book: dict[str, str]) -> str:
    return f"https://www.goodreads.com/book/show/{book['book_id']}"


def public_book(book: dict[str, str]) -> dict[str, str]:
    return {
        "id": book["book_id"],
        "title": book["title"],
        "author": book["author"],
        "url": book_url(book),
        "image": book["image"],
    }


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def group_read_books(
    books: list[dict[str, str]], curation: dict[str, object]
) -> list[dict[str, object]]:
    excluded = {str(book_id) for book_id in curation.get("exclude", [])}
    categories = curation.get("categories", {})
    if not isinstance(categories, dict):
        raise ValueError("Curation categories must be an object.")

    category_by_id: dict[str, str] = {}
    for category, book_ids in categories.items():
        if not isinstance(book_ids, list):
            raise ValueError(f"Curation category {category!r} must be a list.")
        for book_id in book_ids:
            key = str(book_id)
            if key in category_by_id:
                raise ValueError(f"Book {key} appears in more than one category.")
            category_by_id[key] = str(category)

    grouped: dict[str, list[dict[str, str]]] = {
        str(category): [] for category in categories
    }
    grouped["Other"] = []

    for book in books:
        if book["book_id"] in excluded:
            continue
        category = category_by_id.get(book["book_id"], "Other")
        grouped[category].append(public_book(book))

    return [
        {"name": category, "books": category_books}
        for category, category_books in grouped.items()
        if category_books
    ]


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser()
    parser.add_argument("--user-id", default=DEFAULT_USER_ID)
    parser.add_argument("--profile-url", default=DEFAULT_PROFILE_URL)
    parser.add_argument("--output", type=Path, default=root / "data" / "books.json")
    parser.add_argument(
        "--curation", type=Path, default=root / "data" / "books-curation.json"
    )
    args = parser.parse_args()

    curation = json.loads(args.curation.read_text(encoding="utf-8"))
    excluded = {str(book_id) for book_id in curation.get("exclude", [])}
    move_to_read = {str(book_id) for book_id in curation.get("moveToRead", [])}

    read, read_updated = parse_feed(fetch_feed(args.user_id, "read"))
    currently_reading, current_updated = parse_feed(
        fetch_feed(args.user_id, "currently-reading")
    )

    read_ids = {book["book_id"] for book in read}
    read.extend(
        book
        for book in currently_reading
        if book["book_id"] in move_to_read and book["book_id"] not in read_ids
    )
    currently_reading = [
        book
        for book in currently_reading
        if book["book_id"] not in excluded and book["book_id"] not in move_to_read
    ]

    read.sort(key=lambda book: sort_date(book, "read_at", "added_at"), reverse=True)
    currently_reading.sort(key=lambda book: sort_date(book, "added_at"), reverse=True)

    timestamps = [stamp for stamp in (read_updated, current_updated) if stamp is not None]
    payload = {
        "source": args.profile_url,
        "updated": iso_utc(max(timestamps)) if timestamps else None,
        "readGroups": group_read_books(read, curation),
        "currentlyReading": [public_book(book) for book in currently_reading],
    }
    output = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"

    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists() and args.output.read_text(encoding="utf-8") == output:
        print("Goodreads shelf is already current.")
        return

    temporary = args.output.with_suffix(".tmp")
    temporary.write_text(output, encoding="utf-8")
    temporary.replace(args.output)
    read_count = sum(len(group["books"]) for group in payload["readGroups"])
    print(
        f"Updated {args.output} with {read_count} read and "
        f"{len(payload['currentlyReading'])} currently-reading books."
    )


if __name__ == "__main__":
    main()
