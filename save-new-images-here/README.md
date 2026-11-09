# Save new images here

Drop photos of cartridges here, then run `make add-photos`: it files them into `photos/` as `<sha1>.<ext>` (the file's own SHA-1, never re-encoded) and leaves this folder empty.

- Put them in a subfolder named after where they came from, e.g. `ebay-search/`: that name is the photo's source in `photo-sources.json`. Photos straight in this folder get the source `unrecorded`.
- A `listing.json` in the subfolder (file name -> page_url, image_url, title_on_page, ...) goes into each photo's record.
- Photos already in `photos/` (the same file) are deleted, their listing added to the existing record; anything that isn't a photo stays here, and is listed.
