#!/usr/bin/env python3
"""
Appropriations Committee Report Finder & Downloader

Discovers and downloads Congressional appropriations committee report PDFs
from congress.gov. Supports both hardcoded known report numbers and API-based
discovery via the congress.gov API.
"""

import os
import time
import requests

# congress.gov API key
CONGRESS_API_KEY = "REDACTED"

# Standard User-Agent for congress.gov requests
HEADERS = {
    "User-Agent": "AppropriationsLineItems/1.0 (Congressional Research Tool)"
}

# PDF output directory (relative to this script)
PDF_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pdfs")

# Delay between downloads in seconds
DOWNLOAD_DELAY = 2

# ---------------------------------------------------------------------------
# Appropriations subcommittees and known report numbers
# ---------------------------------------------------------------------------

SUBCOMMITTEES = [
    "Agriculture",
    "Commerce-Justice-Science",
    "Defense",
    "Energy-Water",
    "Financial Services",
    "Homeland Security",
    "Interior-Environment",
    "Labor-HHS-Education",
    "Legislative Branch",
    "Military Construction-VA",
    "National Security-State",
    "Transportation-HUD",
]

# Known report numbers keyed by (fiscal_year, subcommittee).
# Values are dicts with optional "house" and "senate" entries,
# each storing the numeric report number (e.g. 172 for H.Rept. 119-172).
KNOWN_REPORTS = {
    # ----- FY2026 (119th Congress) -----
    ("FY2026", "Agriculture"):                {"house": 172, "senate": 37},
    ("FY2026", "Commerce-Justice-Science"):    {"house": 272, "senate": 44},
    ("FY2026", "Defense"):                     {"house": 162, "senate": 52},
    ("FY2026", "Energy-Water"):                {"house": 213},
    ("FY2026", "Financial Services"):          {"house": 236},
    ("FY2026", "Homeland Security"):           {"house": 173},
    ("FY2026", "Interior-Environment"):        {"house": 215, "senate": 46},
    ("FY2026", "Labor-HHS-Education"):         {"house": 271, "senate": 55},
    ("FY2026", "Legislative Branch"):          {"house": 178, "senate": 38},
    ("FY2026", "Military Construction-VA"):    {"house": 161, "senate": 43},
    ("FY2026", "National Security-State"):     {"house": 217},
    ("FY2026", "Transportation-HUD"):          {"house": 212, "senate": 47},
    # ----- FY2025 (118th Congress) -----
    ("FY2025", "Agriculture"):                {"house": 583, "senate": 193},
    ("FY2025", "Commerce-Justice-Science"):    {"house": 582, "senate": 198},
    ("FY2025", "Defense"):                     {"house": 557, "senate": 204},
    ("FY2025", "Energy-Water"):                {"house": 580, "senate": 205},
    ("FY2025", "Financial Services"):          {"house": 556, "senate": 206},
    ("FY2025", "Homeland Security"):           {"house": 553, "senate": 201},
    ("FY2025", "Interior-Environment"):        {"house": 581, "senate": 201},
    ("FY2025", "Labor-HHS-Education"):         {"house": 585, "senate": 207},
    ("FY2025", "Legislative Branch"):          {"house": 555, "senate": 192},
    ("FY2025", "Military Construction-VA"):    {"house": 528, "senate": 191},
    ("FY2025", "Transportation-HUD"):          {"house": 543, "senate": 199},
    # ----- FY2024 (118th Congress) -----
    ("FY2024", "Agriculture"):                {"house": 124, "senate": 44},
    ("FY2024", "Commerce-Justice-Science"):    {"house": 121, "senate": 62},
    ("FY2024", "Defense"):                     {"house": 120, "senate": 81},
    ("FY2024", "Energy-Water"):                {"house": 126, "senate": 72},
    ("FY2024", "Financial Services"):          {"house": 145, "senate": 61},
    ("FY2024", "Homeland Security"):           {"house": 123, "senate": 85},
    ("FY2024", "Interior-Environment"):        {"house": 155, "senate": 83},
    ("FY2024", "Labor-HHS-Education"):         {"house": 122, "senate": 84},
    ("FY2024", "Legislative Branch"):          {"house": 124, "senate": 44},
    ("FY2024", "Military Construction-VA"):    {"house": 122, "senate": 43},
    ("FY2024", "Transportation-HUD"):          {"house": 154, "senate": 70},
}

# Map fiscal year to congress number
FY_TO_CONGRESS = {
    "FY2024": 118,
    "FY2025": 118,
    "FY2026": 119,
}


