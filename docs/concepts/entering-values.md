---
title: Entering values
section: Concepts
order: 10
lede: One syntax for quantities, angles, times, coordinates and expressions, shared by every tool.
---

All tools read text fields through the same parser, so a value that works in one page works in all of them.

## Quantities

A number followed by a unit. Anything astropy's unit parser accepts is valid.

| You type | Meaning |
|---|---|
| `3.5 km/s` | 3.5 kilometres per second |
| `1e-3 m` | one millimetre |
| `2.5 m**2` | an area |
| `0 mag(AB)` | an AB magnitude |
| `1,5 m` | a decimal comma is read as a decimal point |
| `42` | allowed only where the field has a default unit, shown in its label or tooltip |

An unknown unit gives a warning that names the field, for example *unknown unit 'foo'*.

## Angles

Without a unit the field's default is used (usually degrees, hours where the label says RA).

```text
10.684            decimal degrees
10h41m02s         hours, minutes, seconds
-5d12m03.5s       degrees, arcminutes, arcseconds
1.2 rad           explicit unit
```

## Times

ISO strings such as `2000-01-01 12:00:00` or `2026-10-29T21:30:00`, the word `now`, and Julian or Besselian epochs `J2000.0`, `B1950`. Numeric input (`2451545`) needs an explicit *Input format* such as `jd`, `mjd` or `unix`. The scale (`utc`, `tai`, `tt`, `tdb`, ...) defaults to what the format implies and can be set in the *Input scale* field of the [Time converter](../reference/basics/time_converter.md).

## Coordinates

Two numbers are taken as degrees: `10.68 41.27`. Sexagesimal input works with hours for the first value: `00h42m44s +41d16m09s`. Anything containing words, such as `M31`, is sent to the CDS Sesame name resolver and needs network access.

## Expressions

Wherever a field says *numbers / expression*, you can type a Python expression instead of a list of numbers:

```text
np.linspace(0, 1, 11) * u.m
2 * const.G * 1 * u.Msun / (3e8 * u.m / u.s)**2
x > 3          # element-wise comparison on a column x
(x > 1) & (x < 5)
```

The names available are `u` (astropy.units), `np`, `const` (astropy.constants), `pi`, `e`, `inf`, `nan`, `Angle`, `SkyCoord`, `Time`, the math functions `sqrt exp log log10 sin cos tan abs`, the array builders `arange linspace logspace array zeros ones`, and `float int len min max sum round`.

Table tools also expose each column name. The [API Explorer](../reference/system/api_explorer.md) exposes workspace objects as `ws_<name>`.

Expressions are evaluated by a restricted interpreter: no imports, no comprehensions or lambdas, no names starting with an underscore, and no modules other than numpy and astropy. This keeps a mistyped field from doing anything surprising. It is a convenience restriction for a local desktop tool, not a security boundary against hostile input, so do not paste expressions from sources you do not trust.
