import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
import gbdb_fetch as g

HTML = '''<a href="https://www.game-boy-database.com/game-ACDX-453-EUR.html"><img></a>
<a href="https://www.game-boy-database.com/game-ACDX-5104-EUR.html">Cool Hand</a>
<a href="game-ALAP-73-EUR-1.html">x</a><a href="game-ALAP-73-EUR-1.html">again</a>
<a href="game-K2J-900-JPN.html">x</a><a href="game-AG-12-UKV.html">x</a><a href="game-QC-7-NOE.html">x</a>'''


def test_region_lists_give_serials_and_page_ids():
    assert g.releases(HTML) == [("DMG-ACDX-EUR", "453"), ("DMG-ACDX-EUR", "5104"), ("DMG-ALAP-EUR-1", "73"),
                                ("DMG-K2J-JPN", "900"), ("DMG-AG-UKV", "12"), ("DMG-QC-NOE", "7")]


def test_only_serials_without_a_label_missing_first_at_most_two_each():
    found = g.releases(HTML)
    jobs = g.todo(found, have={"DMG-AG-UKV"}, missing={"DMG-K2J", "DMG-QC-NOE"})
    assert jobs == [("DMG-K2J", "900", "missing"), ("DMG-QC-NOE", "7", "missing"),
                    ("DMG-ACDX-EUR", "453", "variant"), ("DMG-ACDX-EUR", "5104", "variant"), ("DMG-ALAP-EUR-1", "73", "variant")]
    assert [j[0] for j in g.todo(found, {"DMG-AG-UKV"}, {"DMG-QC-NOE"}, missing_only=True)] == ["DMG-QC-NOE"]
    assert g.todo(found, set(), set(), fetched={"453", "5104", "73", "900", "12", "7"}) == []
