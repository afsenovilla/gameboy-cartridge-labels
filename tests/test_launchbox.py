import io

import launchbox_fetch as lb

XML = b"""<?xml version="1.0"?><LaunchBox>
<Game><Name>The Addams Family</Name><DatabaseID>10</DatabaseID><Platform>Nintendo Game Boy</Platform></Game>
<Game><Name>Asterix</Name><DatabaseID>11</DatabaseID><Platform>Nintendo Game Boy</Platform></Game>
<Game><Name>Asterix</Name><DatabaseID>12</DatabaseID><Platform>Sega Game Gear</Platform></Game>
<GameAlternateName><AlternateName>Asterix Le Gaulois</AlternateName><DatabaseID>11</DatabaseID><Region>France</Region></GameAlternateName>
<GameImage><DatabaseID>10</DatabaseID><FileName>a-01.jpg</FileName><Type>Cart - Front</Type><Region>Australia</Region></GameImage>
<GameImage><DatabaseID>10</DatabaseID><FileName>a-02.jpg</FileName><Type>Box - Front</Type><Region>Australia</Region></GameImage>
<GameImage><DatabaseID>11</DatabaseID><FileName>x-01.jpg</FileName><Type>Cart - Front</Type><Region>Germany</Region></GameImage>
<GameImage><DatabaseID>11</DatabaseID><FileName>x-02.jpg</FileName><Type>Cart - Front</Type><Region>France</Region></GameImage>
<GameImage><DatabaseID>12</DatabaseID><FileName>gg.jpg</FileName><Type>Cart - Front</Type><Region>Germany</Region></GameImage>
</LaunchBox>"""


def test_titles_compare_without_articles_and_punctuation():
    assert lb.plain("Addams Family, The") == lb.plain("The Addams Family") == "addamsfamily"
    assert lb.plain("Astérix") == "asterix"


def test_metadata_keeps_the_game_boy_games_with_their_names_and_images():
    games = lb.read_metadata(io.BytesIO(XML))
    assert set(games) == {"10", "11"}
    assert "asterixlegaulois" in games["11"]["names"]
    assert ("x-01.jpg", "cart - front", "germany") in games["11"]["images"]


def test_candidates_are_cartridge_photos_of_the_missing_region():
    games = lb.read_metadata(io.BytesIO(XML))
    wanted = [{"print": "DMG-AF-AUS", "title": "Addams Family, The", "system": "dmg", "serials": ["DMG-AF-AUS"]},
              {"print": "DMG-XA-NOE", "title": "Asterix", "system": "dmg", "serials": ["DMG-XA-NOE"]}]
    got = [(w["print"], f) for w, f, r in lb.candidates(wanted, games)]
    assert got == [("DMG-AF-AUS", "a-01.jpg"), ("DMG-XA-NOE", "x-01.jpg")]
