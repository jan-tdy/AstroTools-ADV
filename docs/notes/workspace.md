## What it does

Browses the objects that tools have stored in the shared [workspace](../../concepts/workspace.md).

## How to use

1. Choose an **Object** from the drop-down.
2. **Show** prints its name, Python type and a text representation.
3. **Delete** removes it from the workspace (other tools can no longer use it).

## Reading the results

A table `t` with one column shows `t  <astropy.table.table.Table>` followed by the table text. For images, models and cosmologies the representation is the one astropy prints.

## Tips and limits

- Deleting cannot be undone.
- **Workspace** in the menu bar also has **List objects** and **Clear workspace**.
