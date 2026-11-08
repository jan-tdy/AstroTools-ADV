## What it does

Cuts a sub-image around a pixel or sky position and keeps the WCS aligned.

## How to use

1. Select the **Image**.
2. **Position in**: `pixel` (`x y`, 0-based) or `sky` (any SkyCoord text; needs a WCS).
3. **Position**: `64 64`, `10.68 41.27` or `00h42m44s +41d16m`.
4. **Size**: `40` (square), `ny, nx`, or an angle like `30 arcsec` (needs a WCS).
5. **Mode**: `trim` cuts at the edges, `partial` fills outside with **Fill value** (default `nan`), `strict` fails if the box leaves the image.
6. Press **Make cutout**; stored as **Store as** (default `cutout`).

## Reading the results

For `test_image`, position `64 64`, size 40: `shape (40, 40)`, `center (original px) (63.5, 63.5)`, `bbox original (y,x) ((44, 83), (44, 83))`, `slices original (slice(44, 84), slice(44, 84))`. An even size cannot be centred on a pixel, hence 63.5. **Plot** shows the cutout.

## Tips and limits

- The bounding box is inclusive of both end values (44 to 83 is 40 pixels).
- `trim` mode returns a smaller image near the edge, so check the shape.
