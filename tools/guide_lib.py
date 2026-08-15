"""
guide_lib - shared parsing core for the Malazan companion-guide site.

Turns one companion-guide deck (as a PDF) into:
  books/<num>-<id>.json   chapters, scenes, highlighted names
  assets/<id>/*.jpg       downscaled artwork
and registers it in books/index.json.

Used by tools/add-book.py (local PDF) and tools/sync-drive.py (Google Slides).
"""
import hashlib, html as H, io, json, os, re, sys

try:
    import pymupdf
    from PIL import Image
except ImportError:
    sys.exit("Missing dependencies. Run:  pip install pymupdf pillow")

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BULLETS = "\u25cf\u25cb\u25a0\u25a1\u25aa\u25ab\u2022\u25c6\u2756\u2023\u2043\u25b8"

# Artwork: width in px, JPEG quality. Raise for sharper plates and a bigger site.
MAXW, QUALITY = 300, 55




def cclass(c):
    if c == 0: return None
    r, g, b = (c >> 16) & 255, (c >> 8) & 255, c & 255
    if r > 150 and g < 110 and b < 110: return "nm"
    if r > 200 and 110 <= g < 205 and b < 120: return "pl"
    if b > 150 and r < 150: return "nt"
    if max(r, g, b) - min(r, g, b) < 35: return "mu"
    return "ac"


def esc(t):
    return t.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def line_html(spans):
    out = []
    for s in spans:
        t = esc(s["text"])
        if not t.strip():
            out.append(t); continue
        f = s["font"]
        bold = "Bold" in f
        ital = "Italic" in f or "Oblique" in f
        cl = cclass(s["color"])
        cls = []
        if cl: cls.append(cl)
        if bold and not cl: cls.append("bd")
        if ital: cls.append("it")
        if cls:
            t = f'<span class="{" ".join(cls)}">{t}</span>'
        out.append(t)
    return "".join(out)


def process(key, title, num, path):
    doc = pymupdf.open(path)
    imgdir = f"img/{key}"
    os.makedirs(imgdir, exist_ok=True)
    seen = {}
    xref_pages = {}
    for pno in range(len(doc)):
        for info in doc[pno].get_images(full=True):
            xref_pages.setdefault(info[0], set()).add(pno)

    slides = []
    for pno in range(len(doc)):
        page = doc[pno]
        d = page.get_text("dict")
        items, heading, hsize = [], None, 0

        for b in d["blocks"]:
            if b["type"] != 0: continue
            pending = None
            prev_y = None
            for l in b["lines"]:
                spans = [s for s in l["spans"] if s["text"] != ""]
                if not spans: continue
                raw = "".join(s["text"] for s in spans)
                if not raw.strip():
                    prev_y = None; continue
                x0 = min(s["bbox"][0] for s in spans)
                y0 = min(s["bbox"][1] for s in spans)
                size = max(s["size"] for s in spans)
                stripped = raw.strip()

                # bullet-only line
                if all(ch in BULLETS or ch.isspace() for ch in stripped):
                    pending = 0 if x0 < 52 else (1 if x0 < 82 else 2)
                    continue

                # inline bullet at line start
                if stripped[0] in BULLETS:
                    pending = 0 if x0 < 52 else (1 if x0 < 82 else 2)
                    spans = spans[1:]
                    while spans and spans[0]["text"].strip() == "": spans = spans[1:]
                    if not spans:
                        continue
                    x0 = min(s["bbox"][0] for s in spans)

                if size >= 17:
                    txt = "".join(s["text"] for s in spans).strip()
                    if y0 < 96 and (heading is None or size >= hsize):
                        heading = txt if heading is None else heading + " " + txt
                        hsize = max(hsize, size)
                    else:
                        items.append({"t": "h", "html": line_html(spans)})
                    prev_y = y0
                    continue

                html = line_html(spans).strip()
                ital = any("Italic" in s["font"] for s in spans)
                close = prev_y is not None and (y0 - prev_y) < size * 1.9

                if pending is not None:
                    items.append({"t": "li", "l": pending, "html": html})
                    pending = None
                elif items and close and x0 > 44 and items[-1]["t"] == "li":
                    items[-1]["html"] += " " + html
                elif items and close and items[-1]["t"] in ("q", "p") and \
                        ((items[-1]["t"] == "q") == ital):
                    items[-1]["html"] += " " + html
                else:
                    items.append({"t": "q" if ital else "p", "html": html})
                prev_y = y0

        imgs = []
        for info in page.get_images(full=True):
            xref = info[0]
            if len(xref_pages.get(xref, ())) > 3: continue
            try: rects = page.get_image_rects(xref)
            except Exception: rects = []
            dw = max([r.width for r in rects], default=0)
            dh = max([r.height for r in rects], default=0)
            if dw < 60 or dh < 60: continue
            try: base = doc.extract_image(xref)
            except Exception: continue
            data = base["image"]
            h = hashlib.md5(data).hexdigest()[:12]
            if h not in seen:
                try: im = Image.open(io.BytesIO(data)).convert("RGB")
                except Exception: continue
                if im.width < 120 or im.height < 120: continue
                if im.width > MAXW:
                    im = im.resize((MAXW, int(im.height * MAXW / im.width)), Image.LANCZOS)
                fn = f"{imgdir}/{h}.jpg"
                im.save(fn, "JPEG", quality=QUALITY, optimize=True, progressive=True)
                seen[h] = fn
            imgs.append({"f": seen[h], "r": round(dw / dh, 3)})

        if not items and not imgs and not heading: continue
        slides.append({"p": pno + 1, "t": heading, "i": items, "g": imgs})

    json.dump({"key": key, "title": title, "num": num, "slides": slides},
              open(f"{key}.json", "w"), ensure_ascii=False)
    print(key, len(slides), "slides |", len(seen), "imgs |",
          round(sum(os.path.getsize(f) for f in set(seen.values())) / 1e6, 2), "MB")



