from typing import Dict, List, Optional

from pydantic import BaseModel


class Assumption(BaseModel):
    id: int
    statement: str
    testable: bool = True
    tied_to_evidence: Optional[str] = None
    status: str = "unknown"


class Option(BaseModel):
    name: str
    pros: List[str]
    cons: List[str]
    cost_band: str


class ActionStep(BaseModel):
    step: int
    action: str
    owner_role: str
    depends_on: List[int] = []


class Risk(BaseModel):
    description: str
    severity: str
    likelihood: str
    mitigation: str
    residual: str


class EvidenceSource(BaseModel):
    title: str
    url: Optional[str] = None
    retrieved: str
    excerpt: str
    verified: bool = False


class ProblemFraming(BaseModel):
    goal: str
    stakeholders: List[str]
    success_criteria: List[str]


class Recommendation(BaseModel):
    chosen_path: str
    rationale: str
    dissenting_view: Optional[str] = None


class EvidencePack(BaseModel):
    sources: List[EvidenceSource] = []
    assumption_table: List[Assumption] = []
    confidence_per_claim: Dict[str, float] = {}
    falsifiers: List[str] = []


class Blueprint(BaseModel):
    problem_framing: ProblemFraming
    assumptions: List[Assumption]
    options: List[Option]
    recommendation: Recommendation
    action_plan: List[ActionStep]
    risks: List[Risk]
    evidence_pack: EvidencePack
    next_steps: List[str]
