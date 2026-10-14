import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from src.providers.router import select_provider
from src.workflow.reflexion import run

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask Company Brain a question.")
    parser.add_argument("question", nargs="*", help="the question; asked interactively when left out")
    parser.add_argument("-c", "--context", help="text file holding the context to answer from")
    args = parser.parse_args()

    context = ""
    if args.context:
        if not os.path.isfile(args.context):
            raise SystemExit(f"Context file not found: {args.context}")
        with open(args.context, encoding="utf-8") as f:
            context = f.read()

    provider = select_provider()
    question = " ".join(args.question).strip() or input("Ask Company Brain a question:\n> ").strip()
    if question == "":
        raise SystemExit("No question given.")

    result = run(provider, question, context)
    print(result.markdown)
