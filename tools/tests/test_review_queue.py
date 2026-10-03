from __future__ import annotations

import unittest

from tools import review_queue
from tools import catalog


class ReviewQueueTests(unittest.TestCase):
    def test_queue_matches_complete_local_inventory(self) -> None:
        report = review_queue.load_queue()
        self.assertEqual(601, report["localArticleCount"])
        self.assertEqual(601, len(report["articles"]))
        self.assertEqual(601, len({row["articleId"] for row in report["articles"]}))
        self.assertEqual(601, len({row["classType"] for row in report["articles"]}))
        self.assertTrue(all(row["sourceCount"] > 0 for row in report["articles"]))
        self.assertTrue(all(row["editorialState"] == "in_review" for row in report["articles"]))
        for row in report["articles"]:
            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / (row["articleId"] + ".json"))
            self.assertEqual(ledger["state"], row["researchState"])
            self.assertIn(row["researchState"], {"fact_checked", "source_reviewed"})
            if row["researchState"] == "source_reviewed":
                self.assertEqual("0.38.0", ledger["baseline"]["comfyui"])
                self.assertFalse(ledger["checks"]["exampleExecuted"])
                self.assertIn("Требуется человеческое утверждение", ledger["knownGaps"])

    def test_single_article_markdown_exposes_honest_review_state(self) -> None:
        text = review_queue.markdown(review_queue.load_queue(), "core.ksampler-advanced")
        self.assertIn("KSamplerAdvanced", text)
        self.assertIn("Автоматическое утверждение запрещено", text)
        self.assertIn("Перед утверждением закрыть", text)
        self.assertIn("recipe.advanced-sampling-external-vae", text)


if __name__ == "__main__":
    unittest.main()
