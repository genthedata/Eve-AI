import os
from typing import Any, Dict
from uuid import uuid4

from app.contracts import A2AMessage
from app.orchestrator import OrchestratorAgent
from app.platform.orchestration import run_catering_flow


class AgentRouter:
    """
    Routes catering invocations through either:
    - Microsoft Agent Framework (USE_MS_AGENT_FRAMEWORK=true) — placeholder; falls back to DAG
    - Microsoft AutoGen group-chat (USE_AUTOGEN=true) — real LLM multi-agent conversation
    - Deterministic DAG (default) — fast, reliable, works without a model

    Backend selection: ORCHESTRATION_BACKEND or app.platform.config.get_orchestration_backend()
    """

    def __init__(self) -> None:
        self.orchestrator = OrchestratorAgent()
        self._autogen_adapter = None

    def _use_autogen(self) -> bool:
        return os.getenv("USE_AUTOGEN", "false").strip().lower() in ("1", "true", "yes")

    def _get_autogen(self):
        if self._autogen_adapter is None:
            from app.runtime.ms_autogen_adapter import MicrosoftAgentFrameworkAdapter
            self._autogen_adapter = MicrosoftAgentFrameworkAdapter()
        return self._autogen_adapter

    def invoke_catering_flow(self, request_payload: Dict[str, Any], thread_id: str) -> Dict:
        return run_catering_flow(
            request_payload,
            thread_id,
            native_runner=self._run_deterministic,
        )

    def _run_deterministic(self, request_payload: Dict[str, Any], thread_id: str) -> Dict:
        state = self.orchestrator.run(request_payload, thread_id)
        return {
            "message_trace": [
                {
                    "sender": m.sender,
                    "recipient": m.recipient,
                    "msg_type": m.msg_type,
                    "payload": m.payload,
                    "reasoning": m.reasoning,
                    "kb_sources": m.kb_sources,
                    "simulation_events": m.simulation_events,
                }
                for m in state.messages
            ],
            "final_report": state.outputs["final_report"],
            "thread_id": state.thread_id,
        }

    def dispatch_message(self, msg: A2AMessage) -> Dict:
        if msg.recipient == "orchestrator" and msg.msg_type == "start_catering_flow":
            tid = (msg.correlation_id or "").strip() or str(uuid4())
            result = self.invoke_catering_flow(msg.payload, tid)
            return {"status": "ok", "result": result}
        return {"status": "ignored", "reason": "No route found for recipient/msg_type"}
