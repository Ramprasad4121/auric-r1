"""Pure tests: solver, MUS, header parsing, reply parsing, decision logic.
No network, no model. Run: python3 -m pytest -q  (or python3 tests/test_solver.py)"""
import json
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "src"))

from auric.decide import decide, plausibility  # noqa: E402
from auric.extract import canon, parse_reply  # noqa: E402
from auric.parse import parse_header, split_item  # noqa: E402
from auric.solver import (ConstraintError, Header, enumerate_rotas,  # noqa: E402
                          holds, minimal_unsat_subsets, solve, validate)

H = Header(people=["A", "B", "C", "D", "E"], blocks=["07:00", "09:00", "11:00", "13:00", "15:00"],
           stations=["intake", "calibration", "packing"], station_people=["A", "C", "E"])


def items():
    with open(os.path.join(ROOT, "data", "items.json")) as f:
        return json.load(f)


class TestEnumerate(unittest.TestCase):
    def test_count(self):
        self.assertEqual(len(enumerate_rotas(H)), 120 * 6)

    def test_answer_shape(self):
        r = enumerate_rotas(H)[0]
        a = r.to_answer(H)
        self.assertEqual(set(a), set(H.people))
        self.assertIn("station", a["A"])
        self.assertNotIn("station", a["B"])


class TestSemantics(unittest.TestCase):
    def setUp(self):
        self.rotas = enumerate_rotas(H)

    def count(self, *cs):
        return len(solve(H, list(cs), self.rotas))

    def test_at(self):
        self.assertEqual(self.count({"type": "at", "who": "A", "block": "07:00"}), 24 * 6)

    def test_not_at(self):
        self.assertEqual(self.count({"type": "not_at", "who": "A", "block": "07:00"}), 96 * 6)

    def test_station(self):
        self.assertEqual(self.count({"type": "on", "who": "A", "station": "intake"}), 120 * 2)
        self.assertEqual(self.count({"type": "not_on", "who": "A", "station": "intake"}), 120 * 4)

    def test_before_is_strict_and_halves(self):
        self.assertEqual(self.count({"type": "before", "a": "A", "b": "B"}), 60 * 6)

    def test_next(self):
        # A immediately before B: 4 adjacent slots * 3! others
        self.assertEqual(self.count({"type": "next", "a": "A", "b": "B"}), 4 * 6 * 6)

    def test_between_either_order(self):
        # M strictly between two others: 1/3 of orderings
        self.assertEqual(self.count({"type": "between", "mid": "C", "ends": ["A", "B"]}), 40 * 6)

    def test_station_reference(self):
        c = {"type": "before", "a": "@packing", "b": "B"}
        for r in self.rotas:
            holder = [p for p, s in r.station if s == "packing"][0]
            b = r.block_of()
            self.assertEqual(holds(H, r, c), H.blocks.index(b[holder]) < H.blocks.index(b["B"]))

    def test_station_reference_self_is_false(self):
        # "A is later than whoever has packing" is false when A has packing
        c = {"type": "before", "a": "@packing", "b": "A"}
        for r in self.rotas:
            if r.station_of()["A"] == "packing":
                self.assertFalse(holds(H, r, c))


class TestValidate(unittest.TestCase):
    def test_rejects_unknown(self):
        for c in [{"type": "at", "who": "Z", "block": "07:00"},
                  {"type": "at", "who": "A", "block": "08:00"},
                  {"type": "on", "who": "B", "station": "nope"},
                  {"type": "before", "a": "A", "b": "A"},
                  {"type": "between", "mid": "A", "ends": ["A", "B"]},
                  {"type": "frobnicate"}]:
            with self.assertRaises(ConstraintError):
                validate(H, c)


class TestMUS(unittest.TestCase):
    def test_three_cycle(self):
        cs = [{"type": "before", "a": "A", "b": "B"},
              {"type": "before", "a": "B", "b": "C"},
              {"type": "before", "a": "C", "b": "A"},
              {"type": "at", "who": "D", "block": "07:00"}]
        self.assertEqual(solve(H, cs), [])
        self.assertEqual(minimal_unsat_subsets(H, cs), [(0, 1, 2)])

    def test_multiple_muses_and_minimality(self):
        cs = [{"type": "not_on", "who": "A", "station": "intake"},
              {"type": "not_on", "who": "A", "station": "calibration"},
              {"type": "not_on", "who": "A", "station": "packing"},
              {"type": "on", "who": "A", "station": "intake"}]
        muses = minimal_unsat_subsets(H, cs)
        self.assertIn((0, 3), muses)
        self.assertIn((0, 1, 2), muses)
        for m in muses:  # every MUS is UNSAT and every proper subset SAT
            self.assertEqual(solve(H, [cs[i] for i in m]), [])
            for drop in m:
                self.assertTrue(solve(H, [cs[i] for i in m if i != drop]))


