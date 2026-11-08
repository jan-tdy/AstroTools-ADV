## What it does

A collection of small astropy utilities: masked quantities, metadata merging, object introspection, size and time formatting, and JSON encoding of astropy objects.

## How to use

| Button | Uses | Returns |
|---|---|---|
| **Evaluate** (masked arrays) | **Data** (expression), **Mask** (True = masked), **Operation on m** (`m.mean()`) | The masked Quantity, its mask and the operation result |
| **Merge** | **Left**, **Right**, **On conflict** (`warn`, `silent`, `error`) | The merged metadata dictionary |
| **Inspect** | **resolve_name** (dotted path), **Module**, **Minimum version** | The object and its docstring, the module version and whether it meets the minimum |
| **Format** | **Bytes**, **Seconds** | `human_file_size` and `human_time` strings |
| **Encode** | **Expression** | JSON text of Quantities, units, arrays, sets, bytes and complex numbers |

## Reading the results

Defaults: masked `np.arange(6.) * u.m` with mask `[0, 1, 0, 0, 1, 0]` gives `m.mean() -> 2.5 m`; merging `{'a': 1, 'b': 2}` with `{'b': 3, 'c': 4}` gives `{'a': 1, 'b': 3, 'c': 4}` plus a `MergeConflictWarning`; `123456789` bytes is `'123M'` and `3725` s is `' 1h 2m'`; `minversion('numpy', '1.20')` gives `True`.

## Tips and limits

- Each button fills only its own tab, so the results of the other buttons remain.
- `resolve_name` is deprecated in astropy and prints a warning.
