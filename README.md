# hreflang-auditor

A lightweight command-line tool for auditing **hreflang** implementations — built for
International SEO work across multilingual and multi-regional websites.

Most hreflang bugs never throw a visible error. A page can look perfectly fine in the
browser while quietly telling Google to ignore it in favor of a duplicate, or while
"leaking" the wrong language into the wrong market. This tool catches the specific
failure patterns that cause those problems.

## What it checks

| Check | Why it matters |
|---|---|
| **Missing self-reference** | Every page in a hreflang cluster must reference itself. Google [explicitly requires this](https://developers.google.com/search/docs/specialty/international/localized-versions) — omitting it is one of the most common implementation errors. |
| **Missing x-default** | Without a fallback, users outside your targeted locales get inconsistent treatment. |
| **Invalid code format** | Catches malformed values like `english` or `en_US` (underscore instead of hyphen) that silently fail. |
| **Uncommon language subtag** | Soft warning when a code doesn't match common ISO 639-1 values — often a typo. |
| **Conflicting / duplicate values** | Flags when the same hreflang value points to two different URLs — a direct contradiction in the signal. |
| **Broken return tags** (`--deep`) | Hreflang is bidirectional. If page A points to page B but B doesn't point back to A, the annotation is effectively broken. This is the hardest issue to catch by hand and the one this tool is built around. |
| **Unreachable targets** (`--deep`) | Flags alternate URLs that 404 or fail to load. |

## Install

```bash
git clone https://github.com/<your-username>/hreflang-auditor.git
cd hreflang-auditor
pip install -e .
```

Or just install dependencies and run the module directly:

```bash
pip install -r requirements.txt
python -m hreflang_auditor.cli audit https://example.com
```

## Usage

Audit a single page:

```bash
hreflang-auditor audit https://example.com
```

Audit a page **and** verify every alternate URL links back correctly (recommended for real audits):

```bash
hreflang-auditor audit https://example.com --deep
```

Audit every URL in a sitemap that carries `xhtml:link` hreflang annotations:

```bash
hreflang-auditor sitemap https://example.com/sitemap.xml --deep --limit 100 --delay 0.5
```

Export a client-ready Markdown report:

```bash
hreflang-auditor audit https://example.com --deep --format markdown --output report.md
```

Or JSON, for feeding into a dashboard or spreadsheet:

```bash
hreflang-auditor audit https://example.com --format json --output report.json
```

See [`examples/sample_report.md`](examples/sample_report.md) for what a real finding looks like —
in this case, a Mexico (`es-mx`) page that fails to link back to its US counterpart.

## Example output

```
https://example.com/us/
  ⚠ [WARNING] No x-default annotation found. Recommended as a fallback for unmatched languages/regions.
  ✖ [ERROR] https://example.com/mx/ does not link back to https://example.com/us/. The return tag is missing or broken.

Summary: 1 page(s) audited | 1 error(s) | 1 warning(s)
```

## Notes on `--deep` mode

Reciprocity checking fetches every alternate URL, so it's slower and makes real
requests to the target site. Use `--delay` to add spacing between requests and avoid
hammering a server during a large sitemap audit. Static checks (format validity,
self-reference, x-default, duplicates) never require this and run instantly.

## Running the test suite

```bash
pip install -r requirements.txt
pytest tests/ -v
```

## Roadmap / ideas for contributors

- HTTP-header-based hreflang detection (for PDFs and non-HTML resources)
- Canonical + hreflang conflict detection
- CSV export for spreadsheet-based audits
- Concurrent fetching for large sitemaps

## About

Built by [Navas](https://github.com/), International SEO & GEO consultant specializing
in multilingual and multi-search-engine (Google / Baidu / Naver) technical SEO.

## License

MIT — see [LICENSE](LICENSE).
