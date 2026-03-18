#!/usr/bin/env python3
"""
Batch download and extract appropriations data from multiple reports.
"""

import os
import sys
import time
import requests

from extract import extract_and_save
from report_finder import (
    KNOWN_REPORTS, get_congress_number, pdf_url, pdf_filename,
    download_pdf, PDF_DIR, HEADERS, DOWNLOAD_DELAY
)

# Reports to process - prioritize variety across subcommittees
BATCH = [
    # FY2026 - all 12 subcommittees (House reports)
    ("FY2026", "Legislative Branch", "house"),
    ("FY2026", "Agriculture", "house"),
    ("FY2026", "Defense", "house"),
    ("FY2026", "Commerce-Justice-Science", "house"),
    ("FY2026", "Energy-Water", "house"),
    ("FY2026", "Homeland Security", "house"),
    ("FY2026", "Interior-Environment", "house"),
    ("FY2026", "Labor-HHS-Education", "house"),
    ("FY2026", "Financial Services", "house"),
    ("FY2026", "Military Construction-VA", "house"),
    ("FY2026", "National Security-State", "house"),
    ("FY2026", "Transportation-HUD", "house"),

    # FY2026 - Senate reports (where available)
    ("FY2026", "Legislative Branch", "senate"),
    ("FY2026", "Agriculture", "senate"),
    ("FY2026", "Defense", "senate"),
    ("FY2026", "Commerce-Justice-Science", "senate"),
    ("FY2026", "Interior-Environment", "senate"),
    ("FY2026", "Labor-HHS-Education", "senate"),
    ("FY2026", "Military Construction-VA", "senate"),
    ("FY2026", "Transportation-HUD", "senate"),

    # FY2025 - all 12 subcommittees (House reports)
    ("FY2025", "Legislative Branch", "house"),
    ("FY2025", "Agriculture", "house"),
    ("FY2025", "Defense", "house"),
    ("FY2025", "Commerce-Justice-Science", "house"),
    ("FY2025", "Energy-Water", "house"),
    ("FY2025", "Homeland Security", "house"),
    ("FY2025", "Interior-Environment", "house"),
    ("FY2025", "Labor-HHS-Education", "house"),
    ("FY2025", "Financial Services", "house"),
    ("FY2025", "Military Construction-VA", "house"),
    ("FY2025", "Transportation-HUD", "house"),

    # FY2025 - Senate reports
    ("FY2025", "Legislative Branch", "senate"),
    ("FY2025", "Agriculture", "senate"),
    ("FY2025", "Defense", "senate"),
]


def get_pdf_path(fiscal_year, subcommittee, source_type):
    """Get the path for a downloaded PDF."""
    reports = KNOWN_REPORTS.get((fiscal_year, subcommittee), {})
    report_num = reports.get(source_type)

    if not report_num:
        return None

    congress = get_congress_number(fiscal_year)
    prefix = "hrpt" if source_type == "house" else "srpt"
    filename = f"CRPT-{congress}{prefix}{report_num}.pdf"
    return os.path.join(PDF_DIR, filename)


def download_report(fiscal_year, subcommittee, source_type):
    """Download a committee report PDF if not already present."""
    reports = KNOWN_REPORTS.get((fiscal_year, subcommittee), {})
    report_num = reports.get(source_type)

    if not report_num:
        print(f"  No known report number for {subcommittee} {fiscal_year} ({source_type})")
        return None

    congress = get_congress_number(fiscal_year)
    filename = pdf_filename(congress, source_type, report_num)
    filepath = os.path.join(PDF_DIR, filename)

    if os.path.exists(filepath):
        print(f"  Already downloaded: {filename}")
        return filepath

    url = pdf_url(congress, source_type, report_num)
    print(f"  Downloading: {url}")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        if resp.status_code == 200:
            os.makedirs(PDF_DIR, exist_ok=True)
            with open(filepath, 'wb') as f:
                f.write(resp.content)
            print(f"  Saved: {filename} ({len(resp.content)} bytes)")
            time.sleep(DOWNLOAD_DELAY)
            return filepath
        else:
            print(f"  HTTP {resp.status_code} for {url}")
            return None
    except Exception as e:
        print(f"  Error downloading: {e}")
        return None


def check_already_extracted(subcommittee, fiscal_year, source_type, data_dir="extracted"):
    """Check if we've already extracted this report."""
    import re
    safe_name = re.sub(r'[^a-z0-9]+', '_', subcommittee.lower()).strip('_')
    filename = f"{safe_name}_{fiscal_year.lower()}_{source_type}.json"
    return os.path.exists(os.path.join(data_dir, filename))


def main():
    """Process all reports in the batch."""
    os.makedirs(PDF_DIR, exist_ok=True)

    # Allow filtering by command line args
    if len(sys.argv) > 1:
        filter_sub = sys.argv[1]
        batch = [(fy, sub, src) for fy, sub, src in BATCH
                 if filter_sub.lower() in sub.lower()]
    else:
        batch = BATCH

    total = len(batch)
    success = 0
    skipped = 0
    failed = 0

    for i, (fiscal_year, subcommittee, source_type) in enumerate(batch):
        print(f"\n[{i+1}/{total}] {subcommittee} {fiscal_year} ({source_type})")

        # Check if already extracted
        if check_already_extracted(subcommittee, fiscal_year, source_type):
            print(f"  Already extracted, skipping.")
            skipped += 1
            continue

        # Download
        pdf_path = download_report(fiscal_year, subcommittee, source_type)
        if not pdf_path:
            failed += 1
            continue

        # Extract
        try:
            result = extract_and_save(pdf_path, subcommittee, fiscal_year, source_type)
            if result:
                success += 1
            else:
                failed += 1
        except Exception as e:
            print(f"  Extraction error: {e}")
            failed += 1

    print(f"\n{'='*60}")
    print(f"Batch complete: {success} extracted, {skipped} skipped, {failed} failed")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
