## What it does

Runs a SAMP hub, connects AstroTools-ADV to it and exchanges tables, images and coordinates with other desktop programs such as TOPCAT, Aladin and DS9. Everything stays on your computer.

## How to use

1. **Lockfile**: blank uses the standard `~/.samp` (what Aladin and TOPCAT use). A different path gives a private hub.
2. Press **Start hub** if no other program already runs one; otherwise connect to the existing hub. **Connect client** registers the application under **Client name** (default `AstroTools-ADV`); **Disconnect client** and **Stop hub** end it. **Refresh clients** updates the list.
3. **Extra listen types** adds message types to receive. **Load received tables into workspace** (on by default) stores tables that arrive; only local `file://` URLs are loaded.
4. To send, choose **Send to** (`(all clients)` or one client), the **Message** (`table.load.votable`, `image.load.fits`, `coord.pointAt.sky`, `custom`) and its data: **Workspace object** for a table, **File / URL** for an image, **Coordinate** (`10.68 41.27`), or **Custom type** with **Parameters**. Press **Send message**.
5. **Call and wait for reply** needs a specific client and times out after 10 s.

## Reading the results

With a private hub started and the client connected: **Log** shows `Hub started (id ...)` and `Client connected as cli#1`. **Clients** lists `cli#1 (this app)` with subscriptions `client.env.get, coord.pointAt.sky, image.load.fits, samp.app.ping, table.load.fits, table.load.votable`, and the hub client `cli#hub`.

## Tips and limits

- Start the other program first if it provides the hub, then connect.
- Sending a workspace object other than a table gives `... cannot be sent over SAMP`; choose a table.
- SAMP never uses the internet; it talks to `127.0.0.1`.
