---
title: The workspace
section: Concepts
order: 20
lede: A shared, in-memory store that lets one tool hand its result to another.
---

Tools do not write files to pass data around. They put named objects into the workspace, and other tools offer those objects in drop-downs.

## What lives there

Tables, coordinate lists, `Time` arrays, images and `NDData`, WCS objects, FITS contents, time series, fitted models and cosmologies. A drop-down only lists objects of the type that tool can use, so the *Table* picker in the catalog matcher shows tables and nothing else.

## Storing and replacing

Buttons labelled *Store ... in workspace*, and fields such as *Store as*, *Workspace name* or *Result name*, choose the name. Storing under an existing name replaces the object. Names are trimmed of surrounding spaces and cannot be empty.

## Inspecting

Open **General → Workspace** to browse the objects and delete one. **Workspace → List objects** shows names with their Python types; **Workspace → Clear workspace** removes everything after a confirmation.

## Lifetime

The workspace exists only while the program runs. Save anything you want to keep: tables and FITS pages have *Save* buttons, and most result tables can be copied as CSV.

## Chaining example

1. **Data → Tables: Open / Inspect / Save**: open a CSV and store it as `stars`.
2. **Coordinates → Catalog matching**: choose `stars` as *Table*, pick its RA and Dec columns, match against a second table, and store the matches.
3. **Data → Tables: Plot**: plot a column of the stored matches.

None of these steps involved a file other than the first.
