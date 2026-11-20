import unittest
from urllib.parse import urlparse,parse_qs
from feedback import issue_url

class FeedbackTests(unittest.TestCase):
    def test_unicode_draft_is_encoded_for_the_author_repository(self):
        url=issue_url('bug','Не підключається','Опис & кроки #1')
        parsed=urlparse(url)
        self.assertEqual(parsed.netloc,'github.com')
        self.assertEqual(parsed.path,'/wertalya/BluettiWidget/issues/new')
        query=parse_qs(parsed.query)
        self.assertEqual(query['title'],['[Bug] Не підключається'])
        self.assertIn('Опис & кроки #1',query['body'][0])
        self.assertNotIn('Модель',query['body'][0])

    def test_optional_context_only_accepts_model_profile_keys(self):
        body=parse_qs(urlparse(issue_url('idea','Ідея','Опис','AC180P')).query)['body'][0]
        self.assertIn('Модель: AC180P',body)
        with self.assertRaises(ValueError):
            issue_url('bug','Title','Body','AC180P123456789')

if __name__=='__main__': unittest.main()
