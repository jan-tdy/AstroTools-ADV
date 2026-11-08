## What it does

Views and changes astropy configuration items for the running session.

## How to use

1. Choose the **Item** (for example `astropy.io.ascii.guess_limit_lines`). The **Item** tab shows type, value, default and description.
2. Type a **New value** in the item's type and press **Set value (this session)**; **Reset item to default** reverts it.
3. **Reload config file for item's package** re-reads the configuration file; **Show config locations** shows the file paths; **Show default config file text** uses **Config package** (default `astropy`).
4. **All items** lists every item as `module, name, value, default, type, description`; **Paths / defaults** shows the locations.

## Reading the results

`astropy.io.ascii.guess_limit_lines` is an integer with value and default 10000: the number of lines used to guess a table format.

## Tips and limits

- Changes last until you close the program; they are not written to the configuration file.
- A value of the wrong type is refused with an error.
