"""
hreflang_auditor.cli
----------------------
Command-line interface.

Examples:
    hreflang-auditor audit https://example.com
    hreflang-auditor audit https://example.com --deep
    hreflang-auditor audit https://example.com --format markdown --output report.md
    hreflang-auditor sitemap https://example.com/sitemap.xml --limit 50
"""
from __future__ import annotations

import argparse
import sys

from . import core, report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="hreflang-auditor",
        description="Audit hreflang annotations for International SEO issues.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    audit_p = sub.add_parser("audit", help="Audit a single URL.")
    audit_p.add_argument("url", help="Page URL to audit.")
    audit_p.add_argument("--deep", action="store_true",
                          help="Also fetch each alternate URL to verify return tags "
                               "(reciprocity check). Slower, more thorough.")
    audit_p.add_argument("--format", choices=["console", "json", "markdown"],
                          default="console")
    audit_p.add_argument("--output", help="Write report to this file instead of stdout.")
    audit_p.add_argument("--timeout", type=int, default=core.DEFAULT_TIMEOUT)

    sitemap_p = sub.add_parser("sitemap", help="Audit every URL listed in a sitemap.xml "
                                                 "that carries xhtml:link hreflang annotations.")
    sitemap_p.add_argument("url", help="Sitemap XML URL.")
    sitemap_p.add_argument("--deep", action="store_true")
    sitemap_p.add_argument("--format", choices=["console", "json", "markdown"],
                            default="console")
    sitemap_p.add_argument("--output", help="Write report to this file instead of stdout.")
    sitemap_p.add_argument("--timeout", type=int, default=core.DEFAULT_TIMEOUT)
    sitemap_p.add_argument("--limit", type=int, default=None,
                            help="Only audit the first N URLs (useful for large sitemaps).")
    sitemap_p.add_argument("--delay", type=float, default=0.0,
                            help="Seconds to wait between requests in --deep mode "
                                 "(be polite to the target server).")

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "audit":
        audit = core.audit_url(args.url, deep=args.deep, timeout=args.timeout)
        audits = [audit]
    elif args.command == "sitemap":
        try:
            audits = core.audit_sitemap(
                args.url, deep=args.deep, timeout=args.timeout,
                delay=getattr(args, "delay", 0.0), limit=args.limit,
            )
        except Exception as exc:  # noqa: BLE001 - surface a clean CLI error
            print(f"Failed to process sitemap: {exc}", file=sys.stderr)
            return 1
        if not audits:
            print("No URLs with hreflang annotations found in sitemap.", file=sys.stderr)
            return 1
    else:
        parser.print_help()
        return 1

    formatter = report.FORMATTERS[args.format]
    output = formatter(audits)

    if args.output:
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)
        print(f"Report written to {args.output}")
    else:
        print(output)

    total_errors = sum(a.error_count for a in audits)
    return 1 if total_errors else 0


if __name__ == "__main__":
    sys.exit(main())
