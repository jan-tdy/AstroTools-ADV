## Cosmology pages

The five cosmology pages share one **Cosmology** selector at the top and, below the results, a block of cosmology parameters. Choose a registered realization (`WMAP1` to `WMAP9`, `Planck13`, `Planck15`, `Planck18`), a cosmology stored in the [workspace](../../concepts/workspace.md), or `Custom`. With `Custom`, pick the **Class** (`FlatLambdaCDM`, `LambdaCDM`, `FlatwCDM`, `wCDM`, `Flatw0waCDM`, `w0waCDM`) and fill **H0**, **Om0**, **Ode0**, **Tcmb0**, **Neff**, **m_nu**, **Ob0**, **w0**, **wa**, **wz** as the class needs. The default is `Planck18`: H0 = 67.66 km/s/Mpc, Om0 = 0.30966.

## Data inputs

Statistics, fitting and series pages read data through a drop-down with up to three sources:

- **Numbers / expression**: type numbers separated by commas, spaces or lines, or an expression such as `linspace(0, 10, 101)` or `normal(0, 1, 200)`.
- **Workspace table**: choose a table and a column.
- **Workspace image**: all pixels (pages that offer it).

Non-finite values (NaN, inf) are dropped and counted in the output.