CH = re.compile(r'^\s*Chapter\s+(\d+)\b', re.I)
PRO = re.compile(r'^\s*Prologue\b', re.I)
EPI = re.compile(r'^\s*Epilogue\b', re.I)
FRONT_STOP = re.compile(r'^\s*(Prologue|Chapter\s+\d+)\b', re.I)


def strip_tags(s):
    return re.sub(r'<[^>]+>', '', s)


def build_sections(slides):
    secs = []
    cur = None

    def newsec(kind, key, label):
        nonlocal cur
        cur = {"kind": kind, "key": key, "label": label, "cards": []}
        secs.append(cur)

    newsec("front", "front", "Before you start")
    for s in slides:
        t = (s["t"] or "").strip()
        m = CH.match(t)
        if m:
            k = "c" + m.group(1)
            if not cur or cur["key"] != k:
                newsec("chapter", k, "Chapter " + m.group(1))
            head = t[m.end():].strip(" -–—:")
        elif PRO.match(t):
            if not cur or cur["key"] != "pro":
                newsec("chapter", "pro", "Prologue")
            head = t[len("Prologue"):].strip(" -–—:")
        elif EPI.match(t):
            if not cur or cur["key"] != "epi":
                newsec("chapter", "epi", "Epilogue")
            head = t[len("Epilogue"):].strip(" -–—:")
        else:
            head = t

        merge = (not t) and cur["cards"]
        if merge:
            c = cur["cards"][-1]
            c["i"] += s["i"]
            c["g"] += s["g"]
            c["p2"] = s["p"]
        else:
            cur["cards"].append({"h": head, "i": list(s["i"]), "g": list(s["g"]),
                                 "p": s["p"], "p2": s["p"]})
    return [s for s in secs if s["cards"]]


def collect_names(secs):
    idx = {}
    for si, sec in enumerate(secs):
        for ci, card in enumerate(sec["cards"]):
            for it in card["i"]:
                for mt in re.finditer(r'<span class="[^"]*\bnm\b[^"]*">(.*?)</span>', it["html"]):
                    n = H.unescape(strip_tags(mt.group(1))).strip()
                    n = re.sub(r'\s+', ' ', n).strip(" ,.;:’'\"()[]—-")
                    if len(n) < 3 or len(n) > 42: continue
                    if n.lower() in ("note", "the", "and"): continue
                    key = n.lower()
                    e = idx.setdefault(key, {"n": n, "hits": []})
                    if not e["hits"] or e["hits"][-1] != [si, ci]:
                        e["hits"].append([si, ci])
    out = []
    for k, v in idx.items():
        if len(v["hits"]) >= 1:
            out.append({"n": v["n"], "h": v["hits"][:80]})
    out.sort(key=lambda x: (-len(x["h"]), x["n"].lower()))
    return out[:400]