class TestDecide(unittest.TestCase):
    def test_unique(self):
        cs = [("a", {"type": "at", "who": p, "block": b}) for p, b in zip(H.people, H.blocks)]
        cs += [("s", {"type": "on", "who": "A", "station": "intake"}),
               ("t", {"type": "on", "who": "C", "station": "packing"})]
        ans = decide(H, cs)
        self.assertEqual(ans["case"], "unique")
        self.assertEqual(ans["assignment"]["E"], {"block": "15:00", "station": "calibration"})

    def test_inconsistent_cites_verbatim_lines(self):
        cs = [("L1", {"type": "before", "a": "A", "b": "B"}),
              ("L2", {"type": "before", "a": "B", "b": "C"}),
              ("L3", {"type": "before", "a": "C", "b": "A"}),
              ("L4", {"type": "at", "who": "D", "block": "07:00"})]
        ans = decide(H, cs)
        self.assertEqual(ans["case"], "inconsistent")
        self.assertEqual(sorted(ans["conflicts"]), ["L1", "L2", "L3"])

    def test_plausibility_priors(self):
        self.assertLess(plausibility({"_diag": {"n_solutions": 30}}), 1)
        self.assertEqual(plausibility({"_diag": {"n_solutions": 3}}), 1)
        self.assertLess(plausibility({"_diag": {"n_solutions": 0, "mus_sizes": [2]}}), 1)


class TestHeader(unittest.TestCase):
    def test_all_visible_headers(self):
        for it in items():
            h = parse_header(split_item(it["text"])[0])
            self.assertEqual(len(h.people), it["n_staff"])
            self.assertEqual(len(h.stations), it["n_stations"])
            self.assertEqual(len(h.blocks), len(h.people))
            self.assertTrue(set(h.station_people) <= set(h.people))

    def test_b2_002_known_unique(self):
        """Gold extraction of B2-002 through the solver gives the known rota."""
        from auric.regex_baseline import extract
        it = [i for i in items() if i["id"] == "B2-002"][0]
        head, lines = split_item(it["text"])
        h = parse_header(head)
        cs = [(l, extract(h, l, "declined")) for l in lines]
        ans = decide(h, [x for x in cs if x[1]])
        self.assertEqual(ans["case"], "unique")
        self.assertEqual(ans["assignment"], {
            "Daniel": {"block": "11:00", "station": "intake"},
            "Rohan": {"block": "09:00", "station": "packing"},
            "Nadia": {"block": "13:00"},
            "Priya": {"block": "15:00"},
            "Meera": {"block": "07:00", "station": "calibration"}})


class TestReplyParser(unittest.TestCase):
    def test_strict_and_rambling(self):
        reply = ("1 | x | A AT 09:00\n"
                 "2 | social | NONE\n"
                 "3 | packing earlier | [packing] BEFORE B\n"
                 "4 | between | C BETWEEN A AND B\n"
                 "5 | hmm | B JUST_BEFORE A (Note: wait, it says A then B, so A JUST_BEFORE B)\n"
                 "6 | garbage | Z AT 09:00\n")
        p = parse_reply(H, reply, 7)
        self.assertEqual(p[0], ("ok", {"type": "at", "who": "A", "block": "09:00"}))
        self.assertEqual(p[1], ("none", None))
        self.assertEqual(p[2][1], {"type": "before", "a": "@packing", "b": "B"})
        self.assertEqual(canon(p[3][1]), canon({"type": "between", "mid": "C", "ends": ["B", "A"]}))
        self.assertEqual(p[4][1], {"type": "next", "a": "A", "b": "B"})  # last fact wins
        self.assertEqual(p[5][0], "bad")
        self.assertNotIn(6, p)

    def test_between_inside_prose(self):
        b = "1 | C between A and B either order | C BETWEEN A AND B (same as 10)\n"
        p = parse_reply(H, b, 1)
        self.assertEqual(p[0], ("ok", {"type": "between", "mid": "C", "ends": ["A", "B"]}))


if __name__ == "__main__":
    unittest.main()
