import screenscraper_download as d


def test_folded_ignores_case_accents_punctuation_and_the_article():
    assert d.folded("Smurfs Nightmare, The") == d.folded("The Smurfs' Nightmare") == "smurfs nightmare"
    assert d.folded("Pokémon - Rote Edition") == "pokemon rote edition"


def test_regions_follow_the_serial_then_europe_then_world():
    assert d.regions_of(["DMG-AU3P-NOE"])[:2] == ["de", "eu"]
    assert d.regions_of(["DMG-XX-USA"])[0] == "us"
    assert d.regions_of(["DMG-ZZ-PPJ"])[0] == "jp"
    assert d.regions_of([])[:2] == ["eu", "wor"]


def test_pick_takes_the_first_wanted_region_and_else_the_first_image():
    images = [("jp", "u1", "png"), ("eu", "u2", "png")]
    assert d.pick(images, ["us", "eu"]) == ("eu", "u2", "png")
    assert d.pick(images, ["us"]) == ("jp", "u1", "png")
    assert d.pick([], ["eu"]) is None


def test_best_game_needs_the_same_name_and_never_guesses():
    found = [{"id": "1", "noms": [{"text": "Tetris Blast"}]}, {"id": "2", "noms": [{"region": "eu", "text": "Tetris"}]}]
    assert d.best_game({"title": "Tetris"}, found)["id"] == "2"
    assert d.best_game({"title": "Tetris Attack"}, found) is None
