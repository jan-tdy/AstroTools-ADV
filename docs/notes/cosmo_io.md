## What it does

Compares two cosmologies, clones one with changes, reads and writes files, converts to other representations and sets the default cosmology.

## How to use

1. The first block is cosmology **A** (the **Cosmology** selector and parameters), the second block is **B** (**Compare with**, default Planck15).
2. **Compare A with B** lists equality and each parameter.
3. **Clone A with changes**: write **Edit (clone) A** as `H0=70, Om0=0.3, name='mine'`, set **Store as** (default `edited`).
4. **Write A to file...** and **Read file...** use **Write format** / **Read format** (`ascii.ecsv`, `ascii.html`, `ascii.latex`, `ascii.mrt`).
5. **Convert A to format** (`astropy.cosmology`, `astropy.model`, `astropy.row`, `astropy.table`, `mapping`, `yaml`) and **Create from text** (YAML or a dict with a `cosmology` class name).
6. **Set A as default cosmology** changes what other pages mean by "default"; **Reset default (Planck18)** undoes it.

## Reading the results

Planck18 against Planck15: `A == B: False`, `same class: True`. The **Parameters** tab shows `H0` 67.66 vs 67.74 (differs), `Om0` 0.30966 vs 0.3075 (differs), `Tcmb0`, `Neff`, `m_nu` the same, `Ob0` 0.04897 vs 0.0486. Cloning with `H0=70` gives `Planck18 (modified)` and leaves other parameters alone.

## Tips and limits

- `is_equivalent` ignores the name; `==` does not.
- `ascii.latex` is offered for writing only; the **Read format** list has `ascii.ecsv`, `ascii.html` and `ascii.mrt`.
