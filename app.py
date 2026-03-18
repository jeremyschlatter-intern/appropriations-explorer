#!/usr/bin/env python3
"""
Appropriations Line Items Explorer - Web Application
Flask app for browsing and analyzing appropriations spending data.
"""

import json
import os
import re
import csv
import io
from collections import defaultdict

from flask import Flask, render_template, jsonify, request, Response

app = Flask(__name__)

DATA_DIR = os.path.join(os.path.dirname(__file__), "extracted")

_cache = {}
_cache_mtime = 0


def load_all_data():
    """Load all extracted data files with simple caching."""
    global _cache, _cache_mtime
    try:
        current_mtime = os.path.getmtime(DATA_DIR)
    except OSError:
        return []

    # Check if any file changed
    files = [f for f in os.listdir(DATA_DIR) if f.endswith('.json') and not f.startswith('debug')]
    max_mtime = max((os.path.getmtime(os.path.join(DATA_DIR, f)) for f in files), default=0)

    if max_mtime <= _cache_mtime and _cache:
        return list(_cache.values())

    data = {}
    for filename in sorted(files):
        filepath = os.path.join(DATA_DIR, filename)
        try:
            with open(filepath) as f:
                d = json.load(f)
            key = f"{d['metadata']['subcommittee']}|{d['metadata']['fiscal_year']}|{d['metadata']['source_type']}"
            data[key] = d
        except (json.JSONDecodeError, IOError, KeyError):
            pass

    _cache = data
    _cache_mtime = max_mtime
    return list(data.values())


def get_summary():
    """Get summary of all available data."""
    data = load_all_data()
    summary = defaultdict(lambda: defaultdict(list))
    for d in data:
        meta = d['metadata']
        summary[meta['subcommittee']][meta['fiscal_year']].append({
            'source_type': meta['source_type'],
            'num_items': meta.get('num_items', len(d.get('line_items', []))),
            'columns': d.get('columns', []),
        })
    return dict(summary)


@app.route('/')
def index():
    """Main page."""
    summary = get_summary()
    return render_template('index.html', summary=summary)


@app.route('/api/summary')
def api_summary():
    return jsonify(get_summary())


@app.route('/api/data/<subcommittee>/<fiscal_year>/<source_type>')
def api_data(subcommittee, fiscal_year, source_type):
    data = load_all_data()
    for d in data:
        meta = d['metadata']
        if (meta['subcommittee'] == subcommittee and
            meta['fiscal_year'] == fiscal_year and
            meta['source_type'] == source_type):
            return jsonify(d)
    return jsonify({"error": "Not found"}), 404


@app.route('/api/data/<subcommittee>')
def api_subcommittee_data(subcommittee):
    data = load_all_data()
    results = [d for d in data if d['metadata']['subcommittee'] == subcommittee]
    if not results:
        return jsonify({"error": "Not found"}), 404
    return jsonify(results)


@app.route('/api/compare/<subcommittee>')
def api_compare(subcommittee):
    """Cross-year comparison for a subcommittee.

    Builds a unified view showing each line item's committee recommendation
    across all available fiscal years.
    """
    data = load_all_data()
    relevant = [d for d in data if d['metadata']['subcommittee'] == subcommittee]

    if not relevant:
        return jsonify({"error": "Not found"}), 404

    # Organize by fiscal year + source
    datasets = {}
    for d in sorted(relevant, key=lambda x: (x['metadata']['fiscal_year'], x['metadata']['source_type'])):
        meta = d['metadata']
        key = f"{meta['fiscal_year']} {meta['source_type'].title()}"
        datasets[key] = d

    # For each dataset, find the "recommendation/bill" column and "enacted/prior" column
    year_columns = []
    year_items = {}

    for key, d in datasets.items():
        cols = d.get('columns', [])
        # Find recommendation column
        rec_idx = None
        enacted_idx = 0  # Usually first column

        for i, col in enumerate(cols):
            cl = col.lower()
            if any(t in cl for t in ['bill', 'recommend', 'committee']) and \
               not any(t in cl for t in ['compar', 'vs', 'vs.']):
                rec_idx = i
                break

        if rec_idx is None:
            rec_idx = min(2, len(cols) - 1)

        year_columns.append({
            'key': key,
            'col_name': cols[rec_idx] if rec_idx < len(cols) else 'Unknown',
            'all_columns': cols,
        })

        items = []
        for item in d.get('line_items', []):
            amounts = item.get('amounts', [])
            rec_val = amounts[rec_idx] if rec_idx < len(amounts) else None
            enacted_val = amounts[enacted_idx] if enacted_idx < len(amounts) else None
            items.append({
                'name': item.get('name', ''),
                'level': item.get('level', 0),
                'recommendation': rec_val,
                'enacted': enacted_val,
                'all_amounts': amounts,
            })
        year_items[key] = items

    return jsonify({
        'subcommittee': subcommittee,
        'year_columns': year_columns,
        'year_items': year_items,
    })


