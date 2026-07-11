from unittest.mock import patch, MagicMock

from hreflang_auditor import core

GOOD_HTML = """
<html><head>
<link rel="alternate" hreflang="en-us" href="https://example.com/us/" />
<link rel="alternate" hreflang="es-es" href="https://example.com/es/" />
<link rel="alternate" hreflang="x-default" href="https://example.com/us/" />
</head><body>US page</body></html>
"""

MISSING_SELF_REF_HTML = """
<html><head>
<link rel="alternate" hreflang="en-us" href="https://example.com/us/" />
<link rel="alternate" hreflang="es-es" href="https://example.com/es/" />
</head><body>fr page with no self-reference</body></html>
"""

BAD_CODE_HTML = """
<html><head>
<link rel="alternate" hreflang="english" href="https://example.com/us/" />
</head></html>
"""

CONFLICTING_HTML = """
<html><head>
<link rel="alternate" hreflang="en-us" href="https://example.com/us/" />
<link rel="alternate" hreflang="en-us" href="https://example.com/us2/" />
</head></html>
"""


def test_extract_hreflang_tags_parses_link_elements():
    tags = core.extract_hreflang_tags(GOOD_HTML, "https://example.com/us/")
    assert len(tags) == 3
    assert tags[0].hreflang == "en-us"
    assert tags[0].href == "https://example.com/us/"


def test_valid_set_has_no_errors():
    tags = core.extract_hreflang_tags(GOOD_HTML, "https://example.com/us/")
    audit = core.validate_tag_set("https://example.com/us/", tags)
    assert audit.error_count == 0


def test_missing_self_reference_flagged():
    tags = core.extract_hreflang_tags(MISSING_SELF_REF_HTML, "https://example.com/fr/")
    audit = core.validate_tag_set("https://example.com/fr/", tags)
    codes = [i.code for i in audit.issues]
    assert "missing_self_reference" in codes


def test_missing_x_default_flagged_as_warning():
    tags = core.extract_hreflang_tags(MISSING_SELF_REF_HTML, "https://example.com/es/")
    audit = core.validate_tag_set("https://example.com/es/", tags)
    warning_codes = [i.code for i in audit.issues if i.severity == "warning"]
    assert "missing_x_default" in warning_codes


def test_invalid_code_format_flagged():
    tags = core.extract_hreflang_tags(BAD_CODE_HTML, "https://example.com/us/")
    audit = core.validate_tag_set("https://example.com/us/", tags)
    codes = [i.code for i in audit.issues]
    assert "invalid_code_format" in codes


def test_duplicate_conflicting_hreflang_flagged():
    tags = core.extract_hreflang_tags(CONFLICTING_HTML, "https://example.com/us/")
    audit = core.validate_tag_set("https://example.com/us/", tags)
    codes = [i.code for i in audit.issues]
    assert "duplicate_hreflang_value" in codes


def test_no_tags_produces_info_warning():
    audit = core.validate_tag_set("https://example.com/", [])
    assert audit.issues[0].code == "no_hreflang_tags"


def test_sitemap_parsing():
    xml = """<?xml version="1.0"?>
    <urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"
            xmlns:xhtml="http://www.w3.org/1999/xhtml">
      <url>
        <loc>https://example.com/us/</loc>
        <xhtml:link rel="alternate" hreflang="en-us" href="https://example.com/us/"/>
        <xhtml:link rel="alternate" hreflang="es-es" href="https://example.com/es/"/>
      </url>
    </urlset>"""
    result = core.extract_sitemap_hreflang(xml)
    assert "https://example.com/us/" in result
    assert len(result["https://example.com/us/"]) == 2


@patch("hreflang_auditor.core.fetch")
def test_check_reciprocity_flags_broken_return_tag(mock_fetch):
    origin = "https://example.com/us/"
    tags = [
        core.HreflangTag("en-us", origin, origin),
        core.HreflangTag("es-es", "https://example.com/es/", origin),
    ]
    audit = core.PageAudit(url=origin, tags=tags)

    # The Spanish page does NOT link back to the US page -> broken reciprocity
    resp = MagicMock()
    resp.status_code = 200
    resp.text = '<link rel="alternate" hreflang="es-es" href="https://example.com/es/">'
    mock_fetch.return_value = resp

    core.check_reciprocity(audit)
    codes = [i.code for i in audit.issues]
    assert "non_reciprocal_tag" in codes


@patch("hreflang_auditor.core.fetch")
def test_check_reciprocity_passes_when_return_tag_present(mock_fetch):
    origin = "https://example.com/us/"
    target = "https://example.com/es/"
    tags = [
        core.HreflangTag("en-us", origin, origin),
        core.HreflangTag("es-es", target, origin),
    ]
    audit = core.PageAudit(url=origin, tags=tags)

    resp = MagicMock()
    resp.status_code = 200
    resp.text = (
        f'<link rel="alternate" hreflang="es-es" href="{target}">'
        f'<link rel="alternate" hreflang="en-us" href="{origin}">'
    )
    mock_fetch.return_value = resp

    core.check_reciprocity(audit)
    codes = [i.code for i in audit.issues]
    assert "non_reciprocal_tag" not in codes
