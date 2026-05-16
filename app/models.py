from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class AgentMessage:
    sender: str
    recipient: str
    msg_type: str
    payload: Dict[str, Any]
    reasoning: Optional[str] = None
    kb_sources: List[str] = field(default_factory=list)
    simulation_events: List[str] = field(default_factory=list)


@dataclass
class SessionState:
    request: Dict[str, Any]
    thread_id: str = ""
    messages: List[AgentMessage] = field(default_factory=list)
    outputs: Dict[str, Any] = field(default_factory=dict)
    catering_context: Optional[Dict[str, Any]] = None