def get_congress_number(fiscal_year):
    """Return the congress number for a given fiscal year string like 'FY2026'."""
    if fiscal_year in FY_TO_CONGRESS:
        return FY_TO_CONGRESS[fiscal_year]
    # Derive from the year: congress = (year - 1) // 2 - 894
    # e.g. FY2026 -> year 2026 -> congress = (2025)//2 - 894 = 1012 - 894 = 118... actually
    # The 119th congress covers 2025-2026, so FY2026 bills originate in the 119th.
    # Formula: congress = (calendar_year_of_session - 1789) // 2 + 1
    # But for FY mapping: FY year N is handled by the congress in session when the bill passes,
    # which is typically the congress starting Jan of year N-1.
    year = int(fiscal_year.replace("FY", ""))
    # Congress starting in Jan of (year-1): congress = (year - 1 - 1789) // 2 + 1
    return (year - 1 - 1789) // 2 + 1


def pdf_url(congress, chamber, report_number):
    """
    Build the congress.gov PDF URL for a committee report.

    Args:
        congress: Congress number (e.g. 119)
        chamber: 'house' or 'senate'
        report_number: Numeric report number (e.g. 172)

    Returns:
        Full URL string to the PDF.
    """
    prefix = "hrpt" if chamber == "house" else "srpt"
    return (
        f"https://www.congress.gov/{congress}/crpt/{prefix}{report_number}/"
        f"CRPT-{congress}{prefix}{report_number}.pdf"
    )


def pdf_filename(congress, chamber, report_number):
    """Return a standard local filename for a downloaded report PDF."""
    prefix = "hrpt" if chamber == "house" else "srpt"
    return f"CRPT-{congress}{prefix}{report_number}.pdf"


def download_pdf(congress, chamber, report_number, output_dir=None):
    """
    Download a committee report PDF from congress.gov.

    Args:
        congress: Congress number (e.g. 119)
        chamber: 'house' or 'senate'
        report_number: Numeric report number
        output_dir: Directory to save to (defaults to PDF_DIR)

    Returns:
        Path to the downloaded file, or None on failure.
    """
    if output_dir is None:
        output_dir = PDF_DIR
    os.makedirs(output_dir, exist_ok=True)

    fname = pdf_filename(congress, chamber, report_number)
    filepath = os.path.join(output_dir, fname)

    # Skip if already downloaded
    if os.path.exists(filepath):
        print(f"  Already exists: {fname}")
        return filepath

    url = pdf_url(congress, chamber, report_number)
    prefix = "H.Rept." if chamber == "house" else "S.Rept."
    label = f"{prefix} {congress}-{report_number}"
    print(f"  Downloading {label} from {url} ...")

    try:
        resp = requests.get(url, headers=HEADERS, timeout=60)
        resp.raise_for_status()
    except requests.exceptions.HTTPError as e:
        print(f"  HTTP error for {label}: {e}")
        return None
    except requests.exceptions.ConnectionError as e:
        print(f"  Connection error for {label}: {e}")
        return None
    except requests.exceptions.Timeout:
        print(f"  Timeout downloading {label}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  Error downloading {label}: {e}")
        return None

    # Verify we got a PDF (not an HTML error page)
    content_type = resp.headers.get("Content-Type", "")
    if "pdf" not in content_type.lower() and not resp.content[:5] == b"%PDF-":
        print(f"  Warning: {label} response does not appear to be a PDF (Content-Type: {content_type})")
        # Still save it -- congress.gov sometimes serves PDFs without the correct content type
        if resp.content[:5] != b"%PDF-":
            print(f"  Skipping {label}: response is not a PDF")
            return None

    with open(filepath, "wb") as f:
        f.write(resp.content)

    size_kb = len(resp.content) / 1024
    print(f"  Saved {fname} ({size_kb:.0f} KB)")
    return filepath


