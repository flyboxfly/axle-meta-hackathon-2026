"""Opt-in TomTom transport for deadhead planning.

Callers disclose provider processing, confirm the pickup candidate and truck
specs, and check the trip revision before applying any estimate. This module
does not read environment credentials or modify trip state.
"""

import asyncio
from decimal import Decimal
from secrets import token_urlsafe
from urllib.parse import quote

import httpx
from pydantic import Field, ValidationError

from .pilot import Frozen


class RoutePoint(Frozen):
    latitude: Decimal = Field(ge=-90, le=90, allow_inf_nan=False)
    longitude: Decimal = Field(ge=-180, le=180, allow_inf_nan=False)


class PickupCandidate(Frozen):
    address: str = Field(min_length=1, max_length=300)
    point: RoutePoint


class DeadheadTruck(Frozen):
    height_m: Decimal = Field(ge=Decimal("0.01"), max_digits=5, decimal_places=2)
    width_m: Decimal = Field(ge=Decimal("0.01"), max_digits=5, decimal_places=2)
    length_m: Decimal = Field(ge=Decimal("0.01"), max_digits=5, decimal_places=2)
    weight_kg: int = Field(gt=0, strict=True)


class TomTomUnavailable(RuntimeError):
    """Provider failure with a message safe for logs and chat."""


class TomTomDeadhead:
    def __init__(self, client: httpx.AsyncClient, api_key: str):
        if not api_key.strip():
            raise ValueError("TomTom requires a configured API key")
        self._client = client
        self._api_key = api_key

    async def _get(self, path: str, params: dict) -> dict:
        try:
            async with asyncio.timeout(5):
                response = await self._client.get(
                    "https://api.tomtom.com" + path,
                    params={"key": self._api_key, **params},
                    timeout=4,
                    follow_redirects=False,
                )
                response.raise_for_status()
                data = response.json()
        except (TimeoutError, httpx.HTTPError, ValueError):
            raise TomTomUnavailable("TomTom lookup unavailable") from None
        if not isinstance(data, dict):
            raise TomTomUnavailable("Invalid TomTom response")
        return data

    async def find_pickups(self, address: str) -> tuple[PickupCandidate, ...]:
        address = address.strip()
        if not 1 <= len(address) <= 200:
            raise ValueError("Enter a pickup street address")
        data = await self._get(
            f"/search/2/geocode/{quote(address, safe='')}.json",
            {"countrySet": "US", "limit": 5},
        )
        candidates = []
        try:
            for result in data["results"][:5]:
                if result["type"] not in {"Point Address", "Address Range"}:
                    continue
                position = result["position"]
                candidates.append(PickupCandidate(
                    address=result["address"]["freeformAddress"],
                    point=RoutePoint(latitude=position["lat"], longitude=position["lon"]),
                ))
        except (KeyError, TypeError, ValidationError):
            raise TomTomUnavailable("Invalid TomTom pickup response") from None
        return tuple(candidates)

    async def estimate_miles(
        self, origin: RoutePoint, pickup: PickupCandidate, truck: DeadheadTruck,
    ) -> Decimal:
        destination = pickup.point
        locations = (
            f"{origin.latitude:f},{origin.longitude:f}:"
            f"{destination.latitude:f},{destination.longitude:f}"
        )
        data = await self._get(f"/routing/1/calculateRoute/{locations}/json", {
            "travelMode": "truck",
            "vehicleCommercial": "true",
            "vehicleHeight": str(truck.height_m),
            "vehicleWidth": str(truck.width_m),
            "vehicleLength": str(truck.length_m),
            "vehicleWeight": truck.weight_kg,
            "routeRepresentation": "summaryOnly",
        })
        try:
            meters = data["routes"][0]["summary"]["lengthInMeters"]
        except (IndexError, KeyError, TypeError):
            raise TomTomUnavailable("TomTom returned no usable truck route") from None
        if type(meters) is not int or not 0 <= meters <= 160_934_400:
            raise TomTomUnavailable("Invalid TomTom route length")
        return Decimal(meters) / Decimal("1609.344")


