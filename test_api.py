import os
import sys
import json
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from service.textAnalyzer import TextAnalyzer
from model.envLoader import EnvLoader

env = EnvLoader()
analyzer = TextAnalyzer(
    key=env.openrouter_api_key,
    base_prompt=env.base_prompt,
    phase2_prompt=env.phase2_prompt,
    model=env.llm_model,
    timezone_name=env.timezone
)

text = '[{"message_id": "1", "chat_id": "1", "text": "Hello, when is the event?"}]'

print("Calling Phase 1...")
try:
    response = analyzer._TextAnalyzer__call_llm(analyzer.base_prompt, text, analyzer.PHASE1_SCHEMA)
    content = response.choices[0].message.content
    print("Raw content:")
    print(repr(content))
except Exception as e:
    print(f"Error: {e}")