# ---------------------------------------------------------------- naming

def slugify(s):
    return re.sub(r'[^a-z0-9]+', '-', s.lower()).strip('-')


def parse_deck_name(name):
    """'1. Gardens of the Moon Guide v2' -> (1, 'Gardens of the Moon').

    Returns (num_or_None, clean_title): strips the leading reading-order
    number and the trailing 'Guide' / 'Companion Guide' / 'v2' noise.
    """
    name = re.sub(r'\.(pdf|pptx)$', '', name.strip(), flags=re.I)
    num = None
    m = re.match(r'^\s*(\d+)\s*[.\)\-_]+\s*(.*)$', name)
    if m:
        num, name = int(m.group(1)), m.group(2)
    name = re.sub(r'\s*[-_]?\s*(companion\s+)?guide\b', '', name, flags=re.I)
    name = re.sub(r'\s*\bv\d+\b', '', name, flags=re.I)
    name = re.sub(r'[\s_]+', ' ', name).strip(' -_')
    return num, name


# ---------------------------------------------------------------- install

def install(pdf_path, title, num, key=None, root=ROOT, quiet=False):
    """Parse a guide PDF and wire it into the site. Returns the index entry."""
    key = key or slugify(title)
    cwd = os.getcwd()
    os.chdir(root)
    try:
        os.makedirs("books", exist_ok=True)
        process(key, title, num, pdf_path)          # -> <key>.json + img/<key>/

        d = json.load(open(f"{key}.json"))
        secs = build_sections(d["slides"])
        names = collect_names(secs)

        dst = os.path.join("assets", key)
        os.makedirs(dst, exist_ok=True)
        for s in secs:
            for c in s["cards"]:
                ng = []
                for g in c["g"]:
                    fn = os.path.basename(g["f"])
                    target = os.path.join(dst, fn)
                    if not os.path.exists(target):
                        os.replace(g["f"], target)
                    ng.append({"f": f"assets/{key}/{fn}", "r": g["r"]})
                c["g"] = ng
                c.pop("p2", None)

        out = f"books/{num}-{key}.json"
        json.dump({"id": key, "title": title, "num": num, "secs": secs, "names": names},
                  open(out, "w"), ensure_ascii=False, separators=(",", ":"))

        entry = {"id": key, "num": num, "title": title,
                 "file": out, "chapters": len(secs)}
        register(entry, root=".")

        os.remove(f"{key}.json")
        for leftover in (f"img/{key}", "img"):
            if os.path.isdir(leftover) and not os.listdir(leftover):
                os.rmdir(leftover)

        if not quiet:
            labels = [s["label"] for s in secs]
            print(f"  {len(secs)} sections: {labels[0]} ... {labels[-1]}")
            print(f"  {len(names)} highlighted names, {len(os.listdir(dst))} images")
            if len(secs) < 5:
                print("  ! Few sections found - this deck may title its slides "
                      "differently. Open " + out + " and check.")
        return entry
    finally:
        os.chdir(cwd)


def register(entry, root=ROOT):
    path = os.path.join(root, "books", "index.json")
    idx = json.load(open(path)) if os.path.exists(path) else []
    idx = [b for b in idx if b["id"] != entry["id"]]
    idx.append(entry)
    idx.sort(key=lambda b: b["num"])
    json.dump(idx, open(path, "w"), ensure_ascii=False, indent=2)
    return idx


def bump_cache_version(root=ROOT):
    """sw.js: malazan-v3 -> malazan-v4, so installed phones pick up changes."""
    p = os.path.join(root, "sw.js")
    if not os.path.exists(p):
        return None
    src = open(p).read()
    m = re.search(r"CACHE_VERSION\s*=\s*'malazan-v(\d+)'", src)
    if not m:
        return None
    new = int(m.group(1)) + 1
    open(p, "w").write(src.replace(m.group(0), f"CACHE_VERSION = 'malazan-v{new}'"))
    return new
