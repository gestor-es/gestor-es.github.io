"""Build the knowledge-base pages and sitemap.xml from the gestor-es repo.

    python3 tools/build_kb.py [path/to/gestor-es]

Reads kb/*.md (Spanish originals), kb/en/*.md and kb/ru/*.md, renders them with the
GitHub markdown API (`gh api markdown`, needs gh logged in) and writes
kb/<slug>/, es/kb/<slug>/, ru/kb/<slug>/ plus the three kb index pages and sitemap.xml.
"""
import html
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

SITE = "https://gestor-es.github.io"
REPO = "https://github.com/gestor-es/gestor-es/blob/main"
OUT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1] if len(sys.argv) > 1 else OUT.parent / "gestor-es").resolve()
LANGS = {"en": ("kb/en", "/"), "es": ("kb", "/es/"), "ru": ("kb/ru", "/ru/")}  # md dir, site prefix
SLUGS = ["iva-facturacion", "irpf-autonomo", "beckham", "reta", "sociedad-limitada", "calendario-presentacion", "visados"]
TITLES = {
    "en": ["IVA and invoicing for autónomos and SLs: rules, casillas and deadlines",
           "IRPF for autónomos in Spain: rules, figures and Modelo 130",
           "Beckham Law (art. 93 LIRPF) for autónomos and SL directors",
           "RETA: social security contributions for autónomos in Spain",
           "Sociedad Limitada with one shareholder-director: taxes and reporting",
           "Spanish tax filing calendar 2026 for autónomos and SLs",
           "Visas, residence, taxes and social security for autónomos in Spain"],
    "es": ["IVA y facturación para autónomos y SL: reglas, casillas y plazos",
           "IRPF del autónomo: reglas, cifras y modelo 130",
           "Ley Beckham (art. 93 LIRPF) para autónomos y administradores de SL",
           "RETA: cotización de autónomos en España",
           "Sociedad Limitada con socio único administrador: impuestos y obligaciones",
           "Calendario fiscal 2026 para autónomos y SL",
           "Visados, residencia, impuestos y Seguridad Social del autónomo"],
    "ru": ["IVA и счета для autónomo и SL: правила, casillas и сроки",
           "IRPF для autónomo в Испании: правила, цифры и модель 130",
           "Закон Бекхэма (art. 93 LIRPF) для autónomo и администратора SL",
           "RETA: взносы autónomo в Испании",
           "Sociedad Limitada с одним участником-администратором: налоги и отчётность",
           "Налоговый календарь Испании 2026 для autónomo и SL",
           "Визы, резиденция, налоги и соцстрах для autónomo в Испании"],
}
UI = {
    "en": {"kb": "Knowledge base", "home": "gestor", "lead": "Rules, figures and deadlines for autónomos and SLs in Spain, with the law quoted from BOE, AEAT, DGT and TGSS. gestor computes with these rules.",
           "note": "Reference, not tax advice. Check every figure in the AEAT Sede before you sign.", "src": "Source on GitHub", "nav": "Sections", "lang": "Language",
           "foot": "gestor calculates; you file yourself in the Sede AEAT. Not tax advice."},
    "es": {"kb": "Base de conocimiento", "home": "gestor", "lead": "Reglas, cifras y plazos para autónomos y SL en España, con la norma citada del BOE, la AEAT, la DGT y la TGSS. gestor calcula con estas reglas.",
           "note": "Material de referencia, no es asesoramiento fiscal. Compruebe cada cifra en la Sede de la AEAT antes de firmar.", "src": "Fuente en GitHub", "nav": "Secciones", "lang": "Idioma",
           "foot": "gestor calcula; la presentación la hace usted en la Sede de la AEAT. No es asesoramiento fiscal."},
    "ru": {"kb": "База знаний", "home": "gestor", "lead": "Правила, цифры и сроки для autónomo и SL в Испании, с цитатами закона из BOE, AEAT, DGT и TGSS. gestor считает по этим правилам.",
           "note": "Справочный материал, не налоговая консультация. Проверяйте каждую цифру в Sede AEAT до подписи.", "src": "Исходник на GitHub", "nav": "Разделы", "lang": "Язык",
           "foot": "gestor считает; подаёте вы сами в Sede AEAT. Не налоговая консультация."},
}
LOCALE = {"en": "en_US", "es": "es_ES", "ru": "ru_RU"}
# external guides shown on the kb index pages: (url, language of the guide, title per site language, note per site language)
GUIDES = [
    ("https://spain.denyamsk.com/digital-nomad-residence-in-spain-2026-97dfbe479af04e8b94d269f07bf7e0a2", "ru",
     {"en": "Digital nomad residence in Spain 2026", "es": "Residencia de nómada digital en España 2026", "ru": "ВНЖ цифрового кочевника в Испании 2026"},
     {"en": "Conditions, timeline for applying from Spain or at a consulate, document checklist. In Russian.",
      "es": "Requisitos, plazos de la solicitud desde España o en el consulado, lista de documentos. En ruso.",
      "ru": "Условия, таймлайн подачи из Испании и через консульство, чеклист документов."}),
    ("https://spain.denyamsk.com/spanish-startup-residence-permit-2026-rus-edition-188230bbb2ce48d7823ce96b15391606", "ru",
     {"en": "Spanish startup residence permit 2026", "es": "Residencia para emprendedores (startup) en España 2026", "ru": "Стартап-ВНЖ в Испании 2026"},
     {"en": "Documents, UGE and ENISA application, business plan template, procedure and timeline. In Russian.",
      "es": "Documentos, solicitud a la UGE y ENISA, plantilla de plan de negocio, procedimiento y plazos. En ruso.",
      "ru": "Документы, подача в UGE и ENISA, шаблон бизнес-плана, процедура и таймлайн."}),
]
GUIDES_TITLE = {"en": "Guides", "es": "Guías", "ru": "Гайды"}