def download_known_reports(fiscal_year, chambers=None, subcommittees=None, output_dir=None):
    """
    Download all known reports for a fiscal year.

    Args:
        fiscal_year: e.g. 'FY2026'
        chambers: List of chambers to download, e.g. ['house', 'senate']. None = both.
        subcommittees: List of subcommittee names to download. None = all.
        output_dir: Directory to save to.

    Returns:
        Dict mapping (subcommittee, chamber) to file path (or None if failed).
    """
    congress = get_congress_number(fiscal_year)
    if chambers is None:
        chambers = ["house", "senate"]
    if subcommittees is None:
        subcommittees = SUBCOMMITTEES

    results = {}
    first = True

    for subcommittee in subcommittees:
        key = (fiscal_year, subcommittee)
        if key not in KNOWN_REPORTS:
            continue

        reports = KNOWN_REPORTS[key]
        for chamber in chambers:
            if chamber not in reports:
                continue

            if not first:
                time.sleep(DOWNLOAD_DELAY)
            first = False

            report_number = reports[chamber]
            print(f"\n[{subcommittee}] ({chamber.title()})")
            path = download_pdf(congress, chamber, report_number, output_dir)
            results[(subcommittee, chamber)] = path

    return results


# ---------------------------------------------------------------------------
# Congress.gov API search
# ---------------------------------------------------------------------------

