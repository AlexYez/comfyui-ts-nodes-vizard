from __future__ import annotations

import unittest

from tools import review_queue
from tools import catalog


class ReviewQueueTests(unittest.TestCase):
    def test_queue_matches_complete_local_inventory(self) -> None:
        report = review_queue.load_queue()
        self.assertEqual("runtime/comfyui-0.45.0.object-info.json", report["inventorySource"])
        self.assertEqual(695, report["localArticleCount"])
        self.assertEqual(695, len(report["articles"]))
        self.assertEqual(695, len({row["articleId"] for row in report["articles"]}))
        self.assertEqual(695, len({row["classType"] for row in report["articles"]}))
        self.assertTrue(all(row["sourceCount"] > 0 for row in report["articles"]))
        self.assertTrue(all(row["editorialState"] == "in_review" for row in report["articles"]))
        for row in report["articles"]:
            ledger = catalog.load_json(catalog.CONTENT / "research/reviews" / (row["articleId"] + ".json"))
            self.assertEqual(ledger["state"], row["researchState"])
            self.assertIn(row["researchState"], {"fact_checked", "source_reviewed"})
            if row["researchState"] == "source_reviewed":
                commits = {"0.37.0": "73c9bad4d21e7addbe1d13bc92eee0f1431b017d", "0.38.0": "6b747c0428c343e1417219641db93a4fb7cb69ae", "0.43.0": "426f5eea52a7ece1dd599fff4cb6cd1f352ddd24"}
                commits["0.45.0"] = "989d93d0d968e704c589ce0146bb18c77f6b50cc"
                self.assertEqual(commits[ledger["baseline"]["comfyui"]], ledger["baseline"]["sourceCommit"])
                self.assertFalse(ledger["checks"]["exampleExecuted"])
                self.assertTrue(any("human" in gap.lower() or "человеческое утверждение" in gap for gap in ledger["knownGaps"]))

    def test_single_article_markdown_exposes_honest_review_state(self) -> None:
        text = review_queue.markdown(review_queue.load_queue(), "core.ksampler-advanced")
        self.assertIn("KSamplerAdvanced", text)
        self.assertIn("Автоматическое утверждение запрещено", text)
        self.assertIn("Перед утверждением закрыть", text)
        self.assertIn("recipe.advanced-sampling-external-vae", text)


if __name__ == "__main__":
    unittest.main()
