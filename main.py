import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.providers.router import select_provider
from src.workflow.reflexion import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask Company Brain a question.")
    parser.add_argument("context", help="text file holding the context to answer from")
    parser.add_argument("question", help="the question")
    args = parser.parse_args()

    if not os.path.isfile(args.context):
        raise SystemExit(f"Context file not found: {args.context}")
    with open(args.context, encoding="utf-8") as f:
        context = f.read()

    provider = select_provider()
    result = run(provider, args.question, context)
    print(result.markdown)
