import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

import config
from src.api.response import build_response
from src.api.service import Attachment, Clearance, answer_question

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ask Company Brain a question.")
    parser.add_argument("question", nargs="*", help="the question; asked interactively when left out")
    parser.add_argument("-c", "--context", help="text file holding the context to answer from")
    parser.add_argument(
        "--clearance-level", type=int, default=config.MAX_CLEARANCE_LEVEL,
        help="what the asker may see, from 0 to %(default)s",
    )
    parser.add_argument(
        "-a", "--attachment", action="append", default=[], metavar="PATH",
        help="a file to attach; repeatable",
    )
    args = parser.parse_args()

    context = ""
    if args.context:
        if not os.path.isfile(args.context):
            raise SystemExit(f"Context file not found: {args.context}")
        with open(args.context, encoding="utf-8") as f:
            context = f.read()

    attachments = []
    for path in args.attachment:
        if not os.path.isfile(path):
            raise SystemExit(f"Attachment not found: {path}")
        with open(path, "rb") as f:
            data = f.read()
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            text = ""
        attachments.append(Attachment(filename=os.path.basename(path), text=text, data=data))

    question = " ".join(args.question).strip() or input("Ask Company Brain a question:\n> ").strip()
    if question == "":
        raise SystemExit("No question given.")

    user = Clearance(level=args.clearance_level)
    answer = answer_question(question, context, user=user, attachments=attachments)
    print(json.dumps(build_response(answer.result), indent=2, ensure_ascii=False))
