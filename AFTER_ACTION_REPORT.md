# After Action Report: Appropriations Line Items Explorer

## Project Summary

**Problem:** Congressional appropriations committee reports contain detailed spending tables (Comparative Statements of New Budget Authority) that show line-item spending for every federal program and agency. These tables are published as landscape-oriented pages within large PDF reports. Currently, extracting this data requires manually typing thousands of numbers from PDFs into spreadsheets -- a process that is extremely time-consuming and error-prone.

**Solution built:** An automated pipeline that extracts spending line items from committee report PDFs using AI vision (Claude API), organizes them into structured data, and serves them through a searchable web interface with CSV export.

**Deployed at:** https://jeremyschlatter-intern.github.io/appropriations-explorer/

**Coverage:** 12 appropriations subcommittees, 21 committee reports, 7,943 line items across FY2025-FY2026.

---

## Technical Architecture

### Data Pipeline

1. **Report Discovery** (`report_finder.py`) - Identifies committee report PDFs on congress.gov using the CRS Appropriations Status Table and known report numbers. Handles the mapping between fiscal years, Congress numbers, and report identifiers for both House and Senate reports.

2. **PDF Download** - Downloads committee report PDFs from congress.gov's standard URL pattern (`congress.gov/{congress}/crpt/{type}{number}/CRPT-{congress}{type}{number}.pdf`).

3. **Table Page Detection** (`extract.py`) - Uses a heuristic to identify the comparative statement table pages within each PDF. These pages have a distinctive signature: they contain rotated/landscape content that pdfplumber can't extract as text (yielding ~200 characters of metadata versus 2,000+ for normal pages). For large reports with multiple rotated sections, falls back to Claude API for page identification.

4. **Image Extraction & Rotation** - Renders each table page as a PNG image using pdfplumber, then rotates it 90 degrees since the tables are printed sideways on portrait-oriented pages.

5. **AI-Powered Table Extraction** - Sends each rotated page image to Claude Sonnet's vision model with a structured prompt that specifies the expected column headers and asks for JSON output with line item names, indentation levels, and amounts. Each page yields 10-20 line items.

6. **Data Assembly** - Combines page-by-page extractions into a complete dataset for each report, with metadata including subcommittee, fiscal year, source type (House/Senate), and source PDF information.

7. **Static Site Generation** (`build_static.py`) - Generates a self-contained HTML page with embedded JavaScript and JSON data files that can be hosted on GitHub Pages without a server.

### Web Interface

- Single-page application with all data loaded client-side
- Subcommittee cards showing available fiscal years and chambers
- Tabbed data viewer with sticky column headers
- Global search with abbreviation expansion (FBI -> Federal Bureau of Investigation)
- CSV export for any table
- Links to source PDF reports on congress.gov

---

## Obstacles Encountered and Solutions

### 1. Rotated PDF Tables

**Problem:** The comparative statement tables are printed in landscape orientation within portrait-format PDFs. Standard PDF text extraction tools (pdfplumber) cannot read the text content of these rotated pages.

**Failed approach:** Initially tried using pdfplumber's text extraction to find table pages by searching for keywords like "COMPARATIVE STATEMENT." This returned no matches because the text was unreadable.

**Solution:** Developed a two-layer approach: (a) a heuristic that identifies rotated pages by their distinctive low text content (~200 chars vs ~2000+ for normal pages), and (b) rendering pages as images and rotating them 90 degrees before sending to Claude's vision model. The AI can read the rotated table images accurately.

### 2. Large PDFs Exceeding API Limits

**Problem:** Some committee reports (e.g., Defense at 311 pages) exceed the Claude API's 100-page PDF limit, preventing full-document analysis.

**Solution:** Switched from full-PDF analysis to page-by-page image extraction. The heuristic identifies candidate pages without needing to send the entire document to the API. For column header detection and per-page extraction, only individual page images are sent.

### 3. Multiple Rotated Sections in Large Reports

**Problem:** Large reports like Agriculture and Defense contain multiple rotated sections -- earmark/community project funding tables AND the comparative statement. The heuristic sometimes picked up earmark tables instead of (or in addition to) the comparative statement.

