import json

import screenscraper_download as d


def test_query_drops_the_article_and_the_punctuation():
    assert d.query_of("Smurfs Nightmare, The") == "Smurfs Nightmare"
    assert d.query_of("Pokémon - Rote Edition") == "Pokemon Rote Edition"


def test_titles_come_from_labels_and_wanted_once_each(tmp_path):
    a, b = tmp_path / "labels.json", tmp_path / "wanted.json"
    a.write_text(json.dumps([{"system": "dmg", "title": "Tetris"}, {"system": "agb", "title": "Tetris"}]), encoding="utf-8")
    b.write_text(json.dumps([{"system": "dmg", "title": "tetris"}, {"system": "cgb", "title": "Zelda, The"}, {"system": "dmg", "title": None}]), encoding="utf-8")
    assert d.titles([str(a), str(b), str(tmp_path / "none.json")]) == [("gb", "Tetris"), ("gba", "Tetris"), ("gbc", "Zelda")]


def fake(responses):
    def call(endpoint, creds, **params):
        return responses[(endpoint, params.get("recherche") or params.get("gameid"))]
    return call


def test_run_keeps_every_game_found_with_every_region_and_never_asks_twice():
    medias = [{"type": "support-texture", "region": "eu", "url": "http://x/1", "format": "png"},
              {"type": "support-texture", "region": "us", "url": "http://x/2", "format": "png"},
              {"type": "support-2D", "region": "eu", "url": "http://x/3", "format": "png"}]
    call = fake({("jeuRecherche.php", "Tetris"): {"response": {"jeux": [{"id": "7", "noms": [{"text": "Tetris"}]}]}},
                 ("jeuInfos.php", 7): {"response": {"jeu": {"medias": medias, "dates": [{"region": "eu"}]}}}})
    state, fetched = {"games": {}, "searched": []}, []
    used = d.run([("gb", "Tetris")], {}, state, 100, call=call, fetch=lambda u, n: fetched.append((u, n)))
    assert used == 2 and fetched == [("http://x/1", "gb/7-eu.png"), ("http://x/2", "gb/7-us.png")]
    assert state["games"]["7"] == {"system": "gb", "names": ["Tetris"], "labels": ["gb/7-eu.png", "gb/7-us.png"], "checked": True}
    assert d.run([("gb", "Tetris")], {}, state, 100, call=call) == 0  # already searched


def test_run_stops_at_the_limit_and_resumes():
    call = fake({("jeuRecherche.php", "A"): {"response": {"jeux": []}}, ("jeuRecherche.php", "B"): {"response": {"jeux": []}}})
    state = {"games": {}, "searched": []}
    assert d.run([("gb", "A"), ("gb", "B")], {}, state, 1, call=call) == 1 and state["searched"] == ["gb|a"]
    assert d.run([("gb", "A"), ("gb", "B")], {}, state, 1, call=call) == 1 and state["searched"] == ["gb|a", "gb|b"]


def test_plain_text_answers_mean_not_found_but_quota_messages_stop():
    state = {"games": {}, "searched": []}
    d.run([("gb", "A")], {}, state, 5, call=lambda *a, **k: {"error": "Erreur : Jeu non trouvée !"})
    assert state["searched"] == ["gb|a"]
    state = {"games": {}, "searched": []}
    d.run([("gb", "A")], {}, state, 5, call=lambda *a, **k: {"error": "API closed for non-members: quota exceeded"})
    assert state["searched"] == []


def test_an_image_that_fails_is_left_out_and_the_run_goes_on():
    medias = [{"type": "support-texture", "region": "eu", "url": "http://x/1", "format": "png"},
              {"type": "support-texture", "region": "us", "url": "http://x/2", "format": "png"}]
    call = fake({("jeuRecherche.php", "Tetris"): {"response": {"jeux": [{"id": "7", "medias": medias, "dates": [{"region": "us"}]}]}}})
    state = {"games": {}, "searched": []}
    d.run([("gb", "Tetris")], {}, state, 5, call=call, fetch=lambda u, n: u != "http://x/1" and None)
    assert state["games"]["7"]["labels"] == ["gb/7-us.png"] and state["searched"] == ["gb|tetris"]


def test_inspect_leaves_out_medias_and_links():
    import screenscraper_inspect as i
    assert i.strip({"id": "7", "medias": [1], "x": [{"url": "https://a?ssid=me", "k": "v"}]}) == {"id": "7", "x": [{"k": "v"}]}


HACK = {"id": "490040", "notgame": "false", "noms": [{"region": "ss", "text": "Castlevania - Revenge"}],
        "editeur": {"id": "12672", "text": "ROMhacking.net"}, "dates": [{"region": "wor", "text": "2007-10-04"}],
        "synopsis": [{"langue": "en", "text": "A hack of Harmony of Dissonance by someone"}],
        "roms": [{"hack": "0", "unl": "0"}]}
