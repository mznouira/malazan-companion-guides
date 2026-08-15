# Malazan Companion Guides — phone reader

A mobile-first, installable reader for u/sleepinxonxbed's chapter-by-chapter
companion guides to *The Malazan Book of the Fallen*.

**Live:** https://mznouira.github.io/malazan-companion-guides/

- One chapter per screen, large readable type, night and day themes
- Tap any highlighted name to see every scene it appears in
- Full-text search across the whole book
- Remembers your place per book; chapters tick off as you finish them
- Installs to your home screen and works with no signal

Guides written by **u/sleepinxonxbed** and used with permission — see
[CREDITS.md](CREDITS.md). Read a chapter here only *after* you've read it in
the novel.

---


```
index.html              the whole app (UI + logic, one file)
sw.js                   offline cache — bump CACHE_VERSION when you change files
manifest.webmanifest    makes it installable on Android/iOS
icons/                  app icons
books/index.json        the book list — the only file you edit by hand
books/<n>-<id>.json     one file per book: chapters, scenes, names
assets/<id>/            that book's artwork
tools/guide_lib.py      the parser — shared by both tools below
tools/add-book.py       a guide PDF on disk  -> book files
tools/sync-drive.py     the author's Google Slides -> book files
```

## Publishing

Any static host works. The whole folder is ~6 MB.

- **Netlify** — drag this folder onto app.netlify.com/drop
- **Cloudflare Pages** — same idea, "Direct Upload"
- **GitHub Pages** — push the folder, enable Pages on the branch (`.nojekyll` is already here)

It must be served over **https** (or `localhost`). The service worker and the
saved reading progress both refuse to run on `file://` — that's why opening the
HTML straight off the phone's storage doesn't stick.

## Installing on the phone

Open the URL in Chrome → menu ⋮ → **Installer l'application** / *Install app*.
You get a real icon, fullscreen, and it works with no signal after the first visit.

## Adding a book

The tools need `pymupdf` and `pillow`. Install them with
[pipx](https://pipx.pypa.io/) so they stay isolated from the system Python
(plain `pip install` is blocked on Debian/Ubuntu):

```bash
sudo apt install pipx    # macOS: brew install pipx
pipx ensurepath

pipx install pymupdf
pipx inject pymupdf pillow
```

`ensurepath` may ask you to open a new terminal. Then point `$PY` at the
pipx environment's Python — the system `python3` will not see these
packages. `pipx environment` finds the venv on Chromebook (`~/.local/pipx`)
and on machines that use `~/.local/share/pipx`:

```bash
PY="$(pipx environment --value PIPX_LOCAL_VENVS)/pymupdf/bin/python"
```

### From the author's Drive folder (preferred)

The guides are Google Slides. Google exports any link-shared presentation as PDF
with no API key and no login, so the tool pulls the deck itself:

```bash
# 1. list the shared folder into books/sources.json
$PY tools/sync-drive.py --folder "<folder url>" --list

# 2. check the numbering it guessed, then build everything
$PY tools/sync-drive.py --sync
```

`--list` reads Google's folder page, which is undocumented markup and may stop
working. If it comes back empty, open the folder in a browser, copy each deck's
URL, and either write `books/sources.json` yourself (the tool prints the format)
or skip it entirely:

```bash
$PY tools/sync-drive.py --deck "<presentation url>" \
        --title "House of Chains" --num 4
```

Re-run any deck later to pick up the author's revisions:

```bash
$PY tools/sync-drive.py --sync --only house-of-chains
```

### From a PDF on disk

```bash
$PY tools/add-book.py "4. House of Chains Guide.pdf"
```

Title and reading-order number come from the filename; override with
`--title` / `--num`.

### Either way

Both write `books/<num>-<slug>.json` plus `assets/<slug>/`, update
`books/index.json`, and bump `CACHE_VERSION` in `sw.js` so installed phones
refresh. Then re-upload the folder.

To remove a book, delete its entry from `books/index.json`; the JSON and assets
can stay or go.

## How reading progress works

Per book, in the browser's local storage under `malazan-b<num>`:
current chapter, scroll position, and the list of chapters marked read.
It's per-device — nothing is sent anywhere. Clearing site data resets it.

## Notes on the conversion

`guide_lib.py` reads the deck's text layer, so it
depends on the source formatting:

- Slide titles matching `Chapter N …`, `Prologue`, `Epilogue` become chapters.
  A deck that titles things differently will land everything under one section.
- Red bold text becomes tappable names, orange becomes places, blue becomes
  editor's notes — the same colour code the author used.
- Untitled slides (usually artwork) merge into the scene above them.
- Reference slides laid out in columns reflow into running paragraphs.

Artwork is downscaled to 300 px wide, JPEG quality 55. Change `MAXW` and
`QUALITY` at the top of `guide_lib.py` if you want sharper or smaller.

The author's set runs to eight decks — Gardens of the Moon (v2), Deadhouse
Gates, Memories of Ice, House of Chains, Midnight Tides, Night of Knives,
The Bonehunters, Reaper's Gale — so expect the site to grow to roughly 15 MB
once they're all in.
