import os
import json
import yaml
import random
import sys
import argparse
import threading
import time
from datetime import datetime, timedelta
from typing import List, Dict, Any

# Add the root directory to sys.path to import modules from service/ and model/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from service.textAnalyzer import TextAnalyzer
from model.envLoader import EnvLoader

def resolve_test_key(env: EnvLoader) -> str:
    """OpenRouter key for integration tests: prefer the dedicated
    OPENROUTER_TEST_API_KEY, fall back to the production OPENROUTER_API_KEY."""
    return env.get("OPENROUTER_TEST_API_KEY") or env.openrouter_api_key


def generate_random_metadata(index: int, override_chat_title: str = None) -> Dict[str, Any]:
    """Generates random metadata for a message."""
    sources = ["telegram", "whatsapp"]
    source = random.choice(sources)
    chat_id = f"chat_{random.randint(1000, 9999)}"
    message_id = f"msg_{index}_{random.randint(10000, 99999)}"
    chat_title = override_chat_title or f"Test Group {random.randint(1, 100)}"

    # Random date within the last month
    days_ago = random.randint(0, 30)
    hours_ago = random.randint(0, 23)
    timestamp = datetime.now() - timedelta(days=days_ago, hours=hours_ago)

    return {
        "source": source,
        "chat_id": chat_id,
        "chat_title": chat_title,
        "message_id": message_id,
        "sender_name": f"User {random.randint(1, 1000)}",
        "datetime": timestamp.strftime("%Y-%m-%d %H:%M:%S")
    }

def load_fixtures(fixtures_dir: str) -> List[Dict[str, Any]]:
    """Loads test cases from subdirectories in a fixtures directory."""
    test_cases = []
    if not os.path.exists(fixtures_dir):
        return []

    subdirs = {
        "reported": True,
        "skipped": False
    }

    for subdir, default_found in subdirs.items():
        path = os.path.join(fixtures_dir, subdir)
        if not os.path.exists(path):
            continue
        
        for filename in sorted(os.listdir(path)):
            if filename.endswith(".txt"):
                file_path = os.path.join(path, filename)
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()

                # Default expected outcome from directory
                expected = {"found": default_found}
                chat_title = filename[:-4]
                text = content

                # Check for frontmatter
                if content.startswith("---"):
                    parts = content.split("---", 2)
                    if len(parts) >= 3:
                        try:
                            metadata = yaml.safe_load(parts[1])
                            text = parts[2].strip()
                            if "chat_title" in metadata:
                                chat_title = metadata["chat_title"]
                            if "expected" in metadata:
                                # Deep update or just update the found key?
                                # metadata['expected'] is likely already a dict
                                expected.update(metadata["expected"])
                        except Exception:
                            pass 

                test_cases.append({
                    "chat_title": chat_title,
                    "text": text.strip(),
                    "expected": expected
                })
    return test_cases

def run_tests(test_cases_file: str, prompt_file: str = None):
    # Load environment
    env = EnvLoader()

    # Load test cases
    test_cases = []
    if os.path.exists(test_cases_file):
        with open(test_cases_file, 'r', encoding='utf-8') as f:
            if test_cases_file.endswith('.yaml') or test_cases_file.endswith('.yml'):
                test_cases = yaml.safe_load(f) or []
            else:
                test_cases = json.load(f)

    # Load fixtures from the 'fixtures' directory alongside the cases file
    fixtures_dir = os.path.join(os.path.dirname(os.path.abspath(test_cases_file)), 'fixtures')
    test_cases.extend(load_fixtures(fixtures_dir))

    if not test_cases:
        print(f"No test cases found in {test_cases_file} or {fixtures_dir}")
        return

    # Prepare messages for TextAnalyzer
    messages_to_analyze = []
    expectations = {} # message_id -> expected outcome

    for i, case in enumerate(test_cases):
        metadata = generate_random_metadata(i, case.get('chat_title'))
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
        key=resolve_test_key(env),
        base_prompt=base_prompt,
        phase2_prompt=env.phase2_prompt,
        model=env.llm_model,
        timezone_name=env.timezone
    )

    print(f"Analyzing {len(messages_to_analyze)} messages...")

    stop_spinner = False

    def spinner():
        start_time = time.time()
        chars = "|/-\\"
        idx = 0
        while not stop_spinner:
            elapsed = time.time() - start_time
            sys.stdout.write(f"\rWaiting for LLM response... {chars[idx % len(chars)]} (Elapsed: {elapsed:.1f}s) ")
            sys.stdout.flush()
            idx += 1
            time.sleep(0.1)

    spinner_thread = threading.Thread(target=spinner)
    spinner_thread.daemon = True
    spinner_thread.start()

    try:
        # Call the analyzer
        results_dict = analyzer.findMessages(json.dumps(messages_to_analyze, ensure_ascii=False))
    finally:
        stop_spinner = True
        spinner_thread.join()
        sys.stdout.write("\r" + " " * 80 + "\r")
        sys.stdout.flush()

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

        print(f"[{status}] Chat: {msg['chat_title']}")
        print(f"      Text: {msg['text'][:100]}{'...' if len(msg['text']) > 100 else ''}")
        print(f"      Expected Found: {expected['found']}, Actual Found: {actual_found}")

        if actual_found:
            reason = found_results_map[msg_id].get('reason', 'No reason provided')
            print(f"      Reason: {reason}")
        elif not actual_found and expected['found']:
             print(f"      Reason: Message was expected to be found but LLM ignored it.")

        print("-" * 20)

    print(f"\nSummary: {passed_count}/{total_count} passed.")

