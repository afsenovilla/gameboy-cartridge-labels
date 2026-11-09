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


def differ_matrix(n, tiles, differ=()):
    """Different nowhere, except: for (members, tile range) in differ, those members different from the rest there."""
    return ~alike_matrix(n, tiles, differ)


def test_different_text_on_a_few_tiles_splits_the_family():
    D = differ_matrix(4, 50, [({2, 3}, slice(10, 13))])            # a region code: three tiles
    groups, differs = prints.split_family(~D, D)
    assert sorted(sorted(g) for g in groups) == [[0, 1], [2, 3]]
    assert differs[10:13].all() and not differs[:10].any()


def test_a_single_label_photo_with_other_text_is_a_print_of_its_own():
    D = differ_matrix(3, 50, [({2}, slice(10, 13))])
    assert sorted(sorted(g) for g in prints.split_family(~D, D)[0]) == [[0, 1], [2]]


def test_a_speck_on_one_or_two_tiles_doesnt_split():
    D = differ_matrix(3, 50, [({2}, slice(10, 12))])
    assert len(prints.split_family(~D, D)[0]) == 1


def test_one_dirty_label_photo_doesnt_split_a_print_whose_others_agree():
    # 0-3 one print; 3 differs from 1 only (a smudge on one of them): most cross pairs agree, one print
    D = differ_matrix(4, 50)
    D[1, 3, 10:14] = D[3, 1, 10:14] = True
    assert len(prints.split_family(~D, D)[0]) == 1


def test_two_prints_of_a_family_get_a_pair_image():
    # prints 0 (members 0, 1) and 1 (members 2, 3) alike on the first 30 of 50 tiles: worth pooling
    A = alike_matrix(4, 50, [({2, 3}, slice(30, 50))])
    masks = prints.pair_masks([[0, 1], [2, 3]], A)
    assert list(masks) == [(0, 1)] and masks[(0, 1)][:30].all() and not masks[(0, 1)][30:].any()


def test_region_variants_alike_nearly_everywhere_all_pool_with_each_other():
    A = alike_matrix(6, 50, [({2, 3}, slice(10, 13)), ({4, 5}, slice(20, 23))])
    A[0:2, 4:6, 10:13] = A[4:6, 0:2, 10:13] = False
    masks = prints.pair_masks([[0, 1], [2, 3], [4, 5]], A)
    assert sorted(masks) == [(0, 1), (0, 2), (1, 2)]


def test_prints_sharing_too_little_get_no_pair_image():
    A = alike_matrix(4, 50, [({2, 3}, slice(5, 50))])
    assert prints.pair_masks([[0, 1], [2, 3]], A) == {}
