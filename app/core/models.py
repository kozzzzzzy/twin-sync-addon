"""Data models for TwinSync Spot."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class SpotType(str, Enum):
    """Types of spots with pre-filled templates."""
    WORK = "work"
    CHILL = "chill"
    SLEEP = "sleep"
    KITCHEN = "kitchen"
    ENTRYWAY = "entryway"
    STORAGE = "storage"
    CUSTOM = "custom"


SPOT_TYPES = {
    SpotType.WORK: {
        "label": "💼 Work / Focus Desk",
        "template": """This is my work area. I need a clear surface to focus.

Things that should be here:
- Laptop/monitor
- Notebook and pen
- Water bottle

Things that shouldn't be here:
- Dirty dishes or cups
- Random papers or mail
- Clothes"""
    },
    SpotType.CHILL: {
        "label": "🛋️ Chill / Relaxing Area",
        "template": """This is where I relax. Should feel calm and uncluttered.

Things that are fine here:
- Remote controls in their spot
- A book or two
- Throw blanket folded

Things that shouldn't pile up:
- Empty glasses or plates
- Random stuff from pockets
- Laundry"""
    },
    SpotType.SLEEP: {
        "label": "🛏️ Sleep Zone",
        "template": """This is my sleep space. Should be calm and ready for rest.

Ready state:
- Bed made (or at least neat)
- Nightstand clear except lamp/phone charger
- No clothes on floor
- Blinds/curtains in position"""
    },
    SpotType.KITCHEN: {
        "label": "🍳 Cooking / Kitchen",
        "template": """This is my kitchen area. Should be clear and ready to use.

Ready state:
- Counters wiped and clear
- Dishes washed or in dishwasher
- No food left out
- Sink empty"""
    },
    SpotType.ENTRYWAY: {
        "label": "🚪 Entryway / Hallway",
        "template": """This is my entryway. First thing I see coming home.

Ready state:
- Shoes in rack or lined up
- Keys/wallet in their spot
- No bags dumped on floor
- Coat hung up"""
    },
    SpotType.STORAGE: {
        "label": "📦 Storage Area",
        "template": """This is a storage area. Things should be organised.

What belongs here:
- [List your items]

Signs it needs sorting:
- Things not in their containers
- Items blocking access
- Stuff that doesn't belong here"""
    },
    SpotType.CUSTOM: {
        "label": "✨ Something else",
        "template": """Describe this spot in your own words.

What is it for?

What should it look like when ready?

What are signs it needs attention?"""
    },
}


class SpotStatus(str, Enum):
    """Status of a spot."""
    SORTED = "sorted"
    NEEDS_ATTENTION = "needs_attention"
    UNKNOWN = "unknown"
    CHECKING = "checking"
    ERROR = "error"


@dataclass
class Spot:
    """A location being tracked."""
    id: int
    name: str
    camera_entity: str
    definition: str
    spot_type: SpotType
    voice: str
    created_at: datetime
    
    # Current state
    status: SpotStatus = SpotStatus.UNKNOWN
    last_check: Optional[datetime] = None
    current_streak: int = 0
    longest_streak: int = 0
    
    # Snooze
    snoozed_until: Optional[datetime] = None
    
    @property
    def is_snoozed(self) -> bool:
        if not self.snoozed_until:
            return False
        return datetime.now() < self.snoozed_until
    
    @property
    def status_emoji(self) -> str:
        if self.is_snoozed:
            return "💤"
        return {
            SpotStatus.SORTED: "✅",
            SpotStatus.NEEDS_ATTENTION: "⚠️",
            SpotStatus.UNKNOWN: "❓",
            SpotStatus.CHECKING: "🔄",
            SpotStatus.ERROR: "❌",
        }.get(self.status, "❓")
    
    @property
    def status_text(self) -> str:
        if self.is_snoozed:
            return "Snoozed"
        return {
            SpotStatus.SORTED: "Sorted",
            SpotStatus.NEEDS_ATTENTION: "Needs Attention",
            SpotStatus.UNKNOWN: "Not checked yet",
            SpotStatus.CHECKING: "Checking...",
            SpotStatus.ERROR: "Error",
        }.get(self.status, "Unknown")


@dataclass
class ToSortItem:
    """An item that needs sorting."""
    item: str
    location: Optional[str] = None
    recurring: bool = False
    recurring_count: int = 0


@dataclass
class CheckResult:
    """Result of a spot check."""
    id: int
    spot_id: int
    timestamp: datetime
    status: SpotStatus
    
    to_sort: list[ToSortItem] = field(default_factory=list)
    looking_good: list[str] = field(default_factory=list)
    
    notes_main: Optional[str] = None
    notes_pattern: Optional[str] = None
    notes_encouragement: Optional[str] = None
    
    error_message: Optional[str] = None
    api_response_time: float = 0.0
    
    @property
    def to_sort_count(self) -> int:
        return len(self.to_sort)
    
    @property
    def looking_good_count(self) -> int:
        return len(self.looking_good)


@dataclass
class SpotMemory:
    """Memory/patterns for a spot."""
    spot_id: int
    
    # Recurring items: {"coffee mug": 12, "papers": 5}
    recurring_items: dict[str, int] = field(default_factory=dict)
    
    # Patterns
    usually_sorted_by: Optional[str] = None  # "10:00 AM"
    worst_day: Optional[str] = None  # "Monday"
    best_day: Optional[str] = None  # "Sunday"
    
    # Stats
    total_checks: int = 0
    total_resets: int = 0
    current_streak: int = 0
    longest_streak: int = 0
    last_reset: Optional[datetime] = None
    
    @property
    def top_recurring(self) -> list[tuple[str, int]]:
        """Get top 5 recurring items."""
        sorted_items = sorted(
            self.recurring_items.items(),
            key=lambda x: x[1],
            reverse=True
        )
        return sorted_items[:5]


@dataclass
class Camera:
    """A camera source."""
    entity_id: str
    name: str
    source_type: str = "ha"  # "ha", "rtsp", "http"
    url: Optional[str] = None  # For RTSP/HTTP
