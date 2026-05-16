"""
Live inventory simulation.
Applies random depletion events (other orders consuming stock) and optional
vendor delay events to give each run a realistic, varied stock picture.

Env:
  SIMULATE_INVENTORY=true    enable random depletion
  SIMULATE_VENDOR_DELAY=true inject a vendor delay event on the highest-demand item
  SIM_SEED                   integer seed for reproducibility (optional)
"""

from __future__ import annotations

import os
import random
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class SimulationSnapshot:
    stock: Dict[str, float]
    events: List[str] = field(default_factory=list)


class InventorySimulator:
    """
    Simulates real-time inventory state by applying concurrent-order depletion
    and optional vendor delay events to a base stock dict.
    """

    DEPLETION_ITEMS = [
        "rice_kg",
        "mixed_vegetables_kg",
        "protein_kg",
        "fruit_kg",
        "seasoning_pack",
    ]

    def __init__(self, base_stock: Dict[str, float]) -> None:
        self._base = dict(base_stock)
        seed_env = os.getenv("SIM_SEED", "").strip()
        self._rng = random.Random(int(seed_env)) if seed_env else random.Random()

    def run(self) -> SimulationSnapshot:
        stock = dict(self._base)
        events: List[str] = []

        # Simulate 1-3 concurrent orders depleting stock
        num_orders = self._rng.randint(1, 3)
        for order_num in range(1, num_orders + 1):
            for item in self.DEPLETION_ITEMS:
                if item not in stock:
                    continue
                depletion_pct = self._rng.uniform(0.05, 0.35)
                depleted = round(stock[item] * depletion_pct, 2)
                stock[item] = round(max(0.0, stock[item] - depleted), 2)
                if depleted > 0:
                    events.append(
                        f"Order #{order_num}: {depleted} {item} consumed by concurrent booking."
                    )

        # Optional vendor delay injection
        if os.getenv("SIMULATE_VENDOR_DELAY", "false").strip().lower() in ("1", "true", "yes"):
            delayed_item = max(self._base, key=lambda k: self._base[k])
            extra_days = self._rng.randint(1, 3)
            events.append(
                f"VENDOR DELAY: {delayed_item} supplier delayed by {extra_days} day(s) — "
                "consider alternative sourcing."
            )
            # Reduce available stock to simulate the delay impact
            if delayed_item in stock:
                stock[delayed_item] = round(stock[delayed_item] * 0.5, 2)

        return SimulationSnapshot(stock=stock, events=events)
