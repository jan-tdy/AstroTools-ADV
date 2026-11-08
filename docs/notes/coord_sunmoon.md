## What it does

Sun and Moon rise, set and transit, twilight windows, the astronomical night, Moon phase and the Moon separation from your targets.

## How to use

1. Set the observer (**Mode**, **Longitude**, **Latitude**, **Height**).
2. Optional **Lines** with targets (ICRS by default) for Moon separation.
3. Set **Start (UTC)** (default `now`), **Window [h]** (24) and **Step [min]** (5; events are then refined to sub-second accuracy) and **Display UTC offset [h]**.
4. Press **Compute**; **Store tables in workspace** saves them under **Workspace name** (default `sunmoon`).

## Reading the results

For longitude -5.9, latitude 37.9 starting 2024-03-10 12:00 UTC: solar noon 12:33:55 (altitude 48.31 deg), sunset 18:26:20, astronomical dusk 19:53:43, astronomical dawn 05:12:57 next day, sunrise 06:40:12. **Astronomical night** lists `start, end, hours`: 9.320 h. **Moon phase**: New Moon, illuminated fraction 0.001, phase angle 177.2 deg. Other tabs: **Events**, **Moon separation**, **Sun and Moon altitude**.

## Tips and limits

- Sun and Moon events use a horizon of -0.833 deg, which includes standard refraction and the apparent radius.
- Window times are UTC. Set the offset to read local times; on 2024-03-10 Spain is UTC+1.
- At high latitudes the Sun may not set; the event is then missing.
- See [Observing night guide](../../guides/observing-night.md).
