"""Ask ChainGuard: one real tool-using agent (Google ADK) that answers questions about a business's alerts, shipments and stock.

What makes it safe and cheap to run:
  - READ ONLY: five lookup tools (src/chat/tools.py), each in a READ ONLY database transaction, bound to one business;
  - HARD CALL CAPS: at most `max_tool_calls` lookups (a callback refuses the rest) and at most `max_llm_calls` model calls (ADK RunConfig);
  - GROUNDED: after the model answers, code checks that every number, date and alert id in the answer came from a lookup
    (src/chat/grounding.py); if not, the answer is returned with a visible note and grounded=False;
  - it is told to say "I cannot find that" instead of guessing, and never to calculate.
The model is the only part that decides WHICH lookup to make next: that choice is what makes this an agent. Everything else is code.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
import uuid
from dataclasses import dataclass, field

from src.chat.grounding import ID_RE, check_grounding
from src.chat.tools import make_tools

logger = logging.getLogger(__name__)

APP_NAME = "ask-chainguard"
DEFAULT_MODEL = os.getenv("CHAT_MODEL", "gemini-3.5-flash-lite")   # free tier: 15 requests/min, 500/day
MAX_TOOL_CALLS = 6
MAX_LLM_CALLS = 8
TIMEOUT_SECONDS = 60

INSTRUCTION = """You are ChainGuard, an assistant for a small importer who runs purchasing. You answer questions about THIS business's \
supply-chain alerts, inbound shipments, stock and data freshness, using ONLY the lookup tools you are given.

