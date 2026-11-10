"""Phoenix tracing for the plain Gemini SDK calls (the old ADK-only instrumentation is not involved here).

With PHOENIX_API_KEY set, `setup_tracing()` registers the Phoenix OpenTelemetry provider and instruments the
google-genai SDK, so every `generate_content` call shows up as a span (prompt, answer, tokens, latency).
Without a key it does nothing and returns a no-op tracer.
"""

from __future__ import annotations

import logging
from contextlib import contextmanager

from opentelemetry import trace

logger = logging.getLogger(__name__)
_instrumented = False


def setup_tracing():
    """Returns the tracer provider, or None when Phoenix is not configured."""
    global _instrumented
    from src.agent.observability import configure_phoenix

    provider = configure_phoenix()
    if provider is not None and not _instrumented:
        try:
            from openinference.instrumentation.google_genai import GoogleGenAIInstrumentor

            GoogleGenAIInstrumentor().instrument(tracer_provider=provider)
            _instrumented = True
        except Exception as exc:  # noqa: BLE001
            logger.warning("google-genai instrumentation not enabled: %s", exc)
    return provider


@contextmanager
def span(name: str, **attributes):
    """A span around a batch / run (no-op tracer when tracing is off)."""
    tracer = trace.get_tracer("chainguard.reader")
    with tracer.start_as_current_span(name) as s:
        for k, v in attributes.items():
            s.set_attribute(k, v)
        yield s