async def telegram_deadhead(conversation, user, chat, text, adapter, truck):
    """Offer, resolve and apply a route for the exact active draft."""
    inbox = conversation.inbox
    with inbox._lock:
        carrier = inbox._carrier(user, chat)
        flow = conversation._flows[carrier]
        inbox._access(user, chat, flow["token"])
        snapshot = conversation.opening.get(user, chat)
        trip = snapshot.trip
        if truck is None or not trip.approximate_truck_pin or not trip.pickup:
            return ("A truck routing profile, shared pin and pickup street address are required. "
                    "You can enter deadhead miles manually."), flow["nonce"]
        if snapshot.draft.facts.deadhead_miles is not None:
            return "This draft already has deadhead miles. Edit them directly if needed.", flow["nonce"]
        parts = text.split()
        if len(parts) == 1:
            nonce = token_urlsafe(12)
            flow["tomtom_generation"] = object()
            flow["tomtom"] = (snapshot, flow["nonce"], nonce, ())
            return (
                "TomTom receives the pickup address for lookup. After you choose a match, "
                "TomTom receives your approximate truck pin, the pickup coordinates and "
                "truck dimensions and weight. The result is a planning estimate. "
                f"To send the pickup address, reply /deadhead {nonce} search."
            ), flow["nonce"]
        pending = flow.get("tomtom")
        if (len(parts) != 3 or pending is None or pending[0] is not snapshot
                or pending[1] != flow["nonce"] or pending[2] != parts[1]):
            return "This route request expired. Send /deadhead to start again.", flow["nonce"]
        candidates = pending[3]
        searching = not candidates and parts[2] == "search"
        if not searching and parts[2] not in {str(i) for i in range(1, len(candidates) + 1)}:
            return "Use the search or pickup selection command shown in the route prompt.", flow["nonce"]
        # Consume the request before releasing the lock. New edits can proceed during I/O.
        del flow["tomtom"]
        nonce = flow["nonce"]
        generation = flow["tomtom_generation"]

    failure = "TomTom mileage is unavailable. Enter deadhead miles manually."
    try:
        if searching:
            candidates = await adapter.find_pickups(trip.pickup)
        else:
            pickup = candidates[int(parts[2]) - 1]
            origin = RoutePoint(
                latitude=trip.approximate_truck_pin[0], longitude=trip.approximate_truck_pin[1],
            )
            miles = await adapter.estimate_miles(origin, pickup, truck)
    except TomTomUnavailable:
        failed = True
    else:
        failed = False

    with inbox._lock:
        current = conversation._flows.get(carrier)
        if (current is not flow or flow["nonce"] != nonce or flow.get("tomtom_generation") is not generation
                or conversation.opening.get(user, chat) is not snapshot):
            return None
        inbox._access(user, chat, flow["token"])
        if failed:
            return failure, nonce
        if searching:
            if not candidates:
                return "No matching street address. Refine the pickup or enter deadhead miles manually.", nonce
            selection = token_urlsafe(12)
            flow["tomtom"] = (snapshot, nonce, selection, candidates)
            options = "\n".join(f"{i}. {item.address}" for i, item in enumerate(candidates, 1))
            return (
                f"Confirm the pickup before routing:\n{options}\n"
                f"Send /deadhead {selection} NUMBER to confirm your choice."
            ), nonce
        source = "TomTom estimate"
        draft = snapshot.draft.model_copy(update={
            "facts": snapshot.draft.facts.model_copy(update={"deadhead_miles": miles}),
            "evidence": {**snapshot.draft.evidence, "deadhead_miles": source},
        })
        updated = conversation.opening.put(
            user, chat, draft, snapshot.pricing, expected_revision=snapshot.revision,
            trip=trip,
            counter_offer=snapshot.counter_offer, counter_note=snapshot.counter_note,
            sources={**snapshot.sources, "deadhead_miles": source},
        )
        return (f"Pickup used for routing: {pickup.address}\n"
                + conversation._review_trip(user, chat, carrier, flow, updated)), flow["nonce"]
