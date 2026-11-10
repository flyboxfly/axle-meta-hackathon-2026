"""Offline TomTom contract tests with fictional locations."""
import asyncio
from decimal import Decimal

import httpx
import pytest

from axle_hackathon.opening_tomtom import (
    DeadheadTruck, PickupCandidate, RoutePoint, TomTomDeadhead, TomTomUnavailable,
)


def test_pickups_require_separate_route_request_and_use_truck_specs():
    requests = []

    def respond(request):
        requests.append(request)
        if request.url.path.startswith("/search/"):
            return httpx.Response(200, json={"results": [
                {
                    "type": "Point Address",
                    "address": {"freeformAddress": address},
                    "position": {"lat": 40.1, "lon": longitude},
                }
                for address, longitude in (("1 Fictional Dock", -74.2), ("2 Fictional Dock", -74.3))
            ]})
        return httpx.Response(200, json={"routes": [{"summary": {"lengthInMeters": 16093}}]})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = TomTomDeadhead(client, "mock-key")
            candidates = await adapter.find_pickups("Fictional Dock")
            assert [item.address for item in candidates] == ["1 Fictional Dock", "2 Fictional Dock"]
            assert len(requests) == 1
            origin = RoutePoint(latitude="40.2", longitude="-74.4")
            truck = DeadheadTruck(height_m="3.8", width_m="2.6", length_m="10.2", weight_kg=7500)
            miles = await adapter.estimate_miles(origin, candidates[1], truck)
            assert miles == Decimal(16093) / Decimal("1609.344")

    asyncio.run(run())
    assert requests[0].url.params["countrySet"] == "US"
    assert "40.2,-74.4:40.1,-74.3" in requests[1].url.path
    assert dict(requests[1].url.params) == {
        "key": "mock-key", "travelMode": "truck", "vehicleCommercial": "true",
        "vehicleHeight": "3.8", "vehicleWidth": "2.6", "vehicleLength": "10.2",
        "vehicleWeight": "7500", "routeRepresentation": "summaryOnly",
    }


@pytest.mark.parametrize("result", ["timeout", "quota", "no_route", "invalid_length"])
def test_failures_leave_mileage_unavailable_without_leaking_inputs(result):
    def respond(request):
        if result == "timeout":
            raise httpx.ReadTimeout(str(request.url), request=request)
        if result == "quota":
            return httpx.Response(429)
        routes = [] if result == "no_route" else [{"summary": {"lengthInMeters": True}}]
        return httpx.Response(200, json={"routes": routes})

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
            adapter = TomTomDeadhead(client, "mock-key")
            point = RoutePoint(latitude="40.2", longitude="-74.4")
            pickup = PickupCandidate(address="Fictional Dock", point=point)
            truck = DeadheadTruck(height_m="3.8", width_m="2.6", length_m="10.2", weight_kg=7500)
            with pytest.raises(TomTomUnavailable) as exc:
                await adapter.estimate_miles(point, pickup, truck)
            assert "mock-key" not in str(exc.value)
            assert "-74.4" not in str(exc.value)

    asyncio.run(run())
