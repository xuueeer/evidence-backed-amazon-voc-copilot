# Project Workspace

## Purpose

The Project Workspace turns one-time connector analysis into a reusable project view.

It helps users review:

- product pool,
- supplier pool,
- open supplier follow-up tasks,
- project-level metrics,
- saved project JSON snapshots.

## Why this matters

A professional product development tool should not only process one uploaded file or one URL batch. It should help teams return to the same project, compare products, follow up with suppliers and continue decision-making.

## Current workspace inputs

The first version can build a workspace from the latest product URL connector analysis, including:

- Product Pool Summary
- Supplier Comparison
- Supplier Follow-up Questions

Users can also upload a previously downloaded project JSON.

## Workspace metrics

The workspace dashboard includes:

- product count,
- supplier count,
- review candidate count,
- high risk product count,
- open supplier follow-up count,
- average readiness score.

## Workspace views

### Product Pool

A product-level list for review candidates, follow-up products and risk items.

### Supplier Pool

A supplier-level list for comparing candidate suppliers.

### Follow-up Tasks

A task list generated from supplier follow-up questions.

## Current limitations

This first version does not include database persistence, user accounts or multi-user collaboration.

Projects are saved as JSON files.

## Future improvements

Planned improvements include:

- persistent project storage,
- product detail side panel,
- supplier detail page,
- report builder,
- project timeline,
- team assignment and status tracking.