OFFICIAL = {"id": "84714", "notgame": "false", "noms": [{"region": "ss", "text": "Yoshi"}, {"region": "us", "text": "Yoshi"}],
            "editeur": {"text": "Nintendo"}, "dates": [{"region": "us", "text": "2002-09-24"}],
            "synopsis": [{"langue": "en", "text": "Yoshi's Island makes us discover the origin of Mario."}],
            "roms": [{"hack": "0", "regions": {"regions_shortname": ["us"]}}]}


def test_verdict_keeps_shop_games_and_leaves_out_fan_made_ones():
    assert d.verdict(OFFICIAL) is None
    assert d.verdict(HACK) == "published by ROMhacking.net"
    assert d.verdict({**HACK, "editeur": {"text": "Someone"}}) == "described as a hack or homebrew"
    assert d.verdict({**HACK, "editeur": {}, "synopsis": []}) == "no release in any country and no publisher"
    assert d.verdict({**HACK, "editeur": {"text": "Vivendi Universal Games"}, "synopsis": []}) is None
    assert d.verdict({**OFFICIAL, "synopsis": [{"langue": "en", "text": "A hack and slash game with a hacker."}]}) is None
    assert d.verdict({**OFFICIAL, "roms": [{"unl": "1"}, {"trad": "1"}]}) == "every dump is flagged trad/unl"


def test_run_records_excluded_games_without_downloading_them():
    call = fake({("jeuRecherche.php", "Castlevania"): {"response": {"jeux": [{**HACK, "medias": [
        {"type": "support-texture", "region": "wor", "url": "http://x/1", "format": "png"}]}]}}})
    state, fetched = {"games": {}, "searched": []}, []
    d.run([("gba", "Castlevania")], {}, state, 5, call=call, fetch=lambda u, n: fetched.append(n))
    assert fetched == [] and state["games"]["490040"]["excluded"] == "published by ROMhacking.net"


def test_recheck_moves_the_images_of_games_found_before_the_filter():
    state = {"games": {"490040": {"system": "gba", "names": ["C"], "labels": ["gba/490040-wor.png"]},
                       "84714": {"system": "gba", "names": ["Y"], "labels": ["gba/84714-us.png"]}}, "searched": []}
    answers = {490040: HACK, 84714: OFFICIAL}
    moved = []
    used = d.recheck(state, {}, 10, call=lambda e, c, **p: {"response": {"jeu": answers[p["gameid"]]}}, move=moved.append)
    assert used == 2 and moved == ["gba/490040-wor.png"]
    assert state["games"]["490040"]["labels"] == [] and state["games"]["84714"]["checked"]
    assert d.recheck(state, {}, 10, call=None) == 0


def test_recheck_asks_again_about_games_the_old_country_rule_left_out_and_downloads_them():
    state = {"games": {"562293": {"system": "gba", "names": ["2 in 1"], "labels": [], "excluded": "no release in any country"}}, "searched": []}
    game = {**HACK, "editeur": {"text": "Vivendi Universal Games"}, "synopsis": [],
            "medias": [{"type": "support-texture", "region": "eu", "url": "http://x/1", "format": "png"}]}
    got = []
    d.recheck(state, {}, 5, call=lambda e, c, **p: {"response": {"jeu": game}}, fetch=lambda u, n: got.append(n))
    assert got == ["gba/562293-eu.png"] and state["games"]["562293"] == {"system": "gba", "names": ["2 in 1"], "labels": ["gba/562293-eu.png"], "checked": True}


def test_identical_images_of_two_regions_are_downloaded_once():
    medias = [{"type": "support-texture", "region": "eu", "url": "http://x/1", "format": "png", "md5": "aa"},
              {"type": "support-texture", "region": "fr", "url": "http://x/2", "format": "png", "md5": "aa"},
              {"type": "support-texture", "region": "us", "url": "http://x/3", "format": "png", "md5": "bb"}]
    got = []
    files, same = d.save_textures("gb", "37225", {"medias": medias}, lambda u, n: got.append(u))
    assert got == ["http://x/2", "http://x/3"] and files == ["gb/37225-fr.png", "gb/37225-us.png"]
    assert same == {"gb/37225-eu.png": "gb/37225-fr.png"}


def test_the_kept_region_is_where_the_label_was_sold():
    k = lambda *r: d.region_of(d.keeper([f"gb/1-{x}.png" for x in r]))
    assert k("eu", "fr") == "fr"            # only France: a French label
    assert k("eu", "de", "fr", "it") == "eu"  # several European countries: the European one
    assert k("wor", "us", "ca") == "us"
    assert k("wor", "eu") == "eu" and k("wor", "jp") == "jp" and k("ss", "wor") in ("ss", "wor")


