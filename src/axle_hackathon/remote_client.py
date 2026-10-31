"""Private server-side client for the single approved synthetic demo endpoint."""
from dataclasses import dataclass, field
from decimal import Decimal
import json
import os

import httpx

from .axle_api import AxleEvaluationRequest, AxleEvaluationResponse
from .schemas import Evaluation

DEMO_BASE_URL = "https://axle-api-demo.flyboxfly.com"
MAX_RESPONSE_BYTES = 64 * 1024


class RemoteFailure(RuntimeError):
    def __init__(self, category):
        self.category = category
        super().__init__("Remote Axle evaluation could not be verified")


@dataclass(frozen=True)
class RemoteConfig:
    base_url: str
    token: str = field(repr=False)


def browser_transport():
    mode = os.environ.get("AXLE_BROWSER_EVALUATOR", "local")
    if mode not in {"local", "remote"}:
        raise RemoteFailure("configuration")
    return mode


def load_client_config():
    # Exact endpoint prevents accidental credential delivery to arbitrary hosts.
    endpoint = os.environ.get("AXLE_REMOTE_BASE_URL", "")
    token = os.environ.get("AXLE_REMOTE_API_TOKEN", "").strip()
    if endpoint != DEMO_BASE_URL or not token or any(ord(c) < 33 or ord(c) > 126 for c in token):
        raise RemoteFailure("configuration")
    return RemoteConfig(endpoint, token)


def validate_result(raw, confirmed):
    if not isinstance(raw, dict) or set(AxleEvaluationResponse.model_fields) - raw.keys():
        raise RemoteFailure("response")
    expected = {"schema_version": "1.0", "status": "evaluated",
                "source": confirmed.source, "confirmation_basis": "caller_assertion",
                "delivery": "canonical_api"}
    if any(raw.get(key) != value for key, value in expected.items()):
        raise RemoteFailure("response")
    if raw["model_invoked"] is not False or raw["native_connector"] is not False:
        raise RemoteFailure("response")
    evaluation = raw.get("evaluation")
    if not isinstance(evaluation, dict) or set(Evaluation.model_fields) - evaluation.keys():
        raise RemoteFailure("response")
    if evaluation["synthetic"] is not True or evaluation["profile_id"] != "synthetic-box-001":
        raise RemoteFailure("response")
    if evaluation["decision"] not in {"ACCEPT", "NEGOTIATE", "NEED_MORE_INFORMATION", "DECLINE"}:
        raise RemoteFailure("response")
    target = confirmed.benchmark.target_all_mile_rpm
    source = "carrier_unknown" if target is None else "carrier_confirmed"
    if evaluation["benchmark_source"] != source:
        raise RemoteFailure("response")
    returned = evaluation["target_all_mile_rpm"]
    if (target is None and returned is not None) or (target is not None and (returned is None or Decimal(returned) != target)):
        raise RemoteFailure("response")
    return AxleEvaluationResponse.model_validate(raw)


def evaluate_remote(confirmed: AxleEvaluationRequest, config: RemoteConfig):
    """Exactly one POST; phase timeouts, bounded response, no retry/fallback."""
    try:
        # Revalidate at this trust boundary even if a caller constructed a model.
        confirmed = AxleEvaluationRequest.model_validate(confirmed.model_dump(mode="json"))
        if config.base_url != DEMO_BASE_URL:
            raise RemoteFailure("configuration")
        with httpx.Client(base_url=config.base_url, trust_env=False, verify=True,
                          follow_redirects=False,
                          timeout=httpx.Timeout(10.0, connect=5.0, pool=5.0),
                          headers={"Authorization": "Bearer " + config.token}) as client:
            with client.stream("POST", "/api/v1/axle/evaluate",
                               json=confirmed.model_dump(mode="json")) as response:
                if response.status_code != 200:
                    category = "authorization" if response.status_code in {401, 403} else "http_status"
                    raise RemoteFailure(category)
                if response.headers.get("content-type", "").split(";", 1)[0].lower() != "application/json":
                    raise RemoteFailure("response")
                if response.headers.get("cache-control") != "no-store":
                    raise RemoteFailure("response")
                content = bytearray()
                for chunk in response.iter_bytes(chunk_size=4096):
                    content.extend(chunk)
                    if len(content) > MAX_RESPONSE_BYTES:
                        raise RemoteFailure("response")
        return validate_result(json.loads(content), confirmed)
    except RemoteFailure:
        raise
    except httpx.TimeoutException:
        raise RemoteFailure("timeout") from None
    except httpx.RequestError:
        raise RemoteFailure("connection") from None
    except Exception:
        # Never expose HTTP exceptions, response bodies, inputs or credentials.
        raise RemoteFailure("response") from None
