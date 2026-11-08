## What it does

Rebins an image by whole blocks (`block_reduce`) or repeats pixels (`block_replicate`).

## How to use

1. Select the **Image**.
2. **Operation**: `block_reduce` or `block_replicate`.
3. **Block size**: `2` or per axis `ny, nx` (NumPy order).
4. For reduce choose the **Function**: `sum`, `mean`, `median`, `min`, `max`. For replicate **Conserve sum** divides by the block area so the total stays the same.
5. Press **Apply**; stored as **Store as** (default `blocked`).

## Reading the results

`test_image` with block 2 and `sum`: `(128, 128) -> (64, 64)`, `sum before 1729072.8`, `sum after 1729072.8`.

## Tips and limits

- Sizes that do not divide the image are trimmed at the edge; check the output shape.
- Use `sum` for counts (flux conserved) and `mean` for surface brightness.
