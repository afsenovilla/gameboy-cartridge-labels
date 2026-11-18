import screenscraper_sample as s


def test_support_images_keeps_only_cartridge_images():
    game = {"medias": [{"type": "support-2D", "region": "eu", "url": "http://x/a", "format": "png"},
                       {"type": "box-2D", "region": "eu", "url": "http://x/b", "format": "png"},
                       {"type": "support-2D", "url": "http://x/c"}]}
    assert s.support_images(game) == [("eu", "http://x/a", "png"), ("xx", "http://x/c", "png")]