def test_dedupe_removes_identical_copies_already_downloaded(tmp_path):
    (tmp_path / "gb").mkdir()
    for name, data in (("1-eu", b"x"), ("1-fr", b"x"), ("1-us", b"y")):
        (tmp_path / "gb" / f"{name}.png").write_bytes(data)
    state = {"games": {"1": {"system": "gb", "labels": ["gb/1-eu.png", "gb/1-fr.png", "gb/1-us.png"]}}}
    assert d.dedupe(state, out=str(tmp_path)) == 1
    assert state["games"]["1"]["labels"] == ["gb/1-fr.png", "gb/1-us.png"]
    assert state["games"]["1"]["same"] == {"gb/1-eu.png": "gb/1-fr.png"} and not (tmp_path / "gb" / "1-eu.png").exists()


def test_an_image_another_game_already_has_is_not_downloaded_again():
    seen = {}
    jp = [{"type": "support-texture", "region": "jp", "url": "http://x/a", "format": "png", "md5": "same"}]
    assert d.save_textures("gb", "170167", {"medias": jp}, lambda u, n: None, seen) == (["gb/170167-jp.png"], {})
    got = []
    files, same = d.save_textures("gb", "170168", {"medias": jp}, lambda u, n: got.append(u), seen)
    assert got == [] and files == [] and same == {"gb/170168-jp.png": "gb/170167-jp.png"}


def test_dedupe_works_across_games(tmp_path):
    (tmp_path / "gb").mkdir()
    for name in ("170167-jp", "170168-jp"):
        (tmp_path / "gb" / f"{name}.png").write_bytes(b"x")
    state = {"games": {"170168": {"system": "gb", "labels": ["gb/170168-jp.png"]},
                       "170167": {"system": "gb", "labels": ["gb/170167-jp.png"]}}}
    assert d.dedupe(state, out=str(tmp_path)) == 1
    assert state["games"]["170167"]["labels"] == ["gb/170167-jp.png"]
    assert state["games"]["170168"] == {"system": "gb", "labels": [], "same": {"gb/170168-jp.png": "gb/170167-jp.png"}}


def test_ignored_images_are_never_downloaded_and_removed_if_there(tmp_path):
    lst = tmp_path / "ignore.txt"
    lst.write_text("# ScreenScraper's mistakes\ngb\\82269-us.png  # a GBA label\n\n", encoding="utf-8")
    ignore = d.ignored(str(lst))
    assert ignore == {"82269-us.png"}  # by file name: --fix-systems may move it to gbc/
    medias = [{"type": "support-texture", "region": r, "url": "http://x/" + r, "format": "png", "md5": r} for r in ("us", "jp")]
    got = []
    assert d.save_textures("gb", "82269", {"medias": medias}, lambda u, n: got.append(n), {}, ignore)[0] == ["gb/82269-jp.png"]
    (tmp_path / "gb").mkdir()
    (tmp_path / "gb" / "82269-us.png").write_bytes(b"x")
    state = {"games": {"82269": {"system": "gb", "labels": ["gb/82269-jp.png", "gb/82269-us.png"]}}}
    assert d.drop_ignored(state, ignore, out=str(tmp_path)) == 1
    assert state["games"]["82269"]["labels"] == ["gb/82269-jp.png"] and not (tmp_path / "gb" / "82269-us.png").exists()


def test_a_game_is_filed_under_its_own_system():
    medias = [{"type": "support-texture", "region": "jp", "url": "http://x/1", "format": "png", "md5": "a"}]
    call = fake({("jeuRecherche.php", "Hole In One Golf"): {"response": {"jeux": [
        {"id": "82269", "systeme": {"id": "10"}, "medias": medias, "dates": [{"region": "jp"}]},
        {"id": "5", "systeme": {"id": "46"}, "medias": medias, "dates": [{"region": "jp"}]}]}}})
    state, got = {"games": {}, "searched": []}, []
    d.run([("gb", "Hole In One Golf")], {}, state, 5, call=call, fetch=lambda u, n: got.append(n))
    assert got == ["gbc/82269-jp.png"] and state["games"]["82269"]["system"] == "gbc" and "5" not in state["games"]


