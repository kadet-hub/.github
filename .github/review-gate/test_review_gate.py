import json
import os
import re
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import review_gate

WORKFLOW = os.path.join(HERE, "..", "workflows", "review-gate.yml")


class Decide(unittest.TestCase):  # RG-1
    def test_fixtures(self):
        with open(os.path.join(HERE, "fixtures.json")) as f:
            cases = json.load(f)
        for case in cases:
            with self.subTest(case["name"]):
                reviewers = case.get("reviewers", ["neat-bot"])
                reasons = review_gate.decide(case["author"], case["head"], case["reviews"], lambda login, write=case["write"]: login in write, reviewers)
                self.assertEqual(not reasons, case["pass"], reasons)

    def test_write_access_asked_only_for_change_requests(self):
        asked = []
        reviews = [
            {"user": {"login": "neat-bot"}, "state": "APPROVED", "commit_id": "a"},
            {"user": {"login": "Moep90"}, "state": "APPROVED", "commit_id": "a"},
            {"user": {"login": "drive-by"}, "state": "CHANGES_REQUESTED", "commit_id": "a"},
        ]
        review_gate.decide("kadet-hub-agent[bot]", "a", reviews, lambda login: asked.append(login) or False, ["neat-bot"])
        self.assertEqual(asked, ["drive-by"])

    def test_review_of_a_deleted_account(self):
        reviews = [
            {"user": None, "state": "CHANGES_REQUESTED", "commit_id": "a"},
            {"user": {"login": "neat-bot"}, "state": "APPROVED", "commit_id": "a"},
        ]
        self.assertEqual(review_gate.decide("kadet-hub-agent[bot]", "a", reviews, lambda login: True, ["neat-bot"]), [])


class Workflow(unittest.TestCase):  # RG-2
    def test_read_only_and_pinned(self):
        with open(WORKFLOW) as f:
            text = f.read()
        permissions = re.findall(r"^\s+([a-z-]+): (read|write|none)$", text, re.M)
        self.assertEqual(permissions, [("pull-requests", "read")])
        self.assertIn("permissions: {}", text)
        self.assertNotIn("checkout", text)
        self.assertNotIn("uses:", text)
        self.assertIn("GATE_SHA: ${{ job.workflow_sha }}", text)
        self.assertIn("contents/.github/review-gate/review_gate.py?ref=$GATE_SHA", text)


if __name__ == "__main__":
    unittest.main()