def search_committee_reports(congress, report_type="hrpt", limit=50, offset=0):
    """
    Query the congress.gov API for committee reports.

    Args:
        congress: Congress number (e.g. 119)
        report_type: 'hrpt' for House reports, 'srpt' for Senate reports
        limit: Number of results per page (max 250)
        offset: Starting offset for pagination

    Returns:
        Dict with API response data, or None on error.
    """
    url = f"https://api.congress.gov/v3/committee-report/{congress}/{report_type}"
    params = {
        "api_key": CONGRESS_API_KEY,
        "limit": min(limit, 250),
        "offset": offset,
        "format": "json",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.HTTPError as e:
        print(f"  API HTTP error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"  Response: {e.response.text[:500]}")
        return None
    except requests.exceptions.RequestException as e:
        print(f"  API request error: {e}")
        return None
    except ValueError:
        print(f"  API returned non-JSON response")
        return None


def find_appropriations_reports(congress, report_type="hrpt"):
    """
    Search the congress.gov API for appropriations committee reports.

    Paginates through results and filters for reports from the
    Appropriations Committee.

    Args:
        congress: Congress number (e.g. 119)
        report_type: 'hrpt' or 'srpt'

    Returns:
        List of report dicts with keys like 'number', 'title', 'url', etc.
    """
    chamber_label = "House" if report_type == "hrpt" else "Senate"
    print(f"\nSearching congress.gov API for {chamber_label} appropriations reports "
          f"(Congress {congress})...")

    all_reports = []
    offset = 0
    limit = 100

    while True:
        data = search_committee_reports(congress, report_type, limit=limit, offset=offset)
        if data is None:
            break

        reports = data.get("committeeReports", data.get("reports", []))
        if not reports:
            break

        for report in reports:
            # Check if it looks like an appropriations report
            title = (report.get("title", "") or "").lower()
            citation = report.get("citation", "") or ""
            report_number = report.get("number", None)

            is_approp = any(kw in title for kw in [
                "appropriation",
                "department of",
                "departments of",
                "legislative branch",
                "military construction",
                "energy and water",
                "agriculture",
                "financial services",
                "homeland security",
                "interior",
                "transportation",
                "national security",
            ])

            if is_approp or "appropriat" in title:
                all_reports.append({
                    "number": report_number,
                    "title": report.get("title", ""),
                    "citation": citation,
                    "url": report.get("url", ""),
                    "update_date": report.get("updateDate", ""),
                })

        # Check for more pages
        pagination = data.get("pagination", {})
        total = pagination.get("count", 0)
        if offset + limit >= total:
            break
        offset += limit
        time.sleep(1)  # Be nice to the API

    print(f"  Found {len(all_reports)} appropriations-related reports")
    return all_reports


def get_report_detail(congress, report_type, report_number):
    """
    Get detailed information about a specific committee report from the API.

    Args:
        congress: Congress number
        report_type: 'hrpt' or 'srpt'
        report_number: Numeric report number

    Returns:
        Dict with report details, or None on error.
    """
    url = (
        f"https://api.congress.gov/v3/committee-report/"
        f"{congress}/{report_type}/{report_number}"
    )
    params = {
        "api_key": CONGRESS_API_KEY,
        "format": "json",
    }

    try:
        resp = requests.get(url, params=params, headers=HEADERS, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.RequestException as e:
        print(f"  API error for report {report_number}: {e}")
        return None


def discover_and_download(fiscal_year, chamber="house", output_dir=None):
    """
    Use the API to discover appropriations reports for a fiscal year,
    then download any that are found.

    Args:
        fiscal_year: e.g. 'FY2026'
        chamber: 'house' or 'senate'
        output_dir: Directory to save PDFs.

    Returns:
        List of (title, filepath) tuples for downloaded reports.
    """
    congress = get_congress_number(fiscal_year)
    report_type = "hrpt" if chamber == "house" else "srpt"

    reports = find_appropriations_reports(congress, report_type)
    downloaded = []

    for i, report in enumerate(reports):
        rnum = report.get("number")
        if rnum is None:
            continue

        if i > 0:
            time.sleep(DOWNLOAD_DELAY)

        print(f"\n  [{report['citation'] or f'{report_type.upper()} {rnum}'}] {report['title']}")
        path = download_pdf(congress, chamber, rnum, output_dir)
        if path:
            downloaded.append((report["title"], path))

    return downloaded


# ---------------------------------------------------------------------------
# Convenience helpers
# ---------------------------------------------------------------------------

def list_known_reports(fiscal_year=None):
    """Print a table of all known report numbers."""
    print("\nKnown Appropriations Committee Report Numbers")
    print("=" * 70)

    years = [fiscal_year] if fiscal_year else sorted(set(fy for fy, _ in KNOWN_REPORTS), reverse=True)

    for fy in years:
        congress = get_congress_number(fy)
        print(f"\n{fy} ({congress}th Congress)")
        print("-" * 50)

        for sub in SUBCOMMITTEES:
            key = (fy, sub)
            if key not in KNOWN_REPORTS:
                continue

            reports = KNOWN_REPORTS[key]
            parts = []
            if "house" in reports:
                parts.append(f"H.Rept. {congress}-{reports['house']}")
            if "senate" in reports:
                parts.append(f"S.Rept. {congress}-{reports['senate']}")

            print(f"  {sub:<30s} {', '.join(parts)}")


def get_report_path(fiscal_year, subcommittee, chamber):
    """
    Get the expected local path for a known report PDF.

    Returns:
        Tuple of (filepath, exists) or (None, False) if report not known.
    """
    key = (fiscal_year, subcommittee)
    if key not in KNOWN_REPORTS:
        return None, False

    reports = KNOWN_REPORTS[key]
    if chamber not in reports:
        return None, False

    congress = get_congress_number(fiscal_year)
    fname = pdf_filename(congress, chamber, reports[chamber])
    filepath = os.path.join(PDF_DIR, fname)
    return filepath, os.path.exists(filepath)


# ---------------------------------------------------------------------------
# Main: download a few sample reports for testing
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Appropriations Committee Report Finder")
    print("=" * 50)

    # Show known reports
    list_known_reports()

    # Download a few sample reports for testing
    print("\n\nDownloading sample reports for testing...")
    print("-" * 50)

    os.makedirs(PDF_DIR, exist_ok=True)

    samples = [
        # FY2025 Legislative Branch (known to exist and already in pdfs/)
        ("FY2025", "Legislative Branch", "house"),
        # FY2026 Agriculture (House)
        ("FY2026", "Agriculture", "house"),
        # FY2026 Legislative Branch (Senate)
        ("FY2026", "Legislative Branch", "senate"),
    ]

    for fy, subcommittee, chamber in samples:
        key = (fy, subcommittee)
        if key not in KNOWN_REPORTS or chamber not in KNOWN_REPORTS[key]:
            print(f"\n  No known {chamber} report for {subcommittee} {fy}")
            continue

        congress = get_congress_number(fy)
        report_number = KNOWN_REPORTS[key][chamber]
        prefix = "H.Rept." if chamber == "house" else "S.Rept."

        print(f"\n[{subcommittee} {fy}] {prefix} {congress}-{report_number}")
        path = download_pdf(congress, chamber, report_number)
        if path:
            size_kb = os.path.getsize(path) / 1024
            print(f"  File: {path} ({size_kb:.0f} KB)")

        time.sleep(DOWNLOAD_DELAY)

    # Quick API test: look up report detail for the FY2025 Leg Branch report
    print("\n\nAPI test: fetching report detail for H.Rept. 118-555...")
    print("-" * 50)
    detail = get_report_detail(118, "hrpt", 555)
    if detail:
        report_data = detail.get("committeeReports", [detail])[0] if isinstance(detail.get("committeeReports"), list) else detail
        print(f"  Title: {report_data.get('title', 'N/A')}")
        print(f"  Citation: {report_data.get('citation', 'N/A')}")
        print(f"  Update date: {report_data.get('updateDate', 'N/A')}")
    else:
        print("  Could not retrieve report detail (API may be rate-limited)")

    print("\nDone.")
