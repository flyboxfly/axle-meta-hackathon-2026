"""Run with python -m axle_hackathon.meta_agent. Never logs credentials or reasoning."""
import json
import logging
import os
import time
from typing import Callable
from .schemas import Evaluation, Opportunity

MODEL = "muse-spark-1.3"
BASE_URL = "https://api.meta.ai/v1"
TOOL = {"type": "function", "name": "evaluate_freight_opportunity",
        "description": "Evaluate a freight opportunity using an authorized synthetic box-truck profile. Call for freight economics; preserve missing inputs.",
        "parameters": Opportunity.model_json_schema()}
INSTRUCTIONS = """You are a personal-agent prototype that delegates freight analysis to Axle.
Use evaluate_freight_opportunity for freight economics. Never invent missing inputs.
Payout is the complete confirmed payout; never add a bid or FSC again.
Use the tool decision and exact returned amounts. Clearly label synthetic context.
Do not claim native Muse integration, booking, profitability, or verified legal compliance.
Explain missing information and give the next useful question. No independent arithmetic."""


def delegate(client, message: str, execute: Callable[[Opportunity], Evaluation]) -> dict:
    trace = []
    evaluations = []
    def request(stage, turn, **kwargs):
        started = time.monotonic()
        try:
            return client.responses.create(**kwargs)
        except Exception:
            # Fixed labels/counts/timing only. Preserve the original exception so
            # the browser boundary still categorizes it and fails closed.
            logging.getLogger(__name__).warning(
                "Axle model request failed stage=%s turn=%s validated_evaluations=%s elapsed_ms=%s",
                stage, turn, len(evaluations), int((time.monotonic() - started) * 1000))
            raise
    response = request("tool_selection", 1, model=MODEL, instructions=INSTRUCTIONS,
        input=message, tools=[TOOL], max_output_tokens=2000)
    for turn in range(3):
        calls = [item for item in response.output if item.type == "function_call"]
        if not calls:
            if not evaluations:
                raise RuntimeError("Model did not delegate; live proof failed")
            return {"model": MODEL, "response_id": response.id, "trace": trace,
                    "evaluations": evaluations, "answer": response.output_text,
                    "usage": response.usage.model_dump() if response.usage else None}
        if len(calls) > 3:
            raise RuntimeError("Tool-call budget exceeded")
        outputs = []
        for call in calls:
            if call.name != TOOL["name"]:
                raise ValueError("Unrecognized tool")
            op = Opportunity.model_validate_json(call.arguments)
            result = Evaluation.model_validate(execute(op))
            evaluations.append(result.model_dump())
            trace.append({"response_id": response.id, "call_id": call.call_id,
                          "tool": call.name, "status": "executed_and_validated"})
            outputs.append({"type": "function_call_output", "call_id": call.call_id,
                            "output": result.model_dump_json()})
        response = request("after_tool", turn + 2, model=MODEL, instructions=INSTRUCTIONS,
            previous_response_id=response.id, input=outputs, tools=[TOOL], max_output_tokens=2000)
    raise RuntimeError("Delegation turn budget exceeded")


def main():
    if not os.environ.get("MODEL_API_KEY") or not os.environ.get("AXLE_DEMO_TOKEN"):
        raise SystemExit("Set MODEL_API_KEY and AXLE_DEMO_TOKEN locally; never paste credentials into chat.")
    import httpx
    from openai import OpenAI
    with httpx.Client(base_url="http://127.0.0.1:8000", timeout=15, trust_env=False,
                      headers={"Authorization": "Bearer " + os.environ["AXLE_DEMO_TOKEN"]}) as http:
        def execute(op):
            response = http.post("/api/v1/freight/evaluate", json=op.model_dump(mode="json"))
            response.raise_for_status()
            return Evaluation.model_validate(response.json())
        client = OpenAI(api_key=os.environ["MODEL_API_KEY"], base_url=BASE_URL,
                        timeout=45, max_retries=0)
        try:
            result = delegate(client, "Ask Axle whether this $420 load meets my all-mile revenue target: 180 loaded miles and 60 deadhead miles, with my 26-foot box truck.", execute)
        except Exception as exc:
            # SDK errors can contain request detail: emit only the class.
            raise SystemExit("Delegation failed: " + type(exc).__name__) from None
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
