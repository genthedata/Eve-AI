"""
Microsoft AutoGen multi-agent group-chat orchestration adapter.

Prefer routing via app.platform.orchestration.run_catering_flow (ORCHESTRATION_BACKEND=autogen).
For Microsoft Agent Framework (not AutoGen), use USE_MS_AGENT_FRAMEWORK — see app.platform.ms_agent_framework.

When USE_AUTOGEN=true and autogen-agentchat is installed, the full catering
workflow runs as a real multi-agent group chat where each specialist is an
independent AssistantAgent that sends messages to the next agent in the pipeline.

Install:
    pip install autogen-agentchat autogen-ext[openai]

Required (when USE_AUTOGEN=true):
    MODEL_PROVIDER, MODEL_NAME, MODEL_ENDPOINT, MODEL_API_KEY  (same as LLM provider)
    USE_LLM=true
"""

from __future__ import annotations

import json
import os
from typing import Any, Dict, List


class MicrosoftAgentFrameworkAdapter:
    def __init__(self) -> None:
        self.enabled = False
        try:
            import autogen_agentchat  # type: ignore # noqa: F401
            self.enabled = True
        except Exception:
            self.enabled = False

    def is_available(self) -> bool:
        return self.enabled

    def _build_llm_config(self) -> Dict[str, Any]:
        provider = os.getenv("MODEL_PROVIDER", "mock").lower()
        model = os.getenv("MODEL_NAME", "gpt-4o-mini")
        endpoint = os.getenv("MODEL_ENDPOINT", "https://api.openai.com/v1").rstrip("/")
        api_key = os.getenv("MODEL_API_KEY", "") or os.getenv("AZURE_OPENAI_API_KEY", "")

        return {
            "config_list": [
                {
                    "model": model,
                    "api_key": api_key or "none",
                    "base_url": endpoint if provider != "azure_openai" else None,
                    "api_type": "azure" if provider == "azure_openai" else "openai",
                }
            ],
            "temperature": 0.2,
        }

    def run_multi_agent_flow(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self.enabled:
            raise RuntimeError(
                "autogen-agentchat is not installed. "
                "Run: pip install autogen-agentchat autogen-ext[openai]"
            )

        try:
            from autogen_agentchat.agents import AssistantAgent  # type: ignore
            from autogen_agentchat.teams import RoundRobinGroupChat  # type: ignore
            from autogen_agentchat.conditions import TextMentionTermination  # type: ignore
            from autogen_agentchat.ui import Console  # type: ignore
            import asyncio
        except ImportError as e:
            raise RuntimeError(f"AutoGen import failed: {e}") from e

        llm_config = self._build_llm_config()
        payload_json = json.dumps(payload, indent=2)

        # Each specialist is an AssistantAgent with a domain system prompt.
        customer_agent = AssistantAgent(
            name="CustomerAgent",
            model_client=self._make_model_client(llm_config),
            system_message=(
                "You are the Customer Interaction Agent for a smart catering system. "
                "When given a catering request, parse and validate it, then output a "
                "structured summary of the event requirements (type, guests, dietary needs, "
                "budget, location, date, service style). "
                "End your message with: HANDOFF:MenuAgent"
            ),
        )

        menu_agent = AssistantAgent(
            name="MenuAgent",
            model_client=self._make_model_client(llm_config),
            system_message=(
                "You are the Menu Planning Agent. Given the customer profile from CustomerAgent, "
                "recommend a suitable menu with specific dishes (5-7 items) respecting dietary "
                "constraints, and calculate portion counts for mains, sides, and desserts. "
                "End your message with: HANDOFF:InventoryAgent"
            ),
        )

        inventory_agent = AssistantAgent(
            name="InventoryAgent",
            model_client=self._make_model_client(llm_config),
            system_message=(
                "You are the Inventory and Procurement Agent. Given the menu from MenuAgent, "
                "list required ingredients with quantities, identify what needs to be sourced, "
                "and generate a procurement list with urgency flags. "
                "End your message with: HANDOFF:LogisticsAgent"
            ),
        )

        logistics_agent = AssistantAgent(
            name="LogisticsAgent",
            model_client=self._make_model_client(llm_config),
            system_message=(
                "You are the Logistics Planning Agent. Given the procurement status from "
                "InventoryAgent, create a detailed preparation timeline, allocate kitchen staff "
                "and delivery vehicles, and flag any scheduling risks. "
                "End your message with: HANDOFF:PricingAgent"
            ),
        )

        pricing_agent = AssistantAgent(
            name="PricingAgent",
            model_client=self._make_model_client(llm_config),
            system_message=(
                "You are the Pricing and Optimization Agent. Given the full plan from all "
                "previous agents, calculate ingredient cost, labor cost, logistics cost, "
                "contingency, and final quote. Compare against budget and suggest adjustments "
                "if over budget. "
                "End your message with: HANDOFF:MonitoringAgent"
            ),
        )

        monitoring_agent = AssistantAgent(
            name="MonitoringAgent",
            model_client=self._make_model_client(llm_config),
            system_message=(
                "You are the Monitoring Agent. Review the complete catering plan produced by "
                "all specialist agents. Identify risks, flag delays, assess budget fitness, and "
                "write an executive summary for the operations manager. "
                "When done, end your message with: PLAN_COMPLETE"
            ),
        )

        termination = TextMentionTermination("PLAN_COMPLETE")
        team = RoundRobinGroupChat(
            [customer_agent, menu_agent, inventory_agent,
             logistics_agent, pricing_agent, monitoring_agent],
            termination_condition=termination,
            max_turns=12,
        )

        initial_message = (
            f"New catering request received. Parse and process this end-to-end:\n{payload_json}"
        )

        async def _run() -> List[Dict[str, Any]]:
            messages: List[Dict[str, Any]] = []
            async for msg in team.run_stream(task=initial_message):
                if hasattr(msg, "source") and hasattr(msg, "content"):
                    messages.append({"sender": msg.source, "content": msg.content})
            return messages

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                import concurrent.futures
                with concurrent.futures.ThreadPoolExecutor() as pool:
                    future = pool.submit(asyncio.run, _run())
                    messages = future.result(timeout=120)
            else:
                messages = loop.run_until_complete(_run())
        except Exception as exc:
            return {
                "autogen_error": str(exc),
                "message_trace": [],
                "final_report": {"error": str(exc)},
                "thread_id": payload.get("thread_id", ""),
            }

        a2a_trace = [
            {
                "sender": m["sender"],
                "recipient": "next_agent",
                "msg_type": "autogen_groupchat",
                "payload": {"content": m["content"]},
                "reasoning": m["content"],
                "kb_sources": [],
                "simulation_events": [],
            }
            for m in messages
        ]

        last_content = messages[-1]["content"] if messages else ""
        return {
            "message_trace": a2a_trace,
            "final_report": {
                "thread_id": payload.get("thread_id", ""),
                "autogen_plan": last_content,
                "full_conversation": messages,
                "event_summary": payload,
            },
            "thread_id": payload.get("thread_id", ""),
        }

    def _make_model_client(self, llm_config: Dict[str, Any]) -> Any:
        provider = os.getenv("MODEL_PROVIDER", "mock").lower()
        try:
            if provider == "ollama":
                from autogen_ext.models.ollama import OllamaChatCompletionClient  # type: ignore
                return OllamaChatCompletionClient(
                    model=os.getenv("MODEL_NAME", "llama3.1"),
                )
            else:
                from autogen_ext.models.openai import OpenAIChatCompletionClient  # type: ignore
                cfg = llm_config["config_list"][0]
                kwargs: Dict[str, Any] = {
                    "model": cfg["model"],
                    "api_key": cfg["api_key"],
                }
                if cfg.get("base_url"):
                    kwargs["base_url"] = cfg["base_url"]
                return OpenAIChatCompletionClient(**kwargs)
        except ImportError:
            raise RuntimeError(
                "autogen-ext is required. Run: pip install autogen-ext[openai]"
            )