def run_eval(eval_file: str, prompt_file: str = None):
    """Score Phase-1 classification against a labeled gold set (precision/recall).

    Each item in eval_file has `text`, `chat_title`, and `label` (relevant | not).
    Ground-truth positive = label == 'relevant'. Predicted positive = the message
    appears in Phase-1 `results`. Reports a confusion matrix + precision/recall/F1.
    See docs/adr/0001-measure-precision-before-tuning.md.
    """
    env = EnvLoader()

    with open(eval_file, 'r', encoding='utf-8') as f:
        items = yaml.safe_load(f) or []

    messages = []
    truth = {}      # msg_id -> bool (relevant)
    meta = {}       # msg_id -> (chat_title, text)
    for i, it in enumerate(items):
        md = generate_random_metadata(i, it.get('chat_title'))
        mid = md['message_id']
        messages.append({**md, "text": it['text']})
        truth[mid] = str(it.get('label', '')).strip().lower() == 'relevant'
        meta[mid] = (it.get('chat_title', '') or '—', it['text'])

    base_prompt = env.base_prompt
    if prompt_file:
        if os.path.exists(prompt_file):
            with open(prompt_file, 'r', encoding='utf-8') as f:
                base_prompt = f.read()
            print(f"Using custom prompt: {prompt_file}")
        else:
            print(f"Warning: prompt file {prompt_file} not found; using default.")

    analyzer = TextAnalyzer(
        key=resolve_test_key(env), base_prompt=base_prompt,
        phase2_prompt=env.phase2_prompt, model=env.llm_model,
        timezone_name=env.timezone,
    )

    n_pos = sum(truth.values())
    print(f"Model: {env.llm_model} | Prompt: {prompt_file or env.get('BASE_PROMPT_FILE')}")
    print(f"Items: {len(messages)} (relevant: {n_pos}, not: {len(messages) - n_pos})")
    print("Calling LLM (single batch)...")

    t0 = time.time()
    result = analyzer.findMessages(json.dumps(messages, ensure_ascii=False))
    dt = time.time() - t0

    found_ids = {r['message_id'] for r in result.get('results', [])} if result else set()

    TP = FP = FN = TN = 0
    mistakes = []
    for mid, actual in truth.items():
        pred = mid in found_ids
        if pred and actual:
            TP += 1
        elif pred and not actual:
            FP += 1; mistakes.append(('FP', mid))
        elif (not pred) and actual:
            FN += 1; mistakes.append(('FN', mid))
        else:
            TN += 1

    precision = TP / (TP + FP) if (TP + FP) else 0.0
    recall = TP / (TP + FN) if (TP + FN) else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    accuracy = (TP + TN) / len(truth) if truth else 0.0

    print(f"\n--- Phase-1 Eval ({dt:.1f}s) ---")
    print(f"Confusion:  TP={TP}  FP={FP}  FN={FN}  TN={TN}")
    print(f"Precision: {precision:.0%}   Recall: {recall:.0%}   F1: {f1:.2f}   Accuracy: {accuracy:.0%}")
    if mistakes:
        print(f"\nMistakes ({len(mistakes)}):")
        for kind, mid in mistakes:
            ct, txt = meta[mid]
            preview = txt[:90].replace('\n', ' ')
            print(f"  [{kind}] ({ct[:25]}) {preview}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Integration Test for Message Filtering')
    parser.add_argument('--cases', type=str, default='tests/test_cases.yaml', help='Path to test cases YAML file (or JSON)')
    parser.add_argument('--eval', type=str, help='Path to labeled eval set YAML -> precision/recall mode')
    parser.add_argument('--prompt', type=str, help='Path to optional custom prompt file')

    args = parser.parse_args()

    try:
        if args.eval:
            run_eval(args.eval, args.prompt)
        else:
            run_tests(args.cases, args.prompt)
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
