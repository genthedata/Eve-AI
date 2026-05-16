from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# PLATFORM: orchestration is selected server-side (ORCHESTRATION_BACKEND / USE_MS_AGENT_FRAMEWORK).
# Optional future field: orchestration_backend: Optional[str] = None


class InvocationRequest(BaseModel):
    event_type: str
    guest_count: int
    dietary_constraints: List[str] = Field(default_factory=list)
    budget: float
    currency: str = Field(
        default="PHP",
        description="ISO currency code for the budget (e.g. PHP, MYR, SGD). "
                    "All costs in the report will be expressed in this currency.",
    )
    location: str
    event_date: str
    service_style: str
    thread_id: Optional[str] = Field(
        default=None,
        description="Client-supplied correlation id; server generates if omitted.",
    )


class A2AMessage(BaseModel):
    sender: str
    recipient: str
    msg_type: str
    payload: Dict[str, Any]
    correlation_id: Optional[str] = None


class InvocationResponse(BaseModel):
    correlation_id: str
    thread_id: str
    message_trace: List[Dict[str, Any]]
    final_report: Dict[str, Any]
