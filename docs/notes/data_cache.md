## What it does

Inspects and manages the astropy download cache (`astropy.utils.data`): files that astropy and astroquery downloaded once and reuse.

## How to use

- **Package cache** is the namespace (`astropy`, `astroquery`...) and **URL / key** is the URL the next buttons use.
- **Refresh listing** shows the cache directory and entries; **Verify cache** checks them.
- **Is URL cached?**, **Download URL into cache** (with **Download timeout [s]**), **Import local file under URL key ...**, **Clear URL entry**.
- **Export cache to ZIP ...** and **Import cache from ZIP ...** move a cache to a machine without network.
- **Clear whole cache ...** deletes everything after a confirmation.

## Reading the results

**Info** gives `Cache directory`, `Entries` and `Total size`; **Cache contents** lists `url, file, size`. Example: `/root/.cache/astropy`, 1 entry, 52340 bytes (the observatory site list, `sites.json`). **Verify cache** answers `Cache verified: all entries are consistent.`

## Tips and limits

- Export the cache on a connected machine and import it where you are offline; this makes the data-dependent pages work (observatory names, IERS).
- Clearing the cache forces the next use to download again.
