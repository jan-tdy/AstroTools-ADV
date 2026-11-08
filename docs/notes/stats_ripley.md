## What it does

Ripley's K and L functions for testing spatial clustering of 2-D points.

## How to use

1. **x** and **y** coordinates, **Region x0,x1,y0,y1** (empty = bounding box), **Radii**.
2. **Edge correction**: `none`, `translation`, `ohser`, `var-width`, `ripley`.
3. Press **Compute K and L**.

## Reading the results

150 points in the unit square (ten tight clusters of 15 points) with `ohser` correction: `max |L(r) - r| = 0.111425`. L(r) - r near 0 means random placement, positive means clustering, negative means regularity. **K / L** plots both against r.

## Tips and limits

- Always give the true region; a bounding box of a small sample is too small.
- Use radii up to about a quarter of the shorter side.
