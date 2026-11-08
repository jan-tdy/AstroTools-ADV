---
title: Moving a star to a new epoch
order: 23
lede: Apply proper motion and radial velocity to Barnard's Star to find where it is in 2025.
---

Open [Space motion](../reference/coordinates/coord_motion.md). The page opens filled in for Barnard's Star at epoch J2000:

| Field | Value |
|---|---|
| Lines | `269.45 4.69` |
| Distance | `1.83 pc` |
| PM lon\*cos(lat) | `-798.58` mas/yr |
| PM lat | `10328.12` mas/yr |
| Radial velocity | `-110.51` km/s |
| Obstime | `J2000` |

1. Set **New epoch** to `J2025.0` and leave **or dt** empty (give exactly one of the two).
2. Press **Apply space motion**.

![Barnard's Star moved to J2025](../assets/guides/coords-proper-motion.png "Barnard's Star from J2000 to J2025.")

The **Positions** tab shows the star moving from `269.45, 4.69` to `269.4444265, 4.761833927`, a shift of `259.37 arcsec` in 25 years (10.4 arcsec per year, the largest proper motion of any star). Declination changes by 0.0718 deg, mostly northward, as the large positive `PM lat` says. The result is stored in the workspace as `moved` and can be used by any tool that takes a SkyCoord.
