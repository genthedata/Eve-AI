from typing import Any, Dict, List


class SchedulerAPITool:
    """Staff and delivery slot templates (mock scheduler API)."""

    def build_timeline(self, event_date: str) -> List[Dict[str, str]]:
        return [
            {"step": "Procurement completion", "time": f"{event_date} 07:00"},
            {"step": "Food preparation starts", "time": f"{event_date} 09:00"},
            {"step": "Packing and QA", "time": f"{event_date} 13:00"},
            {"step": "Dispatch", "time": f"{event_date} 15:00"},
            {"step": "On-site setup", "time": f"{event_date} 16:00"},
        ]

    def allocate_resources(self, guest_count: int) -> Dict[str, int]:
        return {
            "kitchen_staff": max(3, guest_count // 50),
            "delivery_vehicles": max(1, guest_count // 120),
        }

    def assess_logistics_risks(
        self, guest_count: int, shortage_count: int, vehicles: int
    ) -> List[str]:
        risks: List[str] = []
        if shortage_count > 2:
            risks.append("High procurement dependency before prep starts.")
        if vehicles == 1 and guest_count > 180:
            risks.append("Single-vehicle dispatch may cause delays.")
        return risks
