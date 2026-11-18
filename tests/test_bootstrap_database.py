import bootstrap_database as b, serials


def test_releases_from_an_index_work_as_the_serials_database(tmp_path):
    index = {"prints": {
        "AGB-A2AE-USA-dan": {"serial": "AGB-A2AE-USA", "release": "AGB-A2AE", "title": "Disney Sports : Basketball", "shape": "agb"},
        "AGB-A2AE-EUR-x": {"serial": "AGB-A2AE-EUR", "release": "AGB-A2AE", "title": "Disney Sports : Basketball", "shape": "agb"},
        "unknown-1": {"serial": None, "release": None, "title": None, "shape": "dmg"},
        "AGB-0488-mike": {"serial": "agb-0488", "release": "agb-0488", "title": "Disney Sports - Soccer", "shape": "agb"}}}
    releases = b.releases_of(index)
    assert [r["id"] for r in releases] == ["AGB-A2AE", "agb-0488"]
    assert releases[0]["cartridgeSerials"] == ["AGB-A2AE-USA", "AGB-A2AE-EUR"]
    import json
    path = tmp_path / "releases.json"
    path.write_text(json.dumps(releases), encoding="utf-8")
    db = serials.load_database(str(path))
    assert serials.release("AGB-A2AE-USA", db)["title"] == "Disney Sports : Basketball"
    assert serials.release("DIS-AGB-A2AE-USA", db)["id"] == "AGB-A2AE"
