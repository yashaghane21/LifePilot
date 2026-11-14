"""Ask the configured model one question and show what it cost. A learning and smoke-test tool.

    python -m app.ai.cli "Explain tokens in one sentence"
    python -m app.ai.cli --model anthropic/claude-haiku-5.5 "Same question, cheaper model"
"""

import argparse
import asyncio
import sys

from app.ai.providers.base import ChatMessage, LLMError
from app.ai.providers.factory import close_llm_provider, get_llm_provider

USD_TO_INR = 84  # rough, for intuition only


async def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("question")
    parser.add_argument("--model", help="override LLM_MODEL for this call")
    parser.add_argument("--max-output-tokens", type=int, default=1024)
    args = parser.parse_args()

    try:
        provider = get_llm_provider()
        result = await provider.complete(
            [
                ChatMessage(role="system", content="You are LifePilot, a concise personal assistant."),
                ChatMessage(role="user", content=args.question),
            ],
            model=args.model,
            max_output_tokens=args.max_output_tokens,
        )
    except LLMError as exc:
        print(f"LLM error ({type(exc).__name__}): {exc}", file=sys.stderr)
        return 1
    finally:
        await close_llm_provider()

    print(result.content or "(no text)")
    cost = result.usage.cost_usd
    cost_text = f"${cost:.6f} (~₹{cost * USD_TO_INR:.3f})" if cost is not None else "not reported"
    print(
        f"\n--- {result.model} | {result.usage.input_tokens} in / {result.usage.output_tokens} out tokens"
        f" | cost {cost_text} | {result.latency_ms:.0f} ms | finish: {result.finish_reason}"
        f" | attempts: {result.attempts}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    # Windows consoles default to a legacy code page; force UTF-8 so ₹ and model text print correctly.
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
    sys.exit(asyncio.run(main()))
