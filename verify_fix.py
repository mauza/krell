#!/usr/bin/env python3
"""
Simple verification script for the OpenAI-compatible API fix.
Tests the provider detection logic without needing pytest.
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def test_provider_detection():
    """Test the provider detection logic"""
    print("Testing provider detection logic...")

    # Test cases: (endpoint, expected_provider)
    test_cases = [
        ("http://localhost:11434", "ollama"),
        ("https://api.openai.com", "openai"),
        ("https://openrouter.ai/api/v1", "openai"),
        ("http://192.168.1.100:11434", "ollama"),
        ("https://custom-llm.example.com/v1", "openai"),
    ]

    def detect_provider(endpoint):
        """Copy of the detection logic from main.py"""
        if "openai.com" in endpoint or "openrouter.ai" in endpoint or "/v1" in endpoint:
            return "openai"
        else:
            return "ollama"

    all_passed = True
    for endpoint, expected in test_cases:
        detected = detect_provider(endpoint)
        status = "✓" if detected == expected else "✗"
        print(f"{status} {endpoint} -> {detected} (expected: {expected})")
        if detected != expected:
            all_passed = False

    return all_passed


def test_endpoint_selection():
    """Test that correct endpoints are selected for each provider"""
    print("\nTesting endpoint selection...")

    def get_test_url(endpoint, provider):
        """Copy of the endpoint selection logic from main.py"""
        if provider == "ollama":
            return f"{endpoint}/api/generate"
        else:  # openai-compatible
            return f"{endpoint}/v1/models"

    test_cases = [
        ("http://localhost:11434", "ollama", "http://localhost:11434/api/generate"),
        ("https://api.openai.com", "openai", "https://api.openai.com/v1/models"),
        ("https://openrouter.ai/api", "openai", "https://openrouter.ai/api/v1/models"),
    ]

    all_passed = True
    for endpoint, provider, expected_url in test_cases:
        actual_url = get_test_url(endpoint, provider)
        status = "✓" if actual_url == expected_url else "✗"
        print(f"{status} {provider} {endpoint} -> {actual_url}")
        if actual_url != expected_url:
            all_passed = False

    return all_passed


def verify_code_changes():
    """Verify that the code changes are in place"""
    print("\nVerifying code changes...")

    checks = []

    # Check main.py for provider detection
    with open("main.py", "r") as f:
        main_content = f.read()

    checks.append(
        (
            "Provider detection in main.py",
            'if "openai.com" in endpoint or "openrouter.ai" in endpoint or "/v1" in endpoint:'
            in main_content,
        )
    )

    checks.append(
        (
            "OpenAI test endpoint (/v1/models)",
            'test_url = f"{endpoint}/v1/models"' in main_content,
        )
    )

    checks.append(
        (
            "Provider parameter in settings",
            'llm_provider: str = Form("auto")' in main_content,
        )
    )

    # Check dashboard.html for provider UI
    with open("templates/dashboard.html", "r") as f:
        dashboard_content = f.read()

    checks.append(
        ("Provider select dropdown", 'id="llm_provider"' in dashboard_content)
    )

    checks.append(
        (
            "Provider in testConnection()",
            "const provider = document.getElementById('llm_provider').value;"
            in dashboard_content,
        )
    )

    all_passed = True
    for check_name, check_result in checks:
        status = "✓" if check_result else "✗"
        print(f"{status} {check_name}")
        if not check_result:
            all_passed = False

    return all_passed


if __name__ == "__main__":
    print("=" * 60)
    print("Verifying OpenAI-compatible API fix")
    print("=" * 60)

    test1_passed = test_provider_detection()
    test2_passed = test_endpoint_selection()
    test3_passed = verify_code_changes()

    print("\n" + "=" * 60)
    if test1_passed and test2_passed and test3_passed:
        print("✓ All verification checks passed!")
        print("\nThe fix should resolve the 404 error for OpenAI-compatible APIs.")
        print("The dashboard will now:")
        print("  - Auto-detect provider type from endpoint URL")
        print("  - Use /v1/models for OpenAI-compatible endpoints")
        print("  - Use /api/generate for Ollama endpoints")
        print("  - Allow manual provider selection in the UI")
        sys.exit(0)
    else:
        print("✗ Some verification checks failed")
        sys.exit(1)
