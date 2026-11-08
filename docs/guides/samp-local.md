---
title: Exchanging data with desktop tools via SAMP
order: 53
lede: Start a SAMP hub, connect, and send a table or coordinates to TOPCAT, Aladin or DS9.
---

SAMP lets programs on the same computer exchange tables, images and sky positions. Nothing goes over the internet.

Open [SAMP](../reference/online/samp.md).

1. **Lockfile**: leave empty to use the standard `~/.samp` that Aladin and TOPCAT use. If one of them already runs a hub, skip the next step.
2. Press **Start hub**, then **Connect client**.

![SAMP with the hub started and the client connected](../assets/guides/online-samp-local.png "A hub with this application connected.")

The **Log** tab reads `Hub started (id ...)` and `Client connected as cli#1`. **Clients** lists every connected program with the messages it accepts: this application subscribes to `table.load.votable`, `table.load.fits`, `image.load.fits`, `coord.pointAt.sky` and `samp.app.ping`.

3. Start TOPCAT or Aladin and press **Refresh clients**. It appears in the list and in **Send to**.
4. To send a table, choose **Message** `table.load.votable`, the **Workspace object**, and press **Send message**. For a position use `coord.pointAt.sky` with **Coordinate** `10.68 41.27`; for an image use `image.load.fits` with a **File / URL**.

Tables selected in TOPCAT arrive in the workspace when **Load received tables into workspace** is on (only local files are loaded). Press **Stop hub** when you are done.
