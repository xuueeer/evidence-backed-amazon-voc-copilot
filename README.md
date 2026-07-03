# Amazon Market Research Dashboard

A cross-border ecommerce product development dashboard for supplier product pages, specification analysis, gap analysis, requirement drafts, readiness scoring, supplier comparison and project workspace review.

## Language

- [English](docs/README.en.md)
- [简体中文](docs/README.zh-CN.md)

## Live Demo

[Open Amazon Market Research Dashboard](https://kirrrto-amazon-market-research.streamlit.app)

## Current capabilities

- Spreadsheet import and field mapping
- Public supplier product page connector
- Template Center
- Specification Matrix
- Coverage Summary
- Gap Analysis
- Product Requirement Draft
- Supplier Follow-up Questions
- Decision Summary
- Product Readiness Summary
- Supplier Comparison
- Product Pool Summary
- Project Workspace JSON export/import

## Documentation

- [Data Collection Guide](docs/data-collection-guide.md)
- [Product Page Connector](docs/product-page-connector.md)
- [Specification Matrix](docs/specification-matrix.md)
- [Requirement Draft Export](docs/requirement-draft-export.md)
- [Readiness Score and Supplier Comparison](docs/readiness-score-and-supplier-comparison.md)
- [Project Workspace](docs/project-workspace.md)

## Local setup

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

## Tests

```bash
python -m pytest -q
```
