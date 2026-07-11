"""
hreflang_auditor.report
------------------------
Formats PageAudit results as console output, JSON, or a client-ready
Markdown report.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

SEVERITY_ICON = {"error": "\u2716", "warning": "\u26a0", "info": "\u2139"}

try:
    from colorama import Fore, Style, init as colorama_init
    colorama_init()
    _COLOR = {"error": Fore.RED, "warning": Fore.YELLOW, "info": Fore.CYAN}
    _RESET = Style.RESET_ALL
except ImportError:  # colorama is optional; degrade gracefully
    _COLOR = {"error": "", "warning": "", "info": ""}
    _RESET = ""


def to_console(audits: list) -> str:
    lines = []
    total_errors = sum(a.error_count for a in audits)
    total_warnings = sum(a.warning_count for a in audits)

    for audit in audits:
        lines.append(f"\n{Style.BRIGHT if _RESET else ''}{audit.url}{_RESET}")
        if not audit.issues:
            lines.append(f"  {_COLOR['info']}\u2713 No issues found ({len(audit.tags)} hreflang tags){_RESET}")
            continue
        for issue in audit.issues:
            icon = SEVERITY_ICON.get(issue.severity, "-")
            color = _COLOR.get(issue.severity, "")
            lines.append(f"  {color}{icon} [{issue.severity.upper()}] {issue.message}{_RESET}")

    lines.append("")
    lines.append(f"Summary: {len(audits)} page(s) audited | "
                 f"{total_errors} error(s) | {total_warnings} warning(s)")
    return "\n".join(lines)


def to_json(audits: list) -> str:
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "pages_audited": len(audits),
        "results": [],
    }
    for audit in audits:
        payload["results"].append({
            "url": audit.url,
            "fetch_error": audit.fetch_error,
            "hreflang_tags": [
                {"hreflang": t.hreflang, "href": t.href} for t in audit.tags
            ],
            "issues": [
                {"severity": i.severity, "code": i.code, "message": i.message, "url": i.url}
                for i in audit.issues
            ],
            "error_count": audit.error_count,
            "warning_count": audit.warning_count,
        })
    return json.dumps(payload, indent=2)


def to_markdown(audits: list, site_label: str = "") -> str:
    total_errors = sum(a.error_count for a in audits)
    total_warnings = sum(a.warning_count for a in audits)
    clean_pages = sum(1 for a in audits if not a.issues)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    lines = [
        f"# Hreflang Audit Report{f' — {site_label}' if site_label else ''}",
        "",
        f"*Generated {now} with hreflang-auditor*",
        "",
        "## Summary",
        "",
        f"- Pages audited: **{len(audits)}**",
        f"- Clean pages: **{clean_pages}**",
        f"- Errors: **{total_errors}**",
        f"- Warnings: **{total_warnings}**",
        "",
        "## Findings",
        "",
    ]

    for audit in audits:
        lines.append(f"### {audit.url}")
        lines.append("")
        if audit.fetch_error:
            lines.append(f"- \u2716 Fetch failed: {audit.fetch_error}")
            lines.append("")
            continue
        lines.append(f"Hreflang tags found: {len(audit.tags)}")
        lines.append("")
        if not audit.issues:
            lines.append("No issues found.")
        else:
            for issue in audit.issues:
                icon = SEVERITY_ICON.get(issue.severity, "-")
                lines.append(f"- {icon} **[{issue.severity.upper()}]** `{issue.code}` — {issue.message}")
        lines.append("")

    lines.append("---")
    lines.append("*Report generated with [hreflang-auditor](https://github.com/) "
                 "— an open-source International SEO diagnostic tool.*")
    return "\n".join(lines)


FORMATTERS = {
    "console": to_console,
    "json": to_json,
    "markdown": to_markdown,
}
