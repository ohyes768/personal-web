import unittest
from hot_albums import parse_qingting, parse_ximalaya, choose

class ParsingTests(unittest.TestCase):
    def test_qingting_rank_and_dedup(self):
        html = '<script>window.__initStores={"AttributeStore":{"FilterList":[{"id":1,"title":"A","category_id":1599,"playcount":"2万"},{"id":2,"title":"B","category_id":1599,"playcount":"1亿"},{"id":1,"title":"A","category_id":1599,"playcount":"2万"}]}}</script>'
        rows = choose(parse_qingting(html), 2, sort_plays=True)
        self.assertEqual([r['album_id'] for r in rows], ['2','1'])
    def test_qingting_rows_have_platform_age_evidence(self):
        html = '<script>window.__initStores={"AttributeStore":{"FilterList":[{"id":1,"title":"A","category_id":1599,"playcount":"2万"}]}}</script>'
        row = parse_qingting(html)[0]
        self.assertEqual(row['age_band'], '0-1岁')
        self.assertEqual(row['age_evidence'], '蜻蜓FM年龄筛选')
        self.assertEqual(row['age_confidence'], '高')
    def test_missing_data_fails(self):
        with self.assertRaises(ValueError): parse_qingting('<html>验证</html>')
        with self.assertRaises(ValueError): parse_ximalaya('<html>验证</html>')
    def test_ximalaya_only_children_rows(self):
        html = '<div class="album-item"><span class="album-index">01</span><a href="/album/123"><div class="title">故事</div><span class="user-category_title">儿童</span></a></div>'
        self.assertEqual(parse_ximalaya(html), [])
        explicit_age = html.replace('故事', '0-1岁宝宝听故事')
        self.assertEqual(parse_ximalaya(explicit_age)[0]['url'], 'https://www.ximalaya.com/album/123')

    def test_choose_allows_short_infant_candidates(self):
        rows = [{'platform': '蜻蜓FM', 'album_id': '1'}]
        self.assertEqual(choose(rows, 15, allow_short=True), rows)
    def test_short_results_fail(self):
        with self.assertRaises(ValueError): choose([],15)

if __name__ == '__main__': unittest.main()