def render(md: str) -> str:
    out = subprocess.run(["gh", "api", "markdown", "--input", "-"], input=json.dumps({"mode": "gfm", "text": md}),
                         capture_output=True, text=True, check=True).stdout
    return re.sub(r"</?markdown-accessiblity-table>", "", out)


def page_url(lang: str, slug: str = "") -> str:
    return f"{LANGS[lang][1]}kb/" + (f"{slug}/" if slug else "")


def fix_links(md: str, md_dir: str) -> str:
    """Point links between kb files at the site pages, everything else relative at GitHub."""
    def repl(m):
        target = m.group(2)
        if re.match(r"^[a-z]+:|^#", target):
            return m.group(0)
        path, _, frag = target.partition("#")
        full = posixpath.normpath(posixpath.join(md_dir, path))
        d, name = posixpath.split(full)
        slug = name[:-3] if name.endswith(".md") else None
        lang = next((l for l, (dd, _) in LANGS.items() if dd == d), None)
        if slug in SLUGS and lang:
            url = page_url(lang, slug)
        else:
            url = f"{REPO}/{full}"
        return f"{m.group(1)}({url}{'#' + frag if frag else ''})"
    return re.sub(r"(\]\s*)\(([^)\s]+)\)", repl, md)


def slugify(text: str) -> str:
    return re.sub(r"[^\w]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")


def plain(md: str) -> str:
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", md)
    s = re.sub(r"[*_`]+", "", s)
    return re.sub(r"\s+", " ", s).strip()


def describe(md: str) -> str:
    first = re.search(r"^## .*?\n+\s*[-*] (.+?)(?=\n\s*[-*] |\n\n)", md, re.S | re.M)
    text = plain(first.group(1)) if first else ""
    return text if len(text) <= 158 else text[:157].rsplit(" ", 1)[0] + "…"


def alternates(slug: str = "") -> str:
    links = "".join(f'<link rel="alternate" hreflang="{l}" href="{SITE}{page_url(l, slug)}">\n' for l in LANGS)
    return links + f'<link rel="alternate" hreflang="x-default" href="{SITE}{page_url("en", slug)}">\n'


