from __future__ import annotations

import unittest

from tools import review_queue


class ReviewQueueTests(unittest.TestCase):
    def test_queue_matches_complete_local_inventory(self) -> None:
        report = review_queue.load_queue()
        self.assertEqual(601, report["localArticleCount"])
        self.assertEqual(601, len(report["articles"]))
        self.assertEqual(601, len({row["articleId"] for row in report["articles"]}))
        self.assertEqual(601, len({row["classType"] for row in report["articles"]}))
        self.assertTrue(all(row["sourceCount"] > 0 for row in report["articles"]))
        self.assertTrue(all(row["editorialState"] == "in_review" for row in report["articles"]))
        self.assertTrue(all(row["researchState"] == "fact_checked" for row in report["articles"]))

    def test_single_article_markdown_exposes_honest_review_state(self) -> None:
        text = review_queue.markdown(review_queue.load_queue(), "core.ksampler-advanced")
        self.assertIn("KSamplerAdvanced", text)
        self.assertIn("Автоматическое утверждение запрещено", text)
        self.assertIn("Перед утверждением закрыть", text)
        self.assertIn("recipe.advanced-sampling-external-vae", text)


if __name__ == "__main__":
    unittest.main()
