#!/usr/bin/env python3
"""
add-book.py — add a companion-guide PDF you already have on disk.

    pip install pymupdf pillow
    python3 tools/add-book.py "4. House of Chains Guide.pdf"

The reading-order number and title are read from the filename when it looks
like "4. House of Chains Guide.pdf"; override either with --num / --title.

To pull decks straight from the author's Google Drive folder instead, use
tools/sync-drive.py — same parser, no manual downloading.
"""
import argparse, os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide_lib as G


def main():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter, description=__doc__)
    ap.add_argument("pdf")
    ap.add_argument("--title", help='e.g. "House of Chains"')
    ap.add_argument("--num", type=int, help="position in the reading order")
    ap.add_argument("--key", help="slug override, e.g. house-of-chains")
    a = ap.parse_args()

    if not os.path.exists(a.pdf):
        sys.exit(f"No such file: {a.pdf}")

    guess_num, guess_title = G.parse_deck_name(os.path.basename(a.pdf))
    title = a.title or guess_title
    num = a.num if a.num is not None else guess_num
    if not title or num is None:
        sys.exit("Couldn't read the title/number from the filename — "
                 "pass --title and --num.")

    print(f"\n{num}. {title}")
    G.install(a.pdf, title, num, key=a.key)

    v = G.bump_cache_version()
    if v:
        print(f"\nsw.js cache is now malazan-v{v}. Re-upload the folder.")


if __name__ == "__main__":
    main()
