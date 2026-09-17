#!/usr/bin/env python3
"""The meal path is reversible until one quote-bound human approval."""
import importlib.util, json, os, pathlib, sys, tempfile, time, unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("food_order_under_test", ROOT / "scripts" / "food_order.py")
fo = importlib.util.module_from_spec(SPEC); SPEC.loader.exec_module(fo)


class FoodOrderTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(); root = pathlib.Path(self.td.name)
        fo.ROOT = str(root / "memory" / "food-orders")
        fo.ORDERS = str(root / "memory" / "food-orders" / "proposals.json")
        fo.EVENTS = str(root / "memory" / "food-orders" / "events.jsonl")
        fo.LOCK = str(root / "memory" / "food-orders" / ".lock")
        fo.DD = str(root / "bin" / "dd-cli"); pathlib.Path(fo.DD).parent.mkdir(); pathlib.Path(fo.DD).write_text("stub")
        fo.PUBLIC_BASE = "http://test.invalid"
        self.sent = []; self.calls = []
        fo._notify = lambda rec, changed=False: self.sent.append((rec["id"], changed)) or {"state": "sent"}
        fo._notify_failure = lambda oid, error: self.sent.append((oid, "failed:" + error)) or {"state": "sent"}
        fo._choose = lambda kind, candidates, user, reply, count=1: (candidates[:count], "his bounded choice")
        self.quote_total = "$24.50"

        def cli(parts, intent, timeout=90):
            self.calls.append(tuple(parts)); key = tuple(parts[:2])
            if parts[0] == "search": return {"stores": [{"store_id": "s1", "name": "Warm Bowl"}]}
            if parts[0] == "menu": return {"menu_id": "m1", "items": [
                {"item_id": "i1", "name": "Rice bowl", "display_price": "$12"},
                {"item_id": "i2", "name": "Dumplings", "display_price": "$8"}]}
            if key == ("cart", "list"): return {"carts": []}
            if key == ("cart", "add-items"): return {"cart_uuid": "cart-1", "success": True}
            if key == ("order", "preview"): return {"quote": {
                "net_total_before_tip": {"display_string": self.quote_total},
                "delivery_availability": {"asap_minutes_range_string": "28-36 min"},
                "delivery_address": {"printable_address": "Saved home"},
                "store_order_cart": {"fulfillment_type": "DELIVERY"}}}
            if key == ("payment-method", "list"): return {"default_payment_method_id": "p1", "cards": [
                {"payment_method_id": "p1", "brand": "Visa", "last4": "4242"}]}
            if key == ("order", "checkout-url"): return {"checkout_url": "https://doordash.test/cart"}
            if key == ("order", "submit"): return {"order_uuid": "o1", "status": "submitted"}
            raise AssertionError(parts)
        fo._cli = cli

    def tearDown(self): self.td.cleanup()

    def test_trigger_is_explicit(self):
        self.assertTrue(fo.requested("Will you order us dinner?"))
        self.assertFalse(fo.requested("What should we have for dinner?"))
        self.assertFalse(fo.requested("Explain how DoorDash ordering works"))

    def test_proposal_review_and_single_submit(self):
        rec = fo.start("Please order us dinner", "I'll choose something warm.", "avatar", "turn-1")
        self.assertEqual("awaiting_approval", rec["state"]); self.assertEqual(2, len(rec["quote"]["items"]))
        self.assertEqual("$24.50", rec["quote"]["total"]); self.assertEqual("4242", rec["quote"]["card"]["last4"])
        self.assertEqual([(rec["id"], False)], self.sent)
        page = fo.review_html(rec["review_token"])
        self.assertIn("Warm Bowl", page); self.assertIn("28-36 min", page); self.assertIn("Approve and place order", page)
        result = fo.approve(rec["review_token"], 450)
        self.assertEqual("submitted", result["state"])
        submits = [x for x in self.calls if x[:2] == ("order", "submit")]
        self.assertEqual(1, len(submits)); self.assertIn("450", submits[0])
        again = fo.approve(rec["review_token"], 450)
        self.assertEqual("submitted", again["state"]); self.assertEqual(1, len([x for x in self.calls if x[:2] == ("order", "submit")]))

    def test_changed_quote_requires_fresh_approval(self):
        rec = fo.start("Order us lunch", "I have an idea.", "chat/full", "turn-2")
        old_token = rec["review_token"]; self.quote_total = "$27.10"
        result = fo.approve(old_token, 300)
        self.assertEqual("requote", result["state"])
        self.assertFalse(any(x[:2] == ("order", "submit") for x in self.calls))
        with open(fo.ORDERS) as f: fresh = next(iter(json.load(f).values()))
        self.assertNotEqual(old_token, fresh["review_token"]); self.assertEqual("$27.10", fresh["quote"]["total"])
        self.assertEqual((fresh["id"], True), self.sent[-1])

    def test_submit_failure_is_unknown_and_never_retried(self):
        rec = fo.start("Order us breakfast", "Breakfast it is.", "chat/full", "turn-3")
        base = fo._cli
        def fails(parts, intent, timeout=90):
            if tuple(parts[:2]) == ("order", "submit"): raise TimeoutError("wire went quiet")
            return base(parts, intent, timeout)
        fo._cli = fails
        result = fo.approve(rec["review_token"], 200)
        self.assertEqual("outcome_unknown", result["state"])
        again = fo.approve(rec["review_token"], 200)
        self.assertEqual("outcome_unknown", again["state"])

    def test_existing_cart_is_not_silently_extended(self):
        base = fo._cli
        def existing(parts, intent, timeout=90):
            if tuple(parts[:2]) == ("cart", "list"): return {"carts": [{"cart_uuid": "old"}]}
            return base(parts, intent, timeout)
        fo._cli = existing
        rec = fo.start("Please order us lunch", "Looking now.", "chat/full", "turn-4")
        self.assertEqual("failed", rec["state"]); self.assertIn("existing_cart_requires_review", rec["error"])
        self.assertFalse(any(x[:2] == ("cart", "add-items") for x in self.calls))

    def test_suite_is_isolated_and_sender_stubbed(self):
        self.assertTrue(fo.ROOT.startswith(self.td.name)); self.assertEqual("<lambda>", fo._notify.__name__)
        self.assertNotIn(os.path.expanduser("~/.vintos/workspace"), fo.ROOT)

    def test_runtime_wiring_is_manifested(self):
        server = (ROOT / "bin" / "server.py").read_text()
        deploy = (ROOT / "scripts" / "deploy-atelier.sh").read_text()
        self.assertIn('@app.get("/api/food-order/review/{token}")', server)
        self.assertIn('@app.post("/api/food-order/review/{token}/approve")', server)
        self.assertIn('"food_order"', server); self.assertIn("food_order.py", deploy)


if __name__ == "__main__": unittest.main()
