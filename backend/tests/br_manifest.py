"""Business rules → milestone that delivers them (docs/09, docs/ops/00-review.md K12).

`tests/test_rule_coverage.py` requires every BR of a completed milestone to appear in at least one
test name (`test_br_XX_*`) or `@pytest.mark.br("BR-XX")` marker. Add a milestone to COMPLETED only
when its acceptance criteria pass.
"""

COMPLETED: frozenset[str] = frozenset({"M0", "M1"})

BR_MILESTONE: dict[str, str] = {
    "BR-01": "M2",
    "BR-02": "M2",
    "BR-03": "M3",
    "BR-04": "M3",
    "BR-05": "M3",
    "BR-06": "M4",
    "BR-07": "M4",
    "BR-08": "M4",
    "BR-09": "M4",
    "BR-10": "M4",
    "BR-11": "M3",
    "BR-12": "M3",
    "BR-13": "M2",
    "BR-14": "M2",
    "BR-15": "M2",
    "BR-16": "M2",
    "BR-17": "M2",
    "BR-18": "M2",
    "BR-19": "M5",
    "BR-20": "M5",
    "BR-21": "M5",
    "BR-22": "M5",
    "BR-23": "M6",
    "BR-24": "M7",
    "BR-25": "M1",
    "BR-26": "M0",
    "BR-27": "M1",
    "BR-28": "M2",
    "BR-29": "M1",
    "BR-30": "M4",
    "BR-31": "M3",
    "BR-32": "M4",
    "BR-33": "P2",
}
