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
                 ("jeuInfos.php", 7): {"response": {"jeu": {"medias": medias}}}})
    state, fetched = {"games": {}, "searched": []}, []
    used = d.run([("gb", "Tetris")], {}, state, 100, call=call, fetch=lambda u, n: fetched.append((u, n)))
    assert used == 2 and fetched == [("http://x/1", "gb/7-eu.png"), ("http://x/2", "gb/7-us.png")]
    assert state["games"]["7"] == {"system": "gb", "names": ["Tetris"], "labels": ["gb/7-eu.png", "gb/7-us.png"]}
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
    call = fake({("jeuRecherche.php", "Tetris"): {"response": {"jeux": [{"id": "7", "medias": medias}]}}})
    state = {"games": {}, "searched": []}
    d.run([("gb", "Tetris")], {}, state, 5, call=call, fetch=lambda u, n: u != "http://x/1" and None)
    assert state["games"]["7"]["labels"] == ["gb/7-us.png"] and state["searched"] == ["gb|tetris"]


def test_inspect_leaves_out_medias_and_links():
    import screenscraper_inspect as i
    assert i.strip({"id": "7", "medias": [1], "x": [{"url": "https://a?ssid=me", "k": "v"}]}) == {"id": "7", "x": [{"k": "v"}]}
