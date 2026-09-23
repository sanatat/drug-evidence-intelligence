from __future__ import annotations
from pydantic import BaseModel, Field
from typing import Optional

class Evidence(BaseModel):
    page: Optional[int] = None
    snippet: Optional[str] = None
    confidence: float = Field(default=0.5, ge=0, le=1)

class QualityParameter(BaseModel):
    category: str
    parameter_name: str
    value_text: Optional[str] = None
    numeric_min: Optional[float] = None
    numeric_max: Optional[float] = None
    operator: Optional[str] = None
    unit: Optional[str] = None
    method_name: Optional[str] = None
    method_details: dict = Field(default_factory=dict)
    basis: Optional[str] = None
    evidence: Evidence = Field(default_factory=Evidence)

class MonographExtraction(BaseModel):
    monograph_name: str
    material_type: str = "API"
    dosage_form: Optional[str] = None
    salt_form: Optional[str] = None
    edition: Optional[str] = None
    effective_date: Optional[str] = None
    confidence: float = 0.5
    parameters: list[QualityParameter] = Field(default_factory=list)

class EndpointExtraction(BaseModel):
    endpoint_name: str
    study_label: Optional[str] = None
    timepoint: Optional[str] = None
    treatment_value: Optional[float] = None
    comparator_value: Optional[float] = None
    effect_measure: Optional[str] = None
    effect_value: Optional[float] = None
    ci_low: Optional[float] = None
    ci_high: Optional[float] = None
    p_value: Optional[float] = None
    unit: Optional[str] = None
    agency_interpretation: Optional[str] = None
    source_page: Optional[int] = None
    confidence: float = 0.5

class TrialExtraction(BaseModel):
    trial_name: Optional[str] = None
    trial_id: Optional[str] = None
    phase: Optional[str] = None
    randomized: Optional[str] = None
    blinded: Optional[str] = None
    sample_size: Optional[int] = None
    population: Optional[str] = None
    treatment_arm: Optional[str] = None
    comparator_arm: Optional[str] = None
    follow_up: Optional[str] = None
    confidence: float = 0.5

class SafetyExtraction(BaseModel):
    event_name: str
    category: Optional[str] = None
    treatment_value: Optional[float] = None
    comparator_value: Optional[float] = None
    unit: Optional[str] = None
    grade: Optional[str] = None
    seriousness: Optional[str] = None
    interpretation: Optional[str] = None
    source_page: Optional[int] = None
    confidence: float = 0.5

class ClinicalExtraction(BaseModel):
    agency: str
    assessment_type: str
    assessment_date: Optional[str] = None
    indication: Optional[str] = None
    disease_stage: Optional[str] = None
    line_of_therapy: Optional[str] = None
    population: Optional[str] = None
    biomarker: Optional[str] = None
    combination_therapy: Optional[str] = None
    comparator: Optional[str] = None
    relative_effectiveness: Optional[str] = None
    benefit_risk: Optional[str] = None
    cost_effectiveness: Optional[str] = None
    managed_entry: Optional[str] = None
    recommendation: Optional[str] = None
    restrictions: Optional[str] = None
    uncertainty: Optional[str] = None
    confidence: float = 0.5
    trials: list[TrialExtraction] = Field(default_factory=list)
    endpoints: list[EndpointExtraction] = Field(default_factory=list)
    safety: list[SafetyExtraction] = Field(default_factory=list)
    evidence: dict[str, Evidence] = Field(default_factory=dict)