@app.route('/api/search')
def api_search():
    query = request.args.get('q', '').strip().lower()
    if not query or len(query) < 2:
        return jsonify([])

    data = load_all_data()
    results = []
    for d in data:
        meta = d['metadata']
        cols = d.get('columns', [])
        # Find recommendation column index
        rec_idx = 2
        for i, col in enumerate(cols):
            cl = col.lower()
            if any(t in cl for t in ['bill', 'recommend']) and 'vs' not in cl:
                rec_idx = i
                break

        for item in d.get('line_items', []):
            name = item.get('name', '')
            if query in name.lower():
                amounts = item.get('amounts', [])
                results.append({
                    'name': name,
                    'level': item.get('level', 0),
                    'recommendation': amounts[rec_idx] if rec_idx < len(amounts) else None,
                    'enacted': amounts[0] if amounts else None,
                    'subcommittee': meta['subcommittee'],
                    'fiscal_year': meta['fiscal_year'],
                    'source_type': meta['source_type'],
                })
    return jsonify(results[:200])


@app.route('/export/<subcommittee>/<fiscal_year>/<source_type>.csv')
def export_csv(subcommittee, fiscal_year, source_type):
    data = load_all_data()
    target = None
    for d in data:
        meta = d['metadata']
        if (meta['subcommittee'] == subcommittee and
            meta['fiscal_year'] == fiscal_year and
            meta['source_type'] == source_type):
            target = d
            break

    if not target:
        return "Not found", 404

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(['Line Item', 'Level'] + target['columns'])
    for item in target['line_items']:
        indent = '  ' * item.get('level', 0)
        row = [f"{indent}{item['name']}", item.get('level', 0)]
        for a in item.get('amounts', []):
            row.append(a if a is not None else '')
        writer.writerow(row)

    output.seek(0)
    safe_name = f"{subcommittee}_{fiscal_year}_{source_type}".replace(' ', '_')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={safe_name}.csv"}
    )


@app.route('/export/<subcommittee>/all.csv')
def export_all_csv(subcommittee):
    """Export all years for a subcommittee as one CSV."""
    data = load_all_data()
    relevant = sorted(
        [d for d in data if d['metadata']['subcommittee'] == subcommittee],
        key=lambda x: (x['metadata']['fiscal_year'], x['metadata']['source_type'])
    )

    if not relevant:
        return "Not found", 404

    output = io.StringIO()
    writer = csv.writer(output)

    for d in relevant:
        meta = d['metadata']
        writer.writerow([])
        writer.writerow([f"=== {meta['fiscal_year']} ({meta['source_type'].title()}) ==="])
        writer.writerow(['Line Item', 'Level'] + d['columns'])
        for item in d['line_items']:
            indent = '  ' * item.get('level', 0)
            row = [f"{indent}{item['name']}", item.get('level', 0)]
            for a in item.get('amounts', []):
                row.append(a if a is not None else '')
            writer.writerow(row)

    output.seek(0)
    safe_name = f"{subcommittee}_all_years".replace(' ', '_')
    return Response(
        output.getvalue(),
        mimetype='text/csv',
        headers={"Content-Disposition": f"attachment; filename={safe_name}.csv"}
    )


if __name__ == '__main__':
    print("Starting Appropriations Line Items Explorer...")
    print("Available at: http://localhost:8093")
    app.run(host='0.0.0.0', port=8093, debug=True)
