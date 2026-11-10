"""The evaluation code itself: label file integrity, scoring maths, grader comparison."""

import json
from datetime import date

import pytest

from src.evaluation.judge_eval import compare
from src.evaluation.reader_eval import ITEMS, LABELS, load_items, load_labels, mismatches, norm_country, score
from src.reader.schema import ReadEvent


def ev(item_id, **kw):
    base = dict(item_id=item_id, relevant=True, event_type="tariff_or_trade_rule", status="happened", direction="higher_cost",
                start_date=date(2026, 10, 19), imposing_country="United States", rate_percent=None)
    base.update(kw)
    return ReadEvent.model_validate(base)


GOLD = {
    "a": {"item_id": "a", "relevant": True, "event_type": "tariff_or_trade_rule", "status": "happened", "start_date": "2026-10-19",
          "imposing_country": "United States", "rate_percent": None, "ambiguous": []},
    "b": {"item_id": "b", "relevant": True, "event_type": "tariff_or_trade_rule", "status": "ongoing", "start_date": None,
          "imposing_country": "China", "rate_percent": 24.0, "ambiguous": ["status"]},
    "c": {"item_id": "c", "relevant": False, "ambiguous": []},
    "d": {"item_id": "d", "relevant": False, "ambiguous": ["relevant"]},
}


def test_label_file_matches_the_frozen_items_and_is_well_formed():
    items, labels = load_items(), load_labels()
    assert len(items) == len(labels) == 50 and {i.item_id for i in items} == set(labels)
    for g in labels.values():
        assert isinstance(g["relevant"], bool) and isinstance(g["ambiguous"], list)
        if g["relevant"]:
            assert g["event_type"] and g["status"] in ("happened", "ongoing", "expected", "unknown") and g["imposing_country"]
            if g.get("start_date"):
                date.fromisoformat(g["start_date"])
    assert sum(g["relevant"] for g in labels.values()) >= 20 and sum(1 for g in labels.values() if g.get("start_date")) >= 15
    assert all("needs" in g["labeled_by"] for g in labels.values())      # drafts until Akshansh reviews them


def test_perfect_predictions_score_one():
    preds = {"a": ev("a"), "b": ev("b", status="ongoing", start_date=None, imposing_country="China", rate_percent=24.0),
             "c": ev("c", relevant=False), "d": ev("d", relevant=False)}
    s = score(GOLD, preds)["all_items"]
    assert s["relevance"]["accuracy"] == 1.0 and s["relevance"]["f1"] == 1.0 and s["event_type"]["accuracy"] == 1.0
    assert s["status"]["accuracy"] == 1.0 and s["start_date"]["exact_rate"] == 1.0 and s["imposing_country"]["accuracy"] == 1.0
    assert s["rate_percent"] == {"gold_with_rate": 1, "correct": 1, "rate_invented_where_gold_has_none": 0}
    assert mismatches(GOLD, preds) == []


def test_errors_are_counted_and_ambiguous_items_can_be_excluded():
    preds = {"a": ev("a", status="expected", start_date=date(2026, 10, 25), imposing_country="USA"),   # wrong status and date, alias ok
             "b": ev("b", status="happened", start_date=date(2026, 11, 1), imposing_country="China", rate_percent=None),  # wrong status, invented date, rate missed
             "c": ev("c", relevant=True),                                                  # false positive
             "d": ev("d", relevant=True)}                                                  # false positive (ambiguous)
    s = score(GOLD, preds)
    allb, clean = s["all_items"], s["unambiguous_items"]
    assert allb["relevance"] == {"accuracy": 0.5, "precision": 0.5, "recall": 1.0, "f1": 0.667, "tp": 2, "fp": 2, "fn": 0, "tn": 0}
    assert allb["status"]["accuracy"] == 0.0 and allb["start_date"]["exact"] == 0 and allb["start_date"]["predicted_a_date_where_gold_has_none"] == 1
    assert allb["imposing_country"]["accuracy"] == 1.0 and allb["rate_percent"]["correct"] == 0
    assert clean["items"] == 2 and clean["relevance"]["fp"] == 1                           # b (status) and d (relevant) dropped
    m = {x["item_id"]: x for x in mismatches(GOLD, preds)}
    assert set(m) == {"a", "b", "c", "d"} and m["a"]["diffs"]["status"] == ("happened", "expected")


def test_failed_read_counts_as_not_relevant_and_country_aliases():
    s = score(GOLD, {"a": None, "b": None, "c": None, "d": None})["all_items"]
    assert s["relevance"]["recall"] == 0.0 and s["relevance"]["tn"] == 2 and s["status"]["correct"] == 0
    assert norm_country("USA") == norm_country("United States") == "united states" and norm_country(None) is None
    assert norm_country("Republic of Korea") == "south korea"


def test_grader_comparison_numbers():
    hand = {"1": "yes", "2": "yes", "3": "no", "4": "partly", "5": "no"}
    llm = {"1": "supported", "2": "partly", "3": "unsupported", "4": "partly", "5": "partly"}
    r = compare(hand, llm)
    assert r["cases"] == 5 and r["exact_agreement"] == 0.6 and r["agreement_fully_supported_vs_not"] == 0.8
    assert r["hand_graded_unsupported"] == 2 and r["llm_flagged_those_as_not_fully_supported"] == 2
    assert r["confusion"]["hand=no llm=partly"] == 1 and compare(hand, {})["cases"] == 0


def test_judge_cases_file_has_real_answers_and_controls():
    from src.evaluation.judge_eval import CASES, GRADES

    cases = [json.loads(l) for l in CASES.read_text(encoding="utf-8").splitlines()]
    grades = {json.loads(l)["case_id"]: json.loads(l) for l in GRADES.read_text(encoding="utf-8").splitlines()}
    graded = [c for c in cases if c["decision"]]
    assert {c["case_id"] for c in graded} == set(grades) and len(grades) >= 12
    assert sum(c["kind"] == "control" for c in cases) == 6 and all(g["supported"] in ("yes", "partly", "no") for g in grades.values())