def shell(lang, slug, title, desc, body, ld) -> str:
    ui = UI[lang]
    url = SITE + page_url(lang, slug)
    langs = "".join(f'<a href="{page_url(l, slug)}" lang="{l}" hreflang="{l}"{" aria-current=page" if l == lang else ""}>{l.upper()}</a>' for l in LANGS)
    return f"""<!doctype html>
<html lang="{lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)} · gestor</title>
<meta name="description" content="{html.escape(desc)}">
<link rel="canonical" href="{url}">
{alternates(slug)}<link rel="icon" type="image/png" href="/favicon.png">
<meta property="og:type" content="{'article' if slug else 'website'}">
<meta property="og:site_name" content="gestor">
<meta property="og:locale" content="{LOCALE[lang]}">
<meta property="og:url" content="{url}">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{SITE}/og.png?v=2">
<meta name="twitter:card" content="summary_large_image">
<script type="application/ld+json">
{json.dumps(ld, ensure_ascii=False, indent=1)}
</script>
<link rel="stylesheet" href="/fonts.css">
<link rel="stylesheet" href="/style.css">
</head>
<body>
<div class="wrap">
<header class="appbar">
  <a class="brand" href="{LANGS[lang][1]}">gestor</a>
  <nav aria-label="{ui['nav']}"><a href="{page_url(lang)}"{' aria-current="page"' if not slug else ''}>{ui['kb']}</a></nav>
  <nav class="langs" aria-label="{ui['lang']}">{langs}</nav>
  <a class="gh" href="https://github.com/gestor-es/gestor-es">GitHub</a>
</header>
<main>
{body}
  <div class="foot"><span>{ui['foot']}</span><span><a href="https://github.com/gestor-es/gestor-es">github.com/gestor-es/gestor-es</a> · MIT</span></div>
</main>
</div>
<footer class="colophon wrap" aria-hidden="true"><div class="giant">gestor</div><img src="/img/papel-sellado.jpg" alt="" width="800" height="368"></footer>
<script data-goatcounter="https://gestor.goatcounter.com/count" async src="https://gc.zgo.at/count.js"></script>
</body>
</html>
"""


def breadcrumbs(lang, items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        {"@type": "ListItem", "position": i + 1, "name": n, "item": SITE + u} for i, (n, u) in enumerate(items)]}


def modified(path: Path) -> str:
    return subprocess.run(["git", "-C", str(SRC), "log", "-1", "--format=%cs", "--", str(path.relative_to(SRC))],
                          capture_output=True, text=True, check=True).stdout.strip()


