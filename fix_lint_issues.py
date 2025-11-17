import os
import re

def fix_common_issues(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    original_content = content

    # Remove trailing whitespace
    content = re.sub(r'[ \t]+$', '', content, flags=re.MULTILINE)

    # Ensure exactly one newline at end of file
    content = content.rstrip('\n') + '\n'

    # Replace multiple empty lines with a single empty line
    content = re.sub(r'\n{3,}', '\n\n', content)

    if content != original_content:
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)
        return True
    return False

def main():
    # Get all Python files in the project
    for root, _, files in os.walk('.'):
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    if fix_common_issues(filepath):
                        print(f"Fixed issues in {filepath}")
                except Exception as e:
                    print(f"Error processing {filepath}: {e}")

if __name__ == '__main__':
    main()
