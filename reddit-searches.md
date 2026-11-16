# Reddit searches

Cartridge photos from r/gameboy and r/gameboyadvance. The extension won't open reddit.com and Reddit refuses automated downloads, so these pages are opened and saved by hand; the photos themselves are then downloaded by a script from i.redd.it and filed through make add-photos with each post's link, title and subreddit.

Open each address in Chrome and save it (Cmd-S, format "Webpage, HTML Only" or as it is) into this folder; the file names don't matter (search.json, search (1).json, … are fine):

downloaded-photos/reddit-json/

Each page holds up to 100 posts. The newest posts in each subreddit, without a search, are on the first two lines; the searches follow, newest first and then best voted of all time.

## r/gameboy

- https://www.reddit.com/r/gameboy/new.json?limit=100
- https://www.reddit.com/r/gameboy/top.json?t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=real&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=real&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=fake&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=fake&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=legit&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=legit&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=authentic&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=authentic&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=haul&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=haul&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=collection&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=collection&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=pickup&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=pickup&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=finally&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboy/search.json?q=finally&restrict_sr=1&sort=top&t=all&limit=100

## r/gameboyadvance

- https://www.reddit.com/r/gameboyadvance/new.json?limit=100
- https://www.reddit.com/r/gameboyadvance/top.json?t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=real&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=real&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=fake&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=fake&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=legit&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=legit&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=authentic&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=authentic&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=haul&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=haul&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=collection&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=collection&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=pickup&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=pickup&restrict_sr=1&sort=top&t=all&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=finally&restrict_sr=1&sort=new&limit=100
- https://www.reddit.com/r/gameboyadvance/search.json?q=finally&restrict_sr=1&sort=top&t=all&limit=100

## More pages

A full page (100 posts) ends with `"after": "t3_…"`. To get the next 100, add `&after=t3_…` (that value) to the same address. Reddit stops after about 1000 posts per listing.
