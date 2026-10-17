import importlib
import os

from dotenv import load_dotenv

import config
from src.providers.base import Provider

def available_providers():
    load_dotenv()
    return [
        name
        for name, env_key in config.PROVIDER_KEYS.items()
        if os.getenv(env_key, "").strip()
    ]

def default_provider(
    available: list[str]
) -> str:
    # no terminal to ask on (API server, pipes, CI): DEFAULT_PROVIDER decides, from the environment or config.py
    name = os.getenv("DEFAULT_PROVIDER", "").strip().lower() or config.DEFAULT_PROVIDER
    if name not in available:
        raise RuntimeError(
            f"Found API keys for {', '.join(available)} but DEFAULT_PROVIDER is {name!r}, which has no key. "
            f"Set DEFAULT_PROVIDER to one of: {', '.join(available)}."
        )
    return name

def ask_which(
    available: list[str]
):
    print("Found more than one API key. Which provider do you want to use?")
    for number, name in enumerate(available, start=1):
        print(f"  {number}. {name}")

    while True:
        answer = input("> ").strip().lower()
        if answer in available:
            return answer
        if answer.isdigit() and 1 <= int(answer) <= len(available):
            return available[int(answer) - 1]
        print(f"Enter a number from 1 to {len(available)}, or a provider name.")

def select_provider(
    interactive: bool | None = None
):
    # interactive: may ask on the terminal when several keys are set; None means "if stdin is a terminal"
    available = available_providers()

    if not available:
        keys = ", ".join(config.PROVIDER_KEYS.values())
        raise RuntimeError(f"No API key found. Add one of these to your .env: {keys}")

    if interactive is None:
        interactive = sys.stdin.isatty()
    if len(available) == 1:
        name = available[0]
    elif interactive:
        name = ask_which(available)
    else:
        name = default_provider(available)
    print(f"Using provider: {name}")

    # imported only now, so SDKs for providers you don't use never need to be installed
    module = importlib.import_module("src.providers." + name)
    return Provider(
        name=name,
        complete=module.complete,
        generator_model=config.MODELS[name]["generator"],
        reflector_model=config.MODELS[name]["reflector"],
    )
