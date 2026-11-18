import json
import build_site


def test_build_site_embeds_the_labels_and_escapes_script_ends(tmp_path):
    (tmp_path / "labels.json").write_text(json.dumps([
        {"id": "a", "serial": "DMG-X-USA", "release": "DMG-X", "title": "</script> Tetris", "system": "dmg",
         "file": "a.avif", "size": [10, 20], "photos": 3}]), encoding="utf-8")
    out, n = build_site.build(str(tmp_path))
    page = open(out, encoding="utf-8").read()
    assert n == 1 and "DMG-X-USA" in page and "<\\/script> Tetris" in page
    assert page.count("</script>") == 2   # the data block's and the page script's: none from the title


def test_a_label_with_no_title_or_serial_shows_under_what_it_has(tmp_path):
    (tmp_path / "labels.json").write_text(json.dumps([
        {"id": "a-x", "serial": None, "release": "AGB-X", "title": None, "system": "agb", "file": "a.avif", "size": None, "photos": 3}]),
        encoding="utf-8")
    out, _ = build_site.build(str(tmp_path))
    page = open(out, encoding="utf-8").read()
    assert '"title":"AGB-X"' in page and '"serial":"AGB-X"' in page