**Partial solution:** For reports where the comparative statement is the last block of rotated pages, this works well. For reports with interleaved rotated content, the detection is less reliable. This remains a known limitation that could be improved by using the AI to classify each rotated section.

### 4. JSON Parsing Errors from AI Extraction

**Problem:** The AI sometimes produced invalid JSON in extraction responses -- particularly parenthesized negative numbers like `(-33979)` instead of `-33979`, and occasionally trailing commas.

**Solution:** Built a `fix_json_text()` function that post-processes the AI response to fix common issues: removing markdown code blocks, converting parenthesized negatives to proper negative numbers, and cleaning trailing commas.

### 5. Congress.gov Access Restrictions

**Problem:** Direct web fetching of congress.gov pages returned 403 errors, blocking programmatic access to the CRS Appropriations Status Table.

**Solution:** Used Chrome browser automation to visit the page directly and extracted report numbers via JavaScript DOM queries. Also hardcoded known report numbers for FY2024-2026 to avoid relying on page scraping.

### 6. GitHub Pages Deployment with Relative Paths

**Problem:** The static site needed to work both locally and when hosted at a subdirectory path on GitHub Pages (`/appropriations-explorer/`).

**Solution:** Used relative paths (`data/filename.json`) throughout the JavaScript code rather than absolute paths, ensuring the site works regardless of hosting location.

---

## DC Reviewer Feedback and Response

I created an AI agent playing the role of Daniel Schuman (the project originator) to review the tool from a DC perspective. Key feedback and actions taken:

| Feedback | Priority | Action Taken |
|----------|----------|-------------|
| Search "FBI" returns no results | High | Added abbreviation mapping for 54 common agency abbreviations |
| National Security-State card missing | High | Fixed CSS class mismatch bug |
| Search results don't scroll to matched item | Medium | Added scroll-to and highlight on search result click |
| No link to source PDF | Medium | Added report numbers and links to congress.gov PDFs |
| No percentage change columns | Low | Noted for future improvement |
| Side-by-side House vs Senate comparison | High | Noted as top feature request for next iteration |
| Data quality issues in Defense FY2025 | High | Identified root cause (earmark table contamination), partially addressed |

---

## Agent Team

This project was completed by a single Claude instance using multiple parallel sub-agents for:
- **Report finder module creation** - Built the report discovery and download system
- **Batch PDF extraction** - Multiple agents ran extractions in parallel for different subcommittees (Agriculture+Defense, CJS+Energy-Water, MCVA+Interior, etc.)
- **DC reviewer** - Simulated Daniel Schuman reviewing the tool from a Capitol Hill perspective

---

## What I Would Do Next

If continuing this project:

1. **Side-by-side House vs Senate comparison view** - The most requested feature. Show House and Senate recommendations for the same line items in adjacent columns.

2. **Year-over-year tracking with fuzzy matching** - Use the `consolidate.py` module (already built) to match line items across fiscal years using fuzzy string matching, enabling trend analysis.

3. **Data validation against 302(b) allocations** - Cross-reference extracted grand totals against published subcommittee allocations to verify extraction accuracy.

4. **Conference report extraction** - Extract data from the joint explanatory statements that accompany enacted appropriations, showing the final enacted amounts.

5. **Improved table detection for large reports** - Use AI classification to distinguish comparative statement tables from earmark tables in large reports with multiple rotated sections.

6. **Contact Congressional data librarians** - If permitted, reaching out to the Congressional Research Service or the Senate/House Appropriations Committee staff could help validate data accuracy and understand edge cases in table formats.

---

## Key Metrics

| Metric | Value |
|--------|-------|
| Reports processed | 21 |
| Line items extracted | 7,943 |
| Subcommittees covered | 12 of 12 |
| Fiscal years | 2 (FY2025, FY2026) |
| PDFs downloaded | 29 |
| API calls made | ~300 (table detection + page extraction) |
| Time to process one report | 2-5 minutes |
| Manual effort saved per report | ~2-4 hours |
