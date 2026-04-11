import os
import json
import random
import sys
import argparse
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add the root directory to sys.path to import modules from service/ and model/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from service.textAnalyzer import TextAnalyzer
from model.envLoader import EnvLoader

def generate_random_metadata(index: int) -> Dict[str, Any]:
    """Generates random metadata for a message."""
    sources = ["telegram", "whatsapp"]
    source = random.choice(sources)
    chat_id = f"chat_{random.randint(1000, 9999)}"
    message_id = f"msg_{index}_{random.randint(10000, 99999)}"
    chat_title = f"Test Group {random.randint(1, 100)}"

    # Random date within the last month
    days_ago = random.randint(0, 30)
    hours_ago = random.randint(0, 23)
    timestamp = datetime.now() - timedelta(days=days_ago, hours=hours_ago)

    return {
        "source": source,
        "chat_id": chat_id,
        "chat_title": chat_title,
        "message_id": message_id,
        "datetime": timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }

def run_tests(test_cases_file: str, prompt_file: str = None):
    # Load environment
    env = EnvLoader()

    # Load test cases
    with open(test_cases_file, 'r', encoding='utf-8') as f:
        test_cases = json.load(f)

    # Prepare messages for TextAnalyzer
    messages_to_analyze = []
    expectations = {} # message_id -> expected outcome

    for i, case in enumerate(test_cases):
        metadata = generate_random_metadata(i)
        msg_id = metadata['message_id']
        messages_to_analyze.append({
            **metadata,
            "text": case['text']
        })
        expectations[msg_id] = case['expected']

    # Initialize TextAnalyzer
    base_prompt = env.base_prompt
    if prompt_file:
        if os.path.exists(prompt_file):
            with open(prompt_file, 'r', encoding='utf-8') as f:
                base_prompt = f.read()
                print(f"Using custom prompt from: {prompt_file}")
        else:
            print(f"Warning: Prompt file {prompt_file} not found. Using default.")

    analyzer = TextAnalyzer(
        key=env.openrouter_api_key,
        base_prompt=base_prompt,
        phase2_prompt=env.phase2_prompt,
        model=env.llm_model,
        timezone_name=env.timezone
    )

    print(f"Analyzing {len(messages_to_analyze)} messages...")

    # Call the analyzer
    results_dict = analyzer.findMessages(json.dumps(messages_to_analyze, ensure_ascii=False))

    if results_dict is None:
        # LLM might return None if 'found' is false and it only contains results
        found_ids = []
        found_results_map = {}
    else:
        found_results = results_dict.get('results', [])
        found_ids = [r['message_id'] for r in found_results]
        found_results_map = {r['message_id']: r for r in found_results}

    # Evaluate results
    passed_count = 0
    total_count = len(test_cases)

    print("\n--- Test Results ---\n")

    for msg in messages_to_analyze:
        msg_id = msg['message_id']
        expected = expectations[msg_id]
        actual_found = msg_id in found_ids

        status = "PASS" if actual_found == expected['found'] else "FAIL"
        if status == "PASS":
            passed_count += 1

        print(f"[{status}] Text: {msg['text'][:100]}{'...' if len(msg['text']) > 100 else ''}")
        print(f"      Expected Found: {expected['found']}, Actual Found: {actual_found}")

        if actual_found:
            reason = found_results_map[msg_id].get('reason', 'No reason provided')
            print(f"      Reason: {reason}")
        elif not actual_found and expected['found']:
             print(f"      Reason: Message was expected to be found but LLM ignored it.")

        print("-" * 20)

    print(f"\nSummary: {passed_count}/{total_count} passed.")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Integration Test for Message Filtering')
    parser.add_argument('--cases', type=str, default='tests/test_cases.json', help='Path to test cases JSON file')
    parser.add_argument('--prompt', type=str, help='Path to optional custom prompt file')

    args = parser.parse_args()

    try:
        run_tests(args.cases, args.prompt)
    except Exception as e:
        print(f"Error running tests: {e}")
        sys.exit(1)
