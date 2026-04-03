from dataclasses import dataclass, field


@dataclass
class TriageDecision:
    triage_level: int
    priority: str
    department: str
    note: str


@dataclass
class WorkingMemory:
    short_term_turns: list[dict] = field(default_factory=list)
    shared_memory: dict = field(default_factory=dict)
    private_memory: dict = field(default_factory=dict)
