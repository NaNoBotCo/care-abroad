"""Link-card tags from og/cards.json, for a site generator.

    import ogcards
    ogcards.copy(ROOT, OUT)                    # og/ -> the built site
    html = ogcards.apply(html, "san/index.html", SITE_URL)   # the page's card tags, if og/cards.json has the page

og/ is drawn by share-cards/sitecards.py and committed with the site.
"""
import html as _h, json, pathlib, re, shutil

_KEYS = r"og:image(?::(?:width|height|alt|type|secure_url|url))?|twitter:image(?::alt)?|twitter:card"
_OLD = re.compile(r'[ \t]*<meta\s+[^>]*(?:property|name)\s*=\s*["\'](?:' + _KEYS + r')["\'][^>]*>[ \t]*\n?', re.I)
_cards = {}


def load(root):
    f = pathlib.Path(root) / "og" / "cards.json"
    _cards.clear()
    if f.is_file():
        _cards.update(json.loads(f.read_text(encoding="utf-8")))
    return _cards


def copy(root, out):
    src = pathlib.Path(root) / "og"
    load(root)
    if src.is_dir():
        shutil.copytree(src, pathlib.Path(out) / "og", dirs_exist_ok=True)


def apply(html, rel, base):
    key = re.sub(r"(^|/)index\.html$", r"\1", rel)
    c = _cards.get(key) or _cards.get(key or "./")
    if not c:
        return html
    i, a = _h.escape(base.rstrip("/") + "/" + c["image"], quote=True), _h.escape(c["alt"], quote=True)
    t = "image/png" if i.lower().endswith(".png") else "image/jpeg"
    block = (f'<meta property="og:image" content="{i}"><meta property="og:image:width" content="1200">'
             f'<meta property="og:image:height" content="630"><meta property="og:image:type" content="{t}">'
             f'<meta property="og:image:alt" content="{a}"><meta name="twitter:card" content="summary_large_image">'
             f'<meta name="twitter:image" content="{i}"><meta name="twitter:image:alt" content="{a}">')
    m = re.search(r"</head\s*>", html, re.I)
    if not m:
        return html
    head = _OLD.sub("", html[: m.start()])
    d = re.search(r'<meta\s+[^>]*property\s*=\s*["\']og:description["\'][^>]*>', head, re.I)
    head = head[: d.end()] + "\n" + block + head[d.end():] if d else head.rstrip() + "\n" + block + "\n"
    return head + html[m.start():]


def apply_tree(out, base):
    """For a generator that writes pages in many places: stamp every page named in cards.json, after the build."""
    out = pathlib.Path(out)
    for key in _cards:
        rel = "index.html" if key == "./" else (key if key.endswith(".html") else key + "index.html")
        f = out / rel
        if f.is_file():
            f.write_text(apply(f.read_text(encoding="utf-8"), rel, base), encoding="utf-8")
