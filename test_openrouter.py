import os
from google.adk.models.registry import LLMRegistry

llm = LLMRegistry.new_llm("openai/openai/gpt-4o-mini")

print(type(llm))
print(llm)