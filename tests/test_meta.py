from app.meta import norm_endpoint, run_meta_analysis


def _row(name, effect, low, high, **extra):
    return {
        "document_id": extra.pop("document_id", name),
        "filename": extra.pop("filename", f"{name}.pdf"),
        "study_name": name,
        "effect_measure": "HR",
        "effect_value": effect,
        "ci_low": low,
        "ci_high": high,
        "confidence": 0.9,
        "endpoint_name": "Overall survival",
        "indication": extra.pop("indication", "metastatic colorectal cancer"),
        "population": extra.pop("population", "previously treated adults"),
        "comparator": extra.pop("comparator", "placebo"),
        "timepoint": extra.pop("timepoint", None),
        **extra,
    }


def test_endpoint_normalization():
    assert norm_endpoint("OS") == "overall survival"
    assert norm_endpoint("Progression-free survival") == "progression free survival"


def test_random_effects_meta_analysis_runs():
    result = run_meta_analysis(
        [
            _row("CORRECT", 0.77, 0.64, 0.94),
            _row("CONCUR", 0.55, 0.40, 0.77),
        ]
    )
    assert result["k"] == 2
    assert 0 < result["random"]["effect"] < 1
    assert result["random"]["ci_low"] < result["random"]["effect"] < result["random"]["ci_high"]
    assert result["I2"] >= 0
    assert result["tau2"] >= 0


def test_identical_duplicate_study_is_deduplicated():
    a = _row("TRIAL-X", 0.75, 0.60, 0.93, document_id=1, filename="paper-a.pdf")
    b = _row("TRIAL-X", 0.75, 0.60, 0.93, document_id=2, filename="paper-b.pdf")
    c = _row("TRIAL-Y", 0.80, 0.66, 0.97, document_id=3, filename="paper-c.pdf")
    result = run_meta_analysis([a, b, c])
    assert result["k"] == 2
    assert any("Duplicate report detected" in w for w in result["review_warnings"])


def test_conflicting_duplicate_study_blocks_pooling():
    a = _row("TRIAL-X", 0.75, 0.60, 0.93, document_id=1, filename="paper-a.pdf")
    b = _row("TRIAL-X", 0.62, 0.50, 0.78, document_id=2, filename="paper-b.pdf")
    c = _row("TRIAL-Y", 0.80, 0.66, 0.97, document_id=3, filename="paper-c.pdf")
    result = run_meta_analysis([a, b, c])
    assert "error" in result
    assert "manual review" in result["error"].lower()
