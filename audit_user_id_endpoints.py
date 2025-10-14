#!/usr/bin/env python3
"""
Audit script to identify all endpoints requiring user_id validation
"""

import re
import os

# Endpoints that require user_id according to documentation
ENDPOINTS_REQUIRING_USER_ID = [
    # Endpoint path, method, parameter location
    ("/chat-queue", "POST", "Form"),
    ("/status/{session_id}", "GET", "Query"),
    ("/download/{session_id}", "GET", "Query"),
    ("/results/{session_id}", "GET", "Query"),
    ("/stop/{session_id}", "POST", "Query"),
    ("/snapshots/{session_id}", "GET", "Query"),
    ("/continue-session", "POST", "Form"),
    ("/multiturn-session/{session_id}", "GET", "Query"),
    ("/multiturn-sessions", "GET", "Query"),
    ("/all-sessions", "GET", "Query"),
    ("/hard-delete/{session_id}", "DELETE", "Query"),
]

def find_endpoint_in_code(file_path, endpoint_path, method):
    """Find endpoint definition in code"""
    with open(file_path, 'r') as f:
        content = f.read()

    # Convert endpoint path to regex pattern
    pattern = endpoint_path.replace("{", r"\{").replace("}", r"\}")

    # Find the decorator and function
    regex = rf'@app\.{method.lower()}\(["\']({pattern})["\'].*?\n.*?async def (\w+)\((.*?)\):'
    matches = re.finditer(regex, content, re.IGNORECASE | re.DOTALL)

    results = []
    for match in matches:
        func_name = match.group(2)
        params = match.group(3)
        start_pos = match.start()
        line_num = content[:start_pos].count('\n') + 1

        results.append({
            'function': func_name,
            'params': params,
            'line': line_num,
            'has_user_id': 'user_id' in params
        })

    return results

def check_user_id_validation(file_path, func_name, line_num):
    """Check if function has user_id validation"""
    with open(file_path, 'r') as f:
        lines = f.readlines()

    # Look at the next 20 lines after function definition
    start = line_num
    end = min(line_num + 20, len(lines))

    function_code = ''.join(lines[start:end])

    # Check for validation patterns
    has_validation = False
    validation_patterns = [
        r'if not user_id',
        r'if user_id is None',
        r'if not user_id or user_id\.strip\(\)',
        r'user_id.*required',
        r'raise.*user_id'
    ]

    for pattern in validation_patterns:
        if re.search(pattern, function_code, re.IGNORECASE):
            has_validation = True
            break

    return has_validation, function_code[:300]

def main():
    server_file = "/home/ubuntu/dleader_agent/agent_fastapi_server_multiturn.py"

    print("=" * 80)
    print("USER_ID VALIDATION AUDIT")
    print("=" * 80)
    print()

    issues = []
    validated = []

    for endpoint_path, method, param_location in ENDPOINTS_REQUIRING_USER_ID:
        print(f"\n{'='*80}")
        print(f"Endpoint: {method} {endpoint_path}")
        print(f"Parameter Location: {param_location}")
        print("-" * 80)

        results = find_endpoint_in_code(server_file, endpoint_path, method)

        if not results:
            print(f"❌ ENDPOINT NOT FOUND IN CODE")
            issues.append({
                'endpoint': f"{method} {endpoint_path}",
                'issue': 'Endpoint not found in code'
            })
            continue

        for result in results:
            print(f"Function: {result['function']} (Line {result['line']})")
            print(f"Has user_id parameter: {result['has_user_id']}")

            if not result['has_user_id']:
                print(f"❌ MISSING user_id PARAMETER")
                issues.append({
                    'endpoint': f"{method} {endpoint_path}",
                    'function': result['function'],
                    'issue': 'Missing user_id parameter'
                })
                continue

            # Check for validation
            has_validation, code_snippet = check_user_id_validation(
                server_file,
                result['function'],
                result['line']
            )

            if has_validation:
                print(f"✅ HAS VALIDATION for empty user_id")
                validated.append({
                    'endpoint': f"{method} {endpoint_path}",
                    'function': result['function'],
                    'line': result['line']
                })
            else:
                print(f"⚠️  NO VALIDATION for empty user_id")
                print(f"Code snippet:\n{code_snippet}")
                issues.append({
                    'endpoint': f"{method} {endpoint_path}",
                    'function': result['function'],
                    'line': result['line'],
                    'issue': 'Missing validation for empty user_id'
                })

    # Summary
    print("\n" + "=" * 80)
    print("AUDIT SUMMARY")
    print("=" * 80)
    print(f"\nTotal endpoints checked: {len(ENDPOINTS_REQUIRING_USER_ID)}")
    print(f"✅ Properly validated: {len(validated)}")
    print(f"⚠️  Issues found: {len(issues)}")

    if validated:
        print("\n✅ VALIDATED ENDPOINTS:")
        for item in validated:
            print(f"  - {item['endpoint']} ({item['function']} at line {item['line']})")

    if issues:
        print("\n⚠️  ENDPOINTS NEEDING ATTENTION:")
        for item in issues:
            print(f"  - {item['endpoint']}")
            print(f"    Function: {item.get('function', 'N/A')}")
            print(f"    Issue: {item['issue']}")
            if 'line' in item:
                print(f"    Line: {item['line']}")
            print()

    return len(issues) == 0

if __name__ == "__main__":
    success = main()
    exit(0 if success else 1)
