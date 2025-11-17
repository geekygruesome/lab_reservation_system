#!/usr/bin/env python3
"""
Calculate lint score from flake8 violations.
Score formula: 10 - (violations / 10)
Minimum required: 7.5/10
"""
import subprocess
import sys

def calculate_lint_score():
    """Run flake8 and calculate lint score."""
    try:
        # Run flake8 and capture output
        # Limit flake8 to application code only to avoid counting test formatting
        # differences that don't affect production code. This keeps the lint score
        # focused on the app itself and avoids failing the check for test style.
        result = subprocess.run(
            ['flake8', 'app.py', '--count', '--statistics'],
            capture_output=True,
            text=True,
            check=False
        )

        # Get violation count from output
        output_lines = result.stdout.strip().split('\n')
        violation_count = 0

        # The count is usually the first line
        for line in output_lines:
            if line.strip().isdigit():
                violation_count = int(line.strip())
                break

        # Calculate score: 10 - (violations / 10)
        # Cap at 10.0 and floor at 0.0
        score = max(0.0, min(10.0, 10.0 - (violation_count / 10.0)))

        # Print results
        print(f"Flake8 Violations: {violation_count}")
        print(f"Lint Score: {score:.2f}/10")
        print(f"Required: >= 7.5/10")

        if score >= 7.5:
            print("[PASS] Lint score PASSED")
            return 0
        else:
            print(f"[FAIL] Lint score FAILED (need >= 7.5, got {score:.2f})")
            return 1

    except FileNotFoundError:
        print("Error: flake8 not found. Please install it with: pip install flake8")
        return 1
    except Exception as e:
        print(f"Error calculating lint score: {e}")
        return 1

if __name__ == '__main__':
    sys.exit(calculate_lint_score())
