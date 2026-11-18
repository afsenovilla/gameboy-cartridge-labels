import json
import tradera_photos as t


def test_page_listings_reads_the_items_of_a_category_page():
    payload = 'xx{"items":[{"name":"crumb"}],"totalItemCount":2334,"items":[{"itemId":761974115,"price":441,"shortDescription":"Pokémon Blue \\"Version\\"","imageUrlTemplate":"https://img.tradera.net/{format}/863/a.jpg","itemUrl":"https://www.tradera.com/item/1","categoryId":300201,"x":{"y":[1,2]}},{"itemId":2,"shortDescription":"b"}],"other":1}'
    script = "self.__next_f.push(" + json.dumps([1, payload]) + ")"
    html = f"<html><script>var a=1</script><script>{script}</script></html>"
    total, items = t.page_listings(html)
    assert total == 2334
    assert items[0] == {"itemId": 761974115, "shortDescription": 'Pokémon Blue "Version"',
                        "imageUrlTemplate": "https://img.tradera.net/{format}/863/a.jpg",
                        "itemUrl": "https://www.tradera.com/item/1", "categoryId": 300201}
    assert [i["itemId"] for i in items] == [761974115, 2]
