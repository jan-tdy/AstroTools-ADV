## What it does

Turns bit-flag data-quality values into boolean masks (`bitfield_to_boolean_mask`) and decodes flag specifications (`interpret_bit_flags`).

## How to use

1. Enter the **Bit field**: integers or an expression such as `arange(0, 33)`, or tick **Use workspace image** and choose a DQ image in **...or workspace**.
2. **Ignore flags** lists flags that do not count as bad: ints, `1+4`, names (defined in **Flag names**, for example `CR=1, HOT=4, DEAD=16`) or `~` for the complement. **Flip bits** treats the list as the flags to keep.
3. **good_mask_value = True** reverses the output convention (good pixels are True).
4. **Make boolean mask** computes the mask; **Interpret flags only** just prints the value of the flag specification.

## Reading the results

Default values `0, 1, 2, 3, 4, 5, 8, 16, 17` with ignored flags `1, 4`: `true=5/9`: values 2, 3, 8, 16 and 17 are masked; 0, 1, 4, 5 are not. **Interpret flags only** gives `5 (binary 0b101)`. The mask is stored as `bitmask`.

## Tips and limits

- A pixel is masked when it has any set bit that is not ignored.
- Use names rather than numbers for flags you will read later.