def main():
    pages = []  # (url path group key, lang, url, lastmod)
    for lang, (md_dir, prefix) in LANGS.items():
        ui = UI[lang]
        entries = []
        for i, slug in enumerate(SLUGS):
            src = SRC / md_dir / f"{slug}.md"
            md = src.read_text()
            head, sep, rest = md.partition("\n## ")
            head = re.sub(r"^# .*\n", "", head, flags=re.M)  # the page sets its own h1
            md = fix_links(head + sep + rest, md_dir)
            title, desc, date = TITLES[lang][i], describe(md), modified(src)
            body_html = render(md)
            body_html = re.sub(r"<h2>(.*?)</h2>", lambda m: f'<h2 id="{slugify(m.group(1))}">{m.group(1)}</h2>', body_html)
            src_url = f"{REPO}/{md_dir}/{slug}.md"
            body = (f'  <p class="crumbs"><a href="{prefix}">gestor</a> › <a href="{page_url(lang)}">{ui["kb"]}</a></p>\n'
                    f'  <h1 class="doc-title">{html.escape(title)}</h1>\n'
                    f'  <p class="sub">{ui["note"]} <a href="{src_url}">{ui["src"]}</a></p>\n'
                    f'  <article class="doc">\n{body_html}</article>')
            ld = {"@context": "https://schema.org", "@graph": [
                {"@type": "Article", "headline": title, "description": desc, "inLanguage": lang, "dateModified": date,
                 "url": SITE + page_url(lang, slug), "image": f"{SITE}/og.png", "isBasedOn": src_url,
                 "author": {"@type": "Organization", "name": "gestor-es contributors", "url": "https://github.com/gestor-es"},
                 "publisher": {"@type": "Organization", "name": "gestor-es contributors", "url": "https://github.com/gestor-es"},
                 "about": {"@type": "SoftwareApplication", "@id": f"{SITE}/#app", "name": "gestor"}},
                breadcrumbs(lang, [("gestor", prefix), (ui["kb"], page_url(lang)), (title, page_url(lang, slug))])]}
            out = OUT / page_url(lang, slug).lstrip("/") / "index.html"
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(shell(lang, slug, title, desc, body, ld))
            entries.append((slug, title, desc))
            pages.append((slug, lang, page_url(lang, slug), date))
        items = "\n".join(f'    <li><a class="entry" href="{page_url(lang, s)}">{html.escape(t)}</a><small>{html.escape(d)}</small></li>' for s, t, d in entries)
        body = (f'  <p class="crumbs"><a href="{prefix}">gestor</a></p>\n  <h1 class="doc-title">{ui["kb"]}</h1>\n'
                f'  <p class="lead">{ui["lead"]}</p>\n  <p class="sub">{ui["note"]}</p>\n  <ul class="index kb-list">\n{items}\n  </ul>')
        guides = "\n".join(f'    <li><a class="entry" href="{u}" hreflang="{gl}">{html.escape(t[lang])}</a><small>{html.escape(n[lang])}</small></li>' for u, gl, t, n in GUIDES)
        body += f'\n  <h2>{GUIDES_TITLE[lang]}</h2>\n  <ul class="index kb-list">\n{guides}\n  </ul>'
        ld = {"@context": "https://schema.org", "@graph": [
            {"@type": "CollectionPage", "name": ui["kb"], "inLanguage": lang, "url": SITE + page_url(lang),
             "hasPart": [{"@type": "Article", "headline": t, "url": SITE + page_url(lang, s)} for s, t, _ in entries]},
            breadcrumbs(lang, [("gestor", prefix), (ui["kb"], page_url(lang))])]}
        (OUT / page_url(lang).lstrip("/")).mkdir(parents=True, exist_ok=True)
        (OUT / page_url(lang).lstrip("/") / "index.html").write_text(shell(lang, "", ui["kb"], ui["lead"], body, ld))
        pages.append(("", lang, page_url(lang), max(p[3] for p in pages if p[1] == lang)))

    # sitemap: landing, explainer, kb; every group linked across languages
    groups = {"/": {l: p for l, (_, p) in LANGS.items()}, "explainer": {l: p + "explainer/" for l, (_, p) in LANGS.items()}}
    dates = {"/": "2026-10-13", "explainer": "2026-10-13"}
    for slug, lang, url, date in pages:
        groups.setdefault("kb:" + slug, {})[lang] = url
        dates["kb:" + slug] = max(dates.get("kb:" + slug, ""), date)
    rows = []
    for key, g in groups.items():
        alts = "".join(f'\n    <xhtml:link rel="alternate" hreflang="{l}" href="{SITE}{u}"/>' for l, u in g.items())
        alts += f'\n    <xhtml:link rel="alternate" hreflang="x-default" href="{SITE}{g["en"]}"/>'
        rows += [f"  <url>\n    <loc>{SITE}{u}</loc>\n    <lastmod>{dates[key]}</lastmod>{alts}\n  </url>" for u in g.values()]
    (OUT / "sitemap.xml").write_text('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" '
                                     'xmlns:xhtml="http://www.w3.org/1999/xhtml">\n' + "\n".join(rows) + "\n</urlset>\n")
    print(f"{len(pages)} kb pages, {len(rows)} sitemap urls")


if __name__ == "__main__":
    main()
