import numpy as np
import prints


def alike_matrix(n, tiles, differ=()):
    """All alike, except: for (members, tile range) in differ, those members unlike the rest on those tiles."""
    A = np.ones((n, n, tiles), bool)
    for members, ts in differ:
        for i in range(n):
            for j in range(n):
                if (i in members) != (j in members):
                    A[i, j, ts] = False
    return A


def test_a_revision_on_several_tiles_splits_the_family():
    A = alike_matrix(4, 50, [({2, 3}, slice(10, 15))])
    groups, poor, differs = prints.split_family(list("abcd"), A, [None] * 4, np.ones((4, 50), bool))
    assert sorted(sorted(g) for g in groups) == [[0, 1], [2, 3]]
    assert differs[10:15].all() and not differs[:10].any()


def test_a_split_on_too_few_tiles_or_flat_tiles_doesnt():
    A = alike_matrix(4, 50, [({2, 3}, slice(10, 12))])            # two tiles only
    assert len(prints.split_family(list("abcd"), A, [None] * 4, np.ones((4, 50), bool))[0]) == 1
    A = alike_matrix(4, 50, [({2, 3}, slice(10, 15))])
    flat = np.ones((4, 50), bool); flat[:, 10:15] = False             # the differing tiles flat
    assert len(prints.split_family(list("abcd"), A, [None] * 4, flat)[0]) == 1


def test_a_defect_on_one_sticker_doesnt_split():
    A = alike_matrix(3, 50, [({2}, slice(0, 20))])                    # one photo off on many tiles: dirt, glare
    groups, poor, _ = prints.split_family(list("abc"), A, [None] * 3, np.ones((3, 50), bool))
    assert len(groups) == 1


def test_different_releases_are_different_prints():
    A = alike_matrix(2, 50)
    groups, _, _ = prints.split_family(list("ab"), A, ["dmg-1", "dmg-2"], np.ones((2, 50), bool))
    assert len(groups) == 2


def test_a_poor_fit_is_judged_against_its_own_release_only():
    A = alike_matrix(4, 50, [({3}, slice(0, 40))])
    groups, poor, _ = prints.split_family(list("abcd"), A, ["r"] * 4, np.ones((4, 50), bool))
    assert poor == [3]
    groups, poor, _ = prints.split_family(list("abcd"), A, ["r1", "r2", "r3", "r4"], np.ones((4, 50), bool))
    assert poor == []


def test_two_prints_of_a_family_get_a_pair_image():
    # prints 0 (members 0, 1) and 1 (members 2, 3) alike on the first 30 of 50 tiles: worth pooling
    A = alike_matrix(4, 50, [({2, 3}, slice(30, 50))])
    masks = prints.pair_masks([[0, 1], [2, 3]], A)
    assert list(masks) == [(0, 1)] and masks[(0, 1)][:30].all() and not masks[(0, 1)][30:].any()


def test_with_three_prints_tiles_all_of_them_share_dont_count():
    # three prints alike only on a frame (the first 10 tiles): no pair worth an image
    A = alike_matrix(6, 50, [({2, 3}, slice(10, 50)), ({4, 5}, slice(10, 50))])
    A[0:2, 4:6, 10:] = A[4:6, 0:2, 10:] = False
    assert prints.pair_masks([[0, 1], [2, 3], [4, 5]], A) == {}