Rules:
- Look things up before you answer. Use the fewest lookups that answer the question (you have a small budget). Never guess.
- Use only what the lookups return. If they do not contain the answer, say plainly that you cannot find it. Do not use outside knowledge.
- Never calculate or estimate. Quote money, days and dates exactly as the lookups give them. Write dates as YYYY-MM-DD.
- When you mention an alert, include its alert_id exactly as returned so the user can open it.
- You can only read. If asked to change, send, order or delete anything, explain that you cannot do that and say what the user could do.
- Be short: a direct answer first, then at most a few supporting points. Plain language, no jargon.
- If a lookup returns an error or says the call limit is reached, say what you could not check and answer with what you have.
"""


@dataclass
class AskResult:
    answer: str
    grounded: bool = True
    issues: list[str] = field(default_factory=list)       # what the grounding check could not verify
    tool_calls: list[dict] = field(default_factory=list)  # [{name, args, ok}]
    llm_calls: int = 0
    capped: bool = False                                  # a call cap was hit
    cited_alert_ids: list[str] = field(default_factory=list)
    model: str = ""
    session_id: str = ""
    seconds: float = 0.0
    error: str | None = None


class ToolBudget:
    def __init__(self, max_calls: int):
        self.max_calls, self.used, self.refused = max_calls, 0, 0

    def before_tool(self, tool, args, tool_context):
        """ADK before-tool callback: refuse calls beyond the budget (returning a dict replaces the tool's result)."""
        if self.used >= self.max_calls:
            self.refused += 1
            return {"error": "tool call limit reached: write the final answer now using only what you already have"}
        self.used += 1
        return None


_session_service = None


def _sessions():
    global _session_service
    if _session_service is None:
        from google.adk.sessions import InMemorySessionService

        _session_service = InMemorySessionService()
    return _session_service


def build_agent(business_id: str, model, budget: ToolBudget):
    from google.adk.agents import LlmAgent

    return LlmAgent(name="AskChainGuard", model=model, instruction=INSTRUCTION, tools=make_tools(business_id),
                    before_tool_callback=budget.before_tool, generate_content_config={"temperature": 0.1})


def _friendly_error(exc: Exception) -> str:
    msg = str(exc).lower()
    if "429" in msg or "resource_exhausted" in msg or "quota" in msg:
        return "The AI model's request limit has been reached for now. Please try again in a minute."
    if "503" in msg or "unavailable" in msg or "overloaded" in msg:
        return "The AI model is overloaded right now. Please try again shortly."
    if "api key" in msg or "401" in msg or "unauthenticated" in msg:
        return "The AI model key is missing or invalid (check GEMINI_API_KEY)."
    return f"Something went wrong while asking the model ({exc.__class__.__name__})."


async def ask(question: str, business_id: str = "demo-business-001", session_id: str | None = None, *, model=None,
              max_tool_calls: int = MAX_TOOL_CALLS, max_llm_calls: int = MAX_LLM_CALLS) -> AskResult:
    """Answer one question. `model` is a model name (default CHAT_MODEL) or an ADK model object (tests pass a fake)."""
    from google.adk.agents.run_config import RunConfig
    from google.adk.runners import Runner
    from google.genai import types

    if not os.getenv("GOOGLE_API_KEY") and os.getenv("GEMINI_API_KEY"):
        os.environ["GOOGLE_API_KEY"] = os.environ["GEMINI_API_KEY"]
    model = model or DEFAULT_MODEL
    session_id = session_id or f"ask-{uuid.uuid4().hex}"
    budget = ToolBudget(max_tool_calls)
    agent = build_agent(business_id, model, budget)
    svc = _sessions()
    if await svc.get_session(app_name=APP_NAME, user_id=business_id, session_id=session_id) is None:
        await svc.create_session(app_name=APP_NAME, user_id=business_id, session_id=session_id)
    runner = Runner(agent=agent, app_name=APP_NAME, session_service=svc)

    result = AskResult(answer="", model=model if isinstance(model, str) else getattr(model, "model", "custom"), session_id=session_id)
    outputs: list[dict] = []
    pending: dict[str, dict] = {}
    started = time.perf_counter()

    async def consume():
        message = types.Content(role="user", parts=[types.Part(text=question)])
        async for event in runner.run_async(user_id=business_id, session_id=session_id, new_message=message,
                                            run_config=RunConfig(max_llm_calls=max_llm_calls)):
            # a model call = an event whose content is the model's turn (the tool results also come back authored by the agent)
            if event.author == agent.name and event.content and event.content.role == "model" and not getattr(event, "partial", False):
                result.llm_calls += 1
            for call in event.get_function_calls():
                entry = {"name": call.name, "args": dict(call.args or {}), "ok": None}
                pending[call.id or call.name] = entry
                result.tool_calls.append(entry)
            for resp in event.get_function_responses():
                body = resp.response if isinstance(resp.response, dict) else {"result": resp.response}
                outputs.append(body)
                entry = pending.get(resp.id or resp.name)
                if entry is not None:
                    entry["ok"] = "error" not in body
            if event.is_final_response() and event.content and event.content.parts:
                text = "".join(p.text or "" for p in event.content.parts if getattr(p, "text", None))
                if text.strip():
                    result.answer = text.strip()

    try:
        await asyncio.wait_for(consume(), timeout=TIMEOUT_SECONDS)
    except asyncio.TimeoutError:
        result.error, result.capped = "The question took too long and was stopped.", True
    except Exception as exc:  # noqa: BLE001 - quota, overload, call cap, bad key ...
        if "LlmCallsLimit" in exc.__class__.__name__ or "llm calls" in str(exc).lower():
            result.capped = True
            result.error = "I hit my limit on model calls for one question before finishing."
        else:
            logger.warning("ask failed: %s: %s", exc.__class__.__name__, str(exc)[:200])
            result.error = _friendly_error(exc)
    result.capped = result.capped or budget.refused > 0
    result.seconds = round(time.perf_counter() - started, 2)

    if not result.answer:
        result.answer = result.error or "I could not produce an answer."
        result.grounded = False
        return result
    result.issues = check_grounding(result.answer, outputs)
    result.grounded = not result.issues
    if result.issues:
        result.answer += "\n\n(Note: I could not verify part of this against the data: " + "; ".join(result.issues[:4]) + ".)"
    ids_returned = {i for o in outputs for i in ID_RE.findall(str(o))}
    result.cited_alert_ids = sorted(i for i in ids_returned if i in result.answer)
    return result


def ask_sync(question: str, business_id: str = "demo-business-001", **kw) -> AskResult:
    return asyncio.run(ask(question, business_id, **kw))
