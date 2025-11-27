"""Memory system - THE HOLY GRAIL.

This is what makes TwinSync special. It REMEMBERS patterns over time.
"""

from collections import Counter
from datetime import datetime, timedelta
from typing import Optional

from app.core.models import SpotMemory, CheckResult, ToSortItem

# How many days of history to analyze
MEMORY_RETENTION_DAYS = 30

# Minimum appearances to be "recurring"
RECURRING_THRESHOLD = 3


class MemoryEngine:
    """Calculates patterns from check history."""
    
    def __init__(self, checks: list[CheckResult]):
        """Initialize with list of check results."""
        self.checks = checks
    
    def calculate_patterns(self) -> SpotMemory:
        """Calculate all patterns from check history."""
        if not self.checks:
            return SpotMemory(spot_id=0)
        
        spot_id = self.checks[0].spot_id
        memory = SpotMemory(spot_id=spot_id)
        
        # Count items
        memory.recurring_items = self._count_recurring_items()
        
        # Day patterns
        memory.worst_day = self._find_worst_day()
        memory.best_day = self._find_best_day()
        
        # Time patterns
        memory.usually_sorted_by = self._find_usual_sorted_time()
        
        # Stats
        memory.total_checks = len(self.checks)
        memory.current_streak = self._calculate_current_streak()
        memory.longest_streak = self._calculate_longest_streak()
        
        return memory
    
    def _count_recurring_items(self) -> dict[str, int]:
        """Count how often each item appears in to_sort."""
        counter: Counter[str] = Counter()
        
        for check in self.checks:
            for item in check.to_sort:
                # Normalize: lowercase, strip
                normalized = item.item.lower().strip()
                counter[normalized] += 1
        
        # Only keep items that appear at least RECURRING_THRESHOLD times
        return {
            item: count
            for item, count in counter.most_common(20)
            if count >= RECURRING_THRESHOLD
        }
    
    def _find_worst_day(self) -> Optional[str]:
        """Find day with most 'needs_attention' checks."""
        day_counts: dict[str, int] = {
            "Monday": 0, "Tuesday": 0, "Wednesday": 0,
            "Thursday": 0, "Friday": 0, "Saturday": 0, "Sunday": 0
        }
        
        for check in self.checks:
            if check.status.value == "needs_attention":
                day_name = check.timestamp.strftime("%A")
                day_counts[day_name] += 1
        
        if not any(day_counts.values()):
            return None
        
        return max(day_counts, key=day_counts.get)
    
    def _find_best_day(self) -> Optional[str]:
        """Find day with most 'sorted' checks."""
        day_counts: dict[str, int] = {
            "Monday": 0, "Tuesday": 0, "Wednesday": 0,
            "Thursday": 0, "Friday": 0, "Saturday": 0, "Sunday": 0
        }
        
        for check in self.checks:
            if check.status.value == "sorted":
                day_name = check.timestamp.strftime("%A")
                day_counts[day_name] += 1
        
        if not any(day_counts.values()):
            return None
        
        return max(day_counts, key=day_counts.get)
    
    def _find_usual_sorted_time(self) -> Optional[str]:
        """Find most common hour when spot is sorted."""
        sorted_hours: Counter[int] = Counter()
        
        for check in self.checks:
            if check.status.value == "sorted":
                sorted_hours[check.timestamp.hour] += 1
        
        if not sorted_hours:
            return None
        
        most_common_hour = sorted_hours.most_common(1)[0][0]
        
        # Format as "10:00 AM"
        if most_common_hour == 0:
            return "12:00 AM"
        elif most_common_hour < 12:
            return f"{most_common_hour}:00 AM"
        elif most_common_hour == 12:
            return "12:00 PM"
        else:
            return f"{most_common_hour - 12}:00 PM"
    
    def _calculate_current_streak(self) -> int:
        """Calculate consecutive days ending in sorted state."""
        if not self.checks:
            return 0
        
        # Group by date, take last status of each day
        daily_status: dict[str, str] = {}
        for check in sorted(self.checks, key=lambda c: c.timestamp):
            date_str = check.timestamp.date().isoformat()
            daily_status[date_str] = check.status.value
        
        # Count backwards from today
        today = datetime.now().date()
        streak = 0
        
        for i in range(MEMORY_RETENTION_DAYS):
            check_date = (today - timedelta(days=i)).isoformat()
            if check_date in daily_status:
                if daily_status[check_date] == "sorted":
                    streak += 1
                else:
                    break
        
        return streak
    
    def _calculate_longest_streak(self) -> int:
        """Calculate longest ever streak."""
        if not self.checks:
            return 0
        
        # Group by date
        daily_status: dict[str, str] = {}
        for check in sorted(self.checks, key=lambda c: c.timestamp):
            date_str = check.timestamp.date().isoformat()
            daily_status[date_str] = check.status.value
        
        # Find longest run of sorted days
        sorted_dates = sorted(daily_status.keys())
        longest = 0
        current = 0
        
        for date_str in sorted_dates:
            if daily_status[date_str] == "sorted":
                current += 1
                longest = max(longest, current)
            else:
                current = 0
        
        return longest
    
    def is_item_recurring(self, item_name: str) -> bool:
        """Check if an item is recurring."""
        normalized = item_name.lower().strip()
        items = self._count_recurring_items()
        return normalized in items
    
    def get_recurring_count(self, item_name: str) -> int:
        """Get how many times an item has appeared."""
        normalized = item_name.lower().strip()
        items = self._count_recurring_items()
        return items.get(normalized, 0)


def build_memory_context(memory: SpotMemory) -> str:
    """Build context string for AI prompt."""
    if memory.total_checks == 0:
        return "First check - no history yet."
    
    lines = []
    
    # Recurring items
    if memory.recurring_items:
        top = memory.top_recurring[:3]
        recurring_str = ", ".join(f"{item} ({count}x)" for item, count in top)
        lines.append(f"Recurring items: {recurring_str}")
    
    # Streak
    if memory.current_streak > 0:
        lines.append(f"Current streak: {memory.current_streak} days sorted")
        if memory.longest_streak > memory.current_streak:
            lines.append(f"Best streak ever: {memory.longest_streak} days")
    
    # Day patterns
    if memory.worst_day:
        lines.append(f"Toughest day: {memory.worst_day}")
    if memory.best_day:
        lines.append(f"Best day: {memory.best_day}")
    if memory.usually_sorted_by:
        lines.append(f"Usually sorted by: {memory.usually_sorted_by}")
    
    # Stats
    lines.append(f"Total checks: {memory.total_checks}")
    
    return "\n".join(lines) if lines else "First check - no history yet."


def enrich_items_with_recurring(
    items: list[ToSortItem],
    memory: SpotMemory
) -> list[ToSortItem]:
    """Add recurring flag to items based on memory."""
    for item in items:
        normalized = item.item.lower().strip()
        if normalized in memory.recurring_items:
            item.recurring = True
            item.recurring_count = memory.recurring_items[normalized]
    return items
