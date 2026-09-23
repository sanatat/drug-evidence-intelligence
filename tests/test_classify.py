from app.classify import classify, resolve_existing_drug


def test_usp_monograph_classification():
    source, region, doc_type, subtype, role, eligible = classify(
        "Alanine-usp.pdf",
        "USP Monographs Alanine United States Pharmacopeia USP-NF",
    )
    assert source == "USP"
    assert region == "US"
    assert doc_type == "pharmacopoeia"
    assert subtype == "monograph"
    assert role == "pharmacopoeia"
    assert eligible == 0


def test_ema_psur_is_not_primary_clinical_assessment():
    text = "European Medicines Agency Scientific conclusions and grounds for the variation PSUSA/000"
    source, _, doc_type, subtype, role, eligible = classify("oxaliplatin-ema.pdf", text)
    assert source == "EMA"
    assert doc_type == "clinical_regulatory"
    assert subtype == "psur_scientific_conclusions"
    assert role == "safety_support"
    assert eligible == 0


def test_alias_mapping_aciclovir_acyclovir():
    existing = ["Aciclovir"]
    assert resolve_existing_drug("Acyclovir", existing) == "Aciclovir"


def test_alias_mapping_acetaminophen_paracetamol():
    existing = ["Paracetamol"]
    assert resolve_existing_drug("Acetaminophen", existing) == "Paracetamol"