def test_an_ignored_game_loses_all_its_images(tmp_path):
    (tmp_path / "gb").mkdir()
    for n in ("82189-eu", "82189-c"):
        (tmp_path / "gb" / f"{n}.png").write_bytes(n.encode())
    state = {"games": {"82189": {"system": "gb", "labels": ["gb/82189-eu.png", "gb/82189-c.png"], "checked": True}}}
    assert d.drop_ignored(state, {"82189"}, out=str(tmp_path)) == 2
    assert state["games"]["82189"] == {"system": "gb", "labels": [], "excluded": "listed in ignore.txt"}
    call = fake({("jeuRecherche.php", "X"): {"response": {"jeux": [{"id": "82188", "noms": [{"text": "X"}]}]}}})
    s2 = {"games": {}, "searched": []}
    assert d.run([("gb", "X")], {}, s2, 5, call=call, ignore={"82188"}) == 1 and s2["games"]["82188"]["excluded"] == "listed in ignore.txt"


def test_fix_systems_moves_gbc_games_out_of_gb():
    state = {"games": {"82269": {"system": "gb", "labels": ["gb/82269-jp.png"], "same": {"gb/82269-us.png": "gb/82269-jp.png"}},
                       "1": {"system": "gb", "labels": ["gb/1-us.png"]}, "2": {"system": "gba", "labels": ["gba/2-us.png"]}},
             "md5": {"a": "gb/82269-jp.png", "b": "gb/1-us.png"}}
    answers = {82269: {"systeme": {"id": "10"}}, 1: {"systeme": {"id": "9"}}}
    moves = []
    used, moved = d.fix_systems(state, {}, 10, call=lambda e, c, **p: {"response": {"jeu": answers[p["gameid"]]}},
                                move=lambda a, b: moves.append((a, b)))
    assert (used, moved) == (2, 1) and moves == [("gb/82269-jp.png", "gbc/82269-jp.png")]
    g = state["games"]["82269"]
    assert g["system"] == "gbc" and g["labels"] == ["gbc/82269-jp.png"] and g["same"] == {"gbc/82269-us.png": "gbc/82269-jp.png"}
    assert state["md5"] == {"a": "gbc/82269-jp.png", "b": "gb/1-us.png"} and state["games"]["1"]["system_checked"]
    assert d.fix_systems(state, {}, 10, call=None) == (0, 0)


def test_dedupe_survives_an_image_listed_twice(tmp_path):
    (tmp_path / "gba").mkdir()
    for n in ("3820-jp", "3820-tw"):
        (tmp_path / "gba" / f"{n}.png").write_bytes(b"x")
    state = {"games": {"3820": {"system": "gba", "labels": ["gba/3820-jp.png", "gba/3820-tw.png", "gba/3820-tw.png"]}}}
    assert d.dedupe(state, out=str(tmp_path)) == 1
    assert state["games"]["3820"]["labels"] == ["gba/3820-jp.png"] and state["games"]["3820"]["same"] == {"gba/3820-tw.png": "gba/3820-jp.png"}


def test_e_reader_cards_are_not_cartridges(tmp_path):
    assert d.e_reader(["Super Mario Advance 4 Card-e"]) and d.e_reader(["Ice Climber-e"]) and d.e_reader(["Rockman EXE 4 Card-e+"])
    assert not d.e_reader(["Super Mario Advance 4", "Pokemon - Edition Rouge", "Tetris"])
    assert d.verdict({**OFFICIAL, "noms": [{"region": "us", "text": "Ice Climber-e"}]}) == "e-Reader cards, not a cartridge"
    (tmp_path / "gba").mkdir()
    (tmp_path / "gba" / "140755-us.png").write_bytes(b"x")
    state = {"games": {"140755": {"system": "gba", "names": ["Ice Climber-e"], "labels": ["gba/140755-us.png"], "checked": True}}}
    assert d.drop_cards(state, out=str(tmp_path)) == 1 and not (tmp_path / "gba" / "140755-us.png").exists()
    assert state["games"]["140755"]["excluded"] == "e-Reader cards, not a cartridge"


def test_variants_keep_the_title_as_written():
    assert d.variants("10-Pin Bowling") == ["10-Pin Bowling", "10 Pin Bowling"]
    assert d.variants("Legend of Zelda, The - Oracle of Ages") == ["Legend of Zelda - Oracle of Ages", "Legend of Zelda", "Legend of Zelda The Oracle of Ages"]
    assert d.variants("お茶犬の大冒険") == []


def test_missing_titles_try_gb_and_gbc_both(tmp_path):
    w = tmp_path / "wanted.json"
    w.write_text(json.dumps([{"system": "cgb", "title": "10-Pin Bowling"}, {"system": "agb", "title": "Yoshi"}]), encoding="utf-8")
    assert d.missing_titles(str(w)) == [("gbc", "10-Pin Bowling"), ("gb", "10-Pin Bowling"), ("gbc", "10 Pin Bowling"),
                                         ("gb", "10 Pin Bowling"), ("gba", "Yoshi")]
