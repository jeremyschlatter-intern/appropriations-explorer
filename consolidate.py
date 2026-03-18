#!/usr/bin/env python3
"""
Consolidate extracted appropriations data across fiscal years.
Matches line items across years using fuzzy string matching and
produces unified spreadsheets.
"""

import json
import os
import re
import csv
import pandas as pd
from rapidfuzz import fuzz, process
from collections import defaultdict


def load_extractions(data_dir="extracted"):
    """Load all extraction JSON files from the data directory."""
    extractions = []
    for filename in sorted(os.listdir(data_dir)):
        if filename.endswith('.json') and not filename.startswith('debug'):
            filepath = os.path.join(data_dir, filename)
            with open(filepath) as f:
                data = json.load(f)
            extractions.append(data)
    return extractions


def normalize_name(name):
    """Normalize a line item name for matching."""
    name = name.strip()
    # Remove leading/trailing dots, dashes
    name = re.sub(r'^[\.\-—–\s]+|[\.\-—–\s]+$', '', name)
    # Normalize whitespace
    name = re.sub(r'\s+', ' ', name)
    # Normalize dashes
    name = re.sub(r'[—–]', '-', name)
    return name


def match_line_items(items_by_year, threshold=80):
    """
    Match line items across different fiscal years using fuzzy matching.

    Args:
        items_by_year: dict mapping year -> list of (name, level, amounts) tuples
        threshold: minimum fuzzy match score (0-100)

    Returns:
        List of matched groups: [{name, matches: {year: (name, amounts)}}]
    """
    # Get all unique names across years
    all_names = {}  # name -> (year, level)
    for year, items in items_by_year.items():
        for name, level, amounts in items:
            norm = normalize_name(name)
            if norm:
                all_names[f"{year}::{norm}"] = (year, name, level, amounts)

    # Build match groups
    matched = set()
    groups = []

    # First pass: exact matches (after normalization)
    name_index = defaultdict(list)
    for key, (year, name, level, amounts) in all_names.items():
        norm = normalize_name(name).lower()
        name_index[norm].append(key)

    for norm, keys in name_index.items():
        if len(keys) > 1:
            group = {"canonical_name": None, "matches": {}}
            for key in keys:
                year, name, level, amounts = all_names[key]
                group["matches"][year] = {"name": name, "level": level, "amounts": amounts}
                matched.add(key)
            # Use the most recent year's name as canonical
            latest = max(group["matches"].keys())
            group["canonical_name"] = group["matches"][latest]["name"]
            group["level"] = group["matches"][latest]["level"]
            groups.append(group)

    # Second pass: fuzzy matches for unmatched items
    unmatched = {k: v for k, v in all_names.items() if k not in matched}
    unmatched_by_year = defaultdict(list)
    for key, (year, name, level, amounts) in unmatched.items():
        unmatched_by_year[year].append((key, name, level, amounts))

    years = sorted(unmatched_by_year.keys())
    if len(years) > 1:
        # For each item in one year, try to find best match in other years
        base_year = years[0]
        for key, name, level, amounts in unmatched_by_year[base_year]:
            if key in matched:
                continue
            group = {"canonical_name": name, "level": level, "matches": {
                base_year.split("::")[0] if "::" in base_year else base_year: {
                    "name": name, "level": level, "amounts": amounts
                }
            }}
            matched.add(key)

            for other_year in years[1:]:
                other_items = [(k, n) for k, n, l, a in unmatched_by_year[other_year] if k not in matched]
                if not other_items:
                    continue

                other_names = [n for k, n in other_items]
                result = process.extractOne(
                    normalize_name(name),
                    [normalize_name(n) for n in other_names],
                    scorer=fuzz.ratio
                )

                if result and result[1] >= threshold:
                    idx = result[2]
                    other_key = other_items[idx][0]
                    _, other_name, other_level, other_amounts = all_names[other_key]
                    yr = other_year.split("::")[0] if "::" in other_year else other_year
                    group["matches"][yr] = {
                        "name": other_name, "level": other_level, "amounts": other_amounts
                    }
                    matched.add(other_key)
                    group["canonical_name"] = other_name  # Use most recent name

            groups.append(group)

    # Add remaining unmatched as solo entries
    for key in all_names:
        if key not in matched:
            year, name, level, amounts = all_names[key]
            groups.append({
                "canonical_name": name,
                "level": level,
                "matches": {
                    year: {"name": name, "level": level, "amounts": amounts}
                }
            })

    return groups


