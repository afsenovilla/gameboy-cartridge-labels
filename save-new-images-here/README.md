# Save new images here

Drop photos of cartridges here, then run `make add-photos`: it files them into `photos/` and leaves
this folder empty.

- Put them in a subfolder named after where they came from, e.g. `ebay-elrocinante/`: the photos are stored under
  `photos/ebay-elrocinante/`. Photos straight in this folder go to `photos/unrecorded/`.
- Each photo is named by the serial read on its label (e.g. `DMG-CIJ-JPN.webp`, `_2`, `_3` when there are several),
  or `UNKNOWN` when none was read: rename it in `photos/` to identify it.
- Photos already in `photos/` (the same file) are deleted; anything that isn't a photo stays here.
- You may change the names of files in the `photos/` folder, and move them around. Running `make add-photos` will update the `sources.json` files.
