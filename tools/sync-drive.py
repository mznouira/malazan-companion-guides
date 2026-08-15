#!/usr/bin/env python3
"""
sync-drive.py — build books straight from the author's Google Slides decks.

The guides live in a shared Drive folder. Google exports any publicly-viewable
presentation as PDF with no API key and no login:

    https://docs.google.com/presentation/d/<FILE_ID>/export/pdf

This script fetches those exports and runs them through the same parser as
tools/add-book.py, so a deck the author revises can be re-pulled at any time.

USAGE

  List what's in the shared folder and write books/sources.json:
      python3 tools/sync-drive.py --folder "<folder url or id>" --list

  Build everything listed in books/sources.json:
      python3 tools/sync-drive.py --sync

  Build (or rebuild) one deck, skipping the folder listing entirely:
      python3 tools/sync-drive.py --deck "<presentation url or id>" \
                                  --title "House of Chains" --num 4

  Rebuild only certain books after the author updates a deck:
      python3 tools/sync-drive.py --sync --only house-of-chains

Folder listing depends on Google's undocumented page markup and can break.
If --list finds nothing, open the folder in a browser, copy each deck's URL,
and add entries to books/sources.json by hand — the format is right there,
and --sync only ever reads that file.
"""
import argparse, codecs, json, os, re, sys, tempfile, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import guide_lib as G

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
SOURCES = os.path.join(G.ROOT, "books", "sources.json")
ID_RE = re.compile(r'[-\w]{25,}')


def get(url, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def extract_id(s):
    """Accept a full Drive/Slides URL or a bare file id."""
    m = ID_RE.search(s or "")
    if not m:
        sys.exit(f"Could not find a Drive id in: {s}")
    return m.group(0)


# ------------------------------------------------------------------ listing

def list_folder(folder):
    """Return [{'id':…, 'name':…}] for presentations in a shared folder."""
    fid = extract_id(folder)
    html = get(f"https://drive.google.com/drive/folders/{fid}")

    found, seen = [], set()

    # Drive embeds the listing in a JS blob; the shape has changed over the
    # years, so try the known one first and fall back to a generic scan.
    m = re.search(r"window\['_DRIVE_ivd'\]\s*=\s*'([^']+)'", html)
    if m:
        try:
            blob = json.loads(codecs.decode(m.group(1), "unicode_escape"))
            for row in blob[0]:
                fid_, name = row[0], row[2]
                if fid_ not in seen:
                    seen.add(fid_)
                    found.append({"id": fid_, "name": name})
        except Exception:
            pass

    if not found:
        # Generic scan: ids paired with a nearby quoted filename.
        for fid_, name in re.findall(r'"([-\w]{25,})",\s*"[^"]*",\s*"([^"]{3,120})"', html):
            if fid_ not in seen and not name.startswith("http"):
                seen.add(fid_)
                found.append({"id": fid_, "name": name})

    return found


def cmd_list(folder):
    items = list_folder(folder)
    if not items:
        print("Found nothing. Google may have changed the folder markup, or the\n"
              "folder isn't shared publicly. Open it in a browser, copy each\n"
              "deck's URL, and write books/sources.json yourself:\n")
        print(json.dumps([{"id": "<file id>", "num": 4,
                           "title": "House of Chains",
                           "key": "house-of-chains"}], indent=2))
        return

    rows = []
    for it in items:
        num, title = G.parse_deck_name(it["name"])
        rows.append({"id": it["id"], "num": num, "title": title,
                     "key": G.slugify(title) if title else None,
                     "source_name": it["name"]})

    rows.sort(key=lambda r: (r["num"] is None, r["num"] or 0))
    os.makedirs(os.path.dirname(SOURCES), exist_ok=True)
    json.dump(rows, open(SOURCES, "w"), ensure_ascii=False, indent=2)

    print(f"Wrote {SOURCES} — {len(rows)} decks:\n")
    for r in rows:
        flag = "" if (r["num"] and r["title"]) else "   <- fill in num/title"
        print(f"  {str(r['num'] or '?'):>2}. {r['title'] or r['source_name']}{flag}")
    print("\nCheck the numbering, then:  python3 tools/sync-drive.py --sync")


# ------------------------------------------------------------------ building

def build_one(file_id, title, num, key=None):
    url = f"https://docs.google.com/presentation/d/{file_id}/export/pdf"
    print(f"\n{num}. {title}")
    print(f"  downloading {file_id} …")
    try:
        pdf = get(url, binary=True)
    except Exception as e:
        print(f"  ! download failed ({e}). Is the deck shared as "
              f"'anyone with the link'?")
        return None
    if not pdf.startswith(b"%PDF"):
        print("  ! Google returned a login page, not a PDF — the deck isn't public.")
        return None

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(pdf)
        tmp = f.name
    try:
        return G.install(tmp, title, num, key=key)
    finally:
        os.unlink(tmp)


def cmd_sync(only):
    if not os.path.exists(SOURCES):
        sys.exit(f"No {SOURCES}. Run --folder <url> --list first, "
                 "or write the file by hand.")
    rows = json.load(open(SOURCES))
    todo = [r for r in rows if r.get("num") and r.get("title")
            and (not only or (r.get("key") or G.slugify(r["title"])) in only)]
    if not todo:
        sys.exit("Nothing to build. Every entry needs both 'num' and 'title'.")

    built = 0
    for r in todo:
        if build_one(r["id"], r["title"], r["num"], r.get("key")):
            built += 1

    if built:
        v = G.bump_cache_version()
        print(f"\n{built} book(s) built. sw.js cache is now malazan-v{v}." if v
              else f"\n{built} book(s) built.")
        print("Re-upload the folder to your host.")


def main():
    ap = argparse.ArgumentParser(
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description=__doc__)
    ap.add_argument("--folder", help="shared Drive folder URL or id")
    ap.add_argument("--list", action="store_true",
                    help="list the folder into books/sources.json")
    ap.add_argument("--sync", action="store_true",
                    help="build everything in books/sources.json")
    ap.add_argument("--only", nargs="*", metavar="KEY",
                    help="with --sync, rebuild only these book keys")
    ap.add_argument("--deck", help="one presentation URL or id")
    ap.add_argument("--title")
    ap.add_argument("--num", type=int)
    ap.add_argument("--key", help="slug override, e.g. house-of-chains")
    a = ap.parse_args()

    if a.deck:
        if not (a.title and a.num):
            sys.exit("--deck also needs --title and --num")
        if build_one(extract_id(a.deck), a.title, a.num, a.key):
            v = G.bump_cache_version()
            if v:
                print(f"\nsw.js cache is now malazan-v{v}. Re-upload the folder.")
        return
    if a.folder and a.list:
        return cmd_list(a.folder)
    if a.sync:
        return cmd_sync(set(a.only or []))
    ap.print_help()


if __name__ == "__main__":
    main()
