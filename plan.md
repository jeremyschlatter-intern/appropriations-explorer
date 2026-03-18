# Appropriations Line Items Extractor - Implementation Plan

## Goal
Build a tool that automatically extracts appropriations line-item spending data from Congressional committee report PDFs and creates structured, trackable data tables across fiscal years.

## Architecture

### Data Pipeline
1. **Report Discovery** - Use congress.gov CRS Appropriations Status Table to find committee reports for each subcommittee and fiscal year
2. **PDF Download** - Download the committee report PDFs from congress.gov
3. **Table Extraction** - Use Claude API to extract the comparative spending tables from PDFs (page-by-page)
4. **Data Structuring** - Parse extracted data into normalized JSON/CSV format
5. **Cross-Year Matching** - Use fuzzy matching to align line items across different fiscal years
6. **Output** - Generate consolidated spreadsheets and a web interface for browsing

### Technology Stack
- **Python** - Core processing pipeline
- **Claude API** - PDF table extraction (vision model for rotated/complex tables)
- **pdfplumber** - PDF page extraction and pre-processing
- **rapidfuzz** - Fuzzy string matching for cross-year line item alignment
- **Flask** - Simple web UI for browsing results
- **pandas** - Data manipulation and CSV/Excel export

### Web Interface
- Browse by subcommittee
- View line items across fiscal years
- Download as CSV/Excel
- Search/filter line items
- Visual spending trends

## Phase 1: Start with Legislative Branch (proof of concept)
- Known data: The project description shows Legislative Branch Appropriations examples
- Extract from FY2024 and FY2025 House, Senate, and Conference reports
- Validate against manually-created spreadsheets

## Phase 2: Expand to all 12 subcommittees
- Use the same pipeline for all appropriations subcommittees
- Handle variations in table format across subcommittees

## Phase 3: Polish and iterate
- Web UI improvements
- Better fuzzy matching
- Historical data going back further
- DC agent feedback loop

## Key Challenges
- PDFs have rotated/landscape pages for spending tables
- Table formats vary between subcommittees
- Line item names change slightly across years
- Some items are added/removed between years
- Need to distinguish House/Senate/Conference versions
