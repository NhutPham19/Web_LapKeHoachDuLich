import unittest
from pathlib import Path

from scripts.evaluate_holdout import evaluate_models


class TestHoldoutEvaluation(unittest.TestCase):
    def test_evaluate_models_holdout(self):
        results = evaluate_models()
        self.assertIn("dataset", results)
        self.assertIn("rating_prediction", results)
        self.assertIn("ranking_evaluation", results)

        rp = results["rating_prediction"]
        self.assertIn("Hybrid_Recommendation", rp)
        self.assertIn("Item_Mean_Baseline", rp)

        # Hybrid model must achieve lower RMSE and MAE than baseline
        self.assertLess(rp["Hybrid_Recommendation"]["RMSE"], rp["Item_Mean_Baseline"]["RMSE"])
        self.assertLess(rp["Hybrid_Recommendation"]["MAE"], rp["Item_Mean_Baseline"]["MAE"])

        # Check ranking metrics
        rk = results["ranking_evaluation"]
        self.assertIn("hybrid", rk)
        self.assertGreater(rk["hybrid"]["NDCG@3"], 0.85)


if __name__ == "__main__":
    unittest.main()
