"""Bounded model-selected HTTP delegation preview; not a native Muse connector."""
import json
import logging
import os
import time
from .axle_api import AxleEvaluationRequest, AxleEvaluationResponse
from .meta_agent import BASE_URL, MODEL, TOOL, INSTRUCTIONS
from .schemas import Opportunity


class DelegationFailure(RuntimeError):
    def __init__(self, stage):
        super().__init__("External delegation not verified at " + stage)
        self.stage = stage


def delegate_external(client, http, confirmed: AxleEvaluationRequest):
    """Two model requests maximum, exactly one canonical HTTP evaluation.

    Authority (benchmark/confirmation/source) stays outside model arguments.
    No retry, forced call, partial-success return or model arithmetic fallback.
    """
    stage = "tool_selection"
    started = time.monotonic()
    try:
        first = client.responses.create(model=MODEL, instructions=INSTRUCTIONS,
            input="Evaluate this synthetic freight opportunity using Axle. Preserve these confirmed facts exactly:\n" + confirmed.opportunity.model_dump_json(),
            tools=[TOOL], max_output_tokens=2000)
        if first.status != "completed":
            raise ValueError("Incomplete selection")
        calls = [item for item in first.output if item.type == "function_call"]
        if len(calls) != 1 or calls[0].status != "completed" or calls[0].name != TOOL['name']:
            raise ValueError("Expected one completed recognized call")
        call = calls[0]
        op = Opportunity.model_validate_json(call.arguments)
        if op != confirmed.opportunity:
            raise ValueError("Changed confirmed facts")
        stage = "axle_http"
        response = http.post('/api/v1/axle/evaluate', json=confirmed.model_dump(mode='json'))
        response.raise_for_status()
        raw = response.json()
        # Require explicit provenance from the server; do not fill absent defaults.
        if any(raw.get(k) != v for k, v in {
            'schema_version':'1.0', 'status':'evaluated', 'delivery':'canonical_api',
            'confirmation_basis':'caller_assertion', 'source':confirmed.source}.items()):
            raise ValueError("Invalid response provenance")
        if raw.get('model_invoked') is not False or raw.get('native_connector') is not False:
            raise ValueError("Invalid response provenance")
        result = AxleEvaluationResponse.model_validate(raw)
        stage = "after_tool"
        final = client.responses.create(model=MODEL, instructions=INSTRUCTIONS,
            previous_response_id=first.id,
            input=[{'type':'function_call_output', 'call_id':call.call_id,
                    'output':result.model_dump_json()}], tools=[TOOL], max_output_tokens=2000)
        if final.status != 'completed' or any(item.type == 'function_call' for item in final.output):
            raise ValueError("Final response not complete")
        if not isinstance(final.output_text, str) or not final.output_text.strip():
            raise ValueError("Missing final text")
        # Prose is generated but not displayed or treated as validated economics.
        return {'model':MODEL, 'tool_selection_response_id':first.id,
                'final_response_id':final.id, 'call_id':call.call_id,
                'status':'round_trip_completed', 'transport':'loopback_http',
                'tool_result_submitted':True, 'final_text_present':True,
                'model_prose_validated':False, 'native_connector':False,
                'canonical_result':result.model_dump(mode='json')}
    except Exception:
        logging.getLogger(__name__).warning(
            'Axle external delegation failed stage=%s elapsed_ms=%s',
            stage, int((time.monotonic()-started)*1000))
        raise DelegationFailure(stage) from None


def synthetic_request():
    return AxleEvaluationRequest.model_validate({
        'opportunity': {'equipment':'box_truck_26ft', 'payout':'420',
            'loaded_miles':'180','deadhead_miles':'60','diesel_per_gallon':'4',
            'mpg':'10','tolls':'20','driver_cost':'80','maintenance_per_mile':'0.10',
            'equipment_trip_cost':'50','insurance_trip_allocation':'20',
            'operating_hours':'6','schedule_feasible':True},
        'benchmark':{'target_all_mile_rpm':'2.00','confirmed':True},
        'facts_confirmed':True,'source':'manual'})


def main():
    import httpx
    from openai import OpenAI
    if not os.environ.get('MODEL_API_KEY') or not os.environ.get('AXLE_DEMO_TOKEN'):
        raise SystemExit('Set MODEL_API_KEY and AXLE_DEMO_TOKEN locally; never share their values.')
    confirmed = synthetic_request()
    print('Synthetic case: $420, 180 loaded + 60 additional miles; target $2.00/all mile.')
    print('Costs: diesel 4, MPG 10, tolls 20, driver 80, maintenance/mile .10, equipment 50, insurance 20; hours 6; schedule Yes.')
    print('This run can make two paid Meta requests. No automatic retry. No booking.')
    if input('Review these synthetic facts and target; type CONFIRM to run: ').strip() != 'CONFIRM':
        raise SystemExit('Cancelled; no requests made.')
    try:
        with httpx.Client(base_url='http://127.0.0.1:8000', timeout=15, trust_env=False,
                headers={'Authorization':'Bearer '+os.environ['AXLE_DEMO_TOKEN']}) as http:
            # Check server health before spending credits; this does not verify bearer auth.
            preflight = http.get('/api/health')
            preflight.raise_for_status()
            with OpenAI(api_key=os.environ['MODEL_API_KEY'],base_url=BASE_URL,
                        timeout=20,max_retries=0) as client:
                result = delegate_external(client,http,confirmed)
    except DelegationFailure as exc:
        raise SystemExit(str(exc)) from None
    except Exception:
        raise SystemExit('Local preflight/client setup failed. No verified round trip.') from None
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
