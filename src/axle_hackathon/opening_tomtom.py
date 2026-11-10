"""Opt-in TomTom transport for deadhead planning.

Callers disclose provider processing, confirm the pickup candidate and truck
specs, and check the trip revision before applying any estimate. This module
does not read environment credentials or modify trip state.
"""

import asyncio
from decimal import Decimal
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