def consolidate_subcommittee(subcommittee, extractions):
    """
    Consolidate all extractions for a given subcommittee into a unified table.

    Returns a dict with:
    - years: list of fiscal years
    - columns_by_year: {year: [column headers]}
    - items: list of consolidated line items
    """
    # Filter extractions for this subcommittee
    relevant = [e for e in extractions
                if e['metadata']['subcommittee'] == subcommittee]

    if not relevant:
        return None

    # Group by fiscal year and source type
    by_year_source = {}
    for ext in relevant:
        fy = ext['metadata']['fiscal_year']
        src = ext['metadata']['source_type']
        by_year_source[f"{fy}_{src}"] = ext

    # Build items by year (using the committee recommendation column)
    items_by_year = {}
    columns_by_year = {}

    for key, ext in sorted(by_year_source.items()):
        fy = ext['metadata']['fiscal_year']
        src = ext['metadata']['source_type']
        year_key = f"{fy} ({src.title()})"

        columns_by_year[year_key] = ext['columns']

        items = []
        for item in ext['line_items']:
            name = item.get('name', '')
            level = item.get('level', 0)
            amounts = item.get('amounts', [])
            items.append((name, level, amounts))

        items_by_year[year_key] = items

    years = sorted(items_by_year.keys())

    return {
        "subcommittee": subcommittee,
        "years": years,
        "columns_by_year": columns_by_year,
        "items_by_year": items_by_year,
    }


def build_comparison_table(consolidated):
    """
    Build a comparison table showing the committee recommendation
    for each line item across fiscal years.

    Returns a pandas DataFrame.
    """
    if not consolidated:
        return None

    years = consolidated['years']
    items_by_year = consolidated['items_by_year']
    columns_by_year = consolidated['columns_by_year']

    # For each year, find the "recommendation" or "bill" column index
    rec_col_idx = {}
    for year, cols in columns_by_year.items():
        for i, col in enumerate(cols):
            col_lower = col.lower()
            if any(term in col_lower for term in ['bill', 'recommend', 'committee']):
                if 'compar' not in col_lower and 'vs' not in col_lower:
                    rec_col_idx[year] = i
                    break
        if year not in rec_col_idx:
            # Default to third column (index 2) which is usually the recommendation
            rec_col_idx[year] = min(2, len(cols) - 1)

    # Build rows: each row is a line item
    rows = []
    for year in years:
        for name, level, amounts in items_by_year[year]:
            idx = rec_col_idx.get(year, 2)
            amount = amounts[idx] if idx < len(amounts) else None

            # Also get enacted (first column usually)
            enacted = amounts[0] if amounts else None

            rows.append({
                "Line Item": name,
                "Level": level,
                "Year": year,
                "Enacted (Prior Year)": enacted,
                "Committee Recommendation": amount,
            })

    if not rows:
        return None

    df = pd.DataFrame(rows)
    return df


def export_to_csv(consolidated, output_path):
    """Export consolidated data to CSV format for easy spreadsheet use."""
    if not consolidated:
        return

    years = consolidated['years']
    items_by_year = consolidated['items_by_year']

    # Write each year as a separate section in the CSV
    rows = []
    for year in years:
        cols = consolidated['columns_by_year'][year]
        rows.append([f"=== {year} ==="] + [""] * len(cols))
        rows.append(["Line Item", "Level"] + cols)

        for name, level, amounts in items_by_year[year]:
            indent = "  " * level
            row = [f"{indent}{name}", level]
            for a in amounts:
                if a is None:
                    row.append("")
                else:
                    row.append(a)
            # Pad if needed
            while len(row) < len(cols) + 2:
                row.append("")
            rows.append(row)

        rows.append([])  # blank line between years

    with open(output_path, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerows(rows)

    print(f"Exported to {output_path}")


def export_to_excel(consolidated, output_path):
    """Export consolidated data to Excel with formatting."""
    if not consolidated:
        return

    with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
        for year in consolidated['years']:
            cols = consolidated['columns_by_year'][year]
            items = consolidated['items_by_year'][year]

            rows = []
            for name, level, amounts in items:
                indent = "  " * level
                row = {"Line Item": f"{indent}{name}", "Level": level}
                for i, col in enumerate(cols):
                    row[col] = amounts[i] if i < len(amounts) else None
                rows.append(row)

            df = pd.DataFrame(rows)
            sheet_name = year[:31]  # Excel sheet name limit
            df.to_excel(writer, sheet_name=sheet_name, index=False)

    print(f"Exported to {output_path}")


def get_available_data(data_dir="extracted"):
    """Get summary of available extracted data."""
    extractions = load_extractions(data_dir)

    summary = defaultdict(lambda: defaultdict(list))
    for ext in extractions:
        meta = ext['metadata']
        summary[meta['subcommittee']][meta['fiscal_year']].append({
            'source_type': meta['source_type'],
            'num_items': meta['num_items'],
            'extraction_date': meta['extraction_date'],
        })

    return dict(summary)


if __name__ == "__main__":
    print("Loading extracted data...")
    extractions = load_extractions()

    if not extractions:
        print("No extractions found. Run extract.py first.")
        exit(1)

    print(f"Found {len(extractions)} extraction files")

    # Get available subcommittees
    subcommittees = set(e['metadata']['subcommittee'] for e in extractions)
    print(f"Subcommittees: {subcommittees}")

    for subcommittee in subcommittees:
        print(f"\nConsolidating: {subcommittee}")
        consolidated = consolidate_subcommittee(subcommittee, extractions)
        if consolidated:
            print(f"  Years: {consolidated['years']}")

            # Export
            safe_name = re.sub(r'[^a-z0-9]+', '_', subcommittee.lower()).strip('_')
            export_to_csv(consolidated, f"data/{safe_name}.csv")
            export_to_excel(consolidated, f"data/{safe_name}.xlsx")
