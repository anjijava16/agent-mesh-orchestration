"""Crestline's prose. Whatever model they use is their business."""

from __future__ import annotations

from refundry.models import SellerResponse


async def phrase(response: SellerResponse) -> str:
    return response.message
