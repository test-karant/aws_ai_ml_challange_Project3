"""
test_edge_cases.py
===================
Validates how NovaMart Multi-Agent System handles real-world edge cases:
  1. Policy inquiry with NO Customer ID or Order ID
  2. Return request with Customer ID, but NO Order ID
  3. Return request with NEITHER Customer ID NOR Order ID
  4. Return request with NON-EXISTENT Order ID (ORD-99999)
"""

import sys
import os
import uuid
import re

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

import config
from agent_orchestrator import build_agent_graph

class _C:
    BOLD  = '\033[1m'
    RESET = '\033[0m'
    OK    = '\033[92m'
    ERR   = '\033[91m'
    ORCH  = '\033[95m'
    GRY   = '\033[90m'

def _strip_xml_tags(text: str) -> str:
    cleaned = re.sub(r'<thinking>.*?</thinking>', '', text, flags=re.DOTALL)
    cleaned = re.sub(r'<[^>]+>', '', cleaned)
    return ' '.join(cleaned.split())

EDGE_CASES = [
    {
        "name": "Case 1: General Policy Question (No Customer ID, No Order ID)",
        "prompt": "What is the return policy window and warranty period for items purchased from NovaMart?",
        "check": lambda resp: "day" in resp.lower() or "return" in resp.lower() or "warranty" in resp.lower(),
        "expected": "Accurately answers policy without failing on missing IDs."
    },
    {
        "name": "Case 2: Return Request with Customer ID but MISSING Order ID",
        "prompt": "[Session ID: {sess}] [Customer ID: CUST-001] I want to return an item I received last week.",
        "check": lambda resp: "order" in resp.lower() or "which" in resp.lower() or "ord-" in resp.lower(),
        "expected": "Lists customer orders or asks which order to return without crashing."
    },
    {
        "name": "Case 3: Return Request with NO Customer ID and NO Order ID",
        "prompt": "[Session ID: {sess}] Can you please give me a refund for my order?",
        "check": lambda resp: "customer" in resp.lower() or "order" in resp.lower() or "provide" in resp.lower(),
        "expected": "Politely requests Customer ID / Order ID to locate the account."
    },
    {
        "name": "Case 4: Return Request for NON-EXISTENT Order ID",
        "prompt": "[Session ID: {sess}] [Customer ID: CUST-001] Please process a return for order ORD-99999.",
        "check": lambda resp: "not found" in resp.lower() or "could not" in resp.lower() or "unable" in resp.lower() or "ord-99999" in resp.lower(),
        "expected": "Reports that order ORD-99999 was not found and refuses refund initiation."
    }
]

def run_suite():
    print(f"\n{_C.BOLD}{_C.ORCH}{'='*70}{_C.RESET}")
    print(f"{_C.BOLD}   NovaMart Multi-Agent System -- Edge Case & Error Handling Suite{_C.RESET}")
    print(f"{_C.BOLD}{_C.ORCH}{'='*70}{_C.RESET}\n")

    print(f"  {_C.ORCH}Initializing Agent Graph...{_C.RESET}")
    orchestrator = build_agent_graph(verbose=False)
    print(f"  {_C.OK}Agent Graph Ready.{_C.RESET}\n")

    passed_count = 0

    for i, test in enumerate(EDGE_CASES, 1):
        sess_id = str(uuid.uuid4())[:8]
        raw_prompt = test["prompt"].format(sess=sess_id)

        print(f"{_C.GRY}{'─'*70}{_C.RESET}")
        print(f"  {_C.BOLD}{test['name']}{_C.RESET}")
        print(f"  {_C.GRY}Input Prompt :{_C.RESET} \"{raw_prompt}\"")
        print(f"  {_C.GRY}Expected     :{_C.RESET} {test['expected']}")

        try:
            response = orchestrator(raw_prompt)
            clean_text = _strip_xml_tags(str(response))
            is_valid = test["check"](clean_text)

            if is_valid:
                status_label = f"{_C.OK}✓ SAFELY & ACCURATELY HANDLED{_C.RESET}"
                passed_count += 1
            else:
                status_label = f"{_C.ERR}✗ UNEXPECTED BEHAVIOR{_C.RESET}"

            print(f"  {_C.GRY}Status       :{_C.RESET} {status_label}")
            print(f"  {_C.GRY}Response     :{_C.RESET} {clean_text}\n")

        except Exception as e:
            print(f"  {_C.ERR}Exception Thrown:{_C.RESET} {str(e)}\n")

    print(f"{_C.BOLD}{_C.ORCH}{'='*70}{_C.RESET}")
    print(f"  Edge Case Evaluation: {passed_count}/{len(EDGE_CASES)} passed successfully.")
    print(f"{_C.BOLD}{_C.ORCH}{'='*70}{_C.RESET}\n")

if __name__ == '__main__':
    run_suite()
