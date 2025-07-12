"""
Inventory models package

Организация:
- groups.py: InventoryLocation
- movements.py: InventoryMovement (source of truth)
- items.py: InventoryItem, InventoryBatch (cached data)
"""

# Location models
from .locations import (
    InventoryLocation,
    InventoryLocationManager
)

# Movement models (source of truth)
from .movements import (
    InventoryMovement,
    InventoryMovementManager
)

# Item models (cached data)
from .items import (
    InventoryItem,
    InventoryBatch,
    InventoryItemManager,
    InventoryBatchManager
)

# Export all for backward compatibility
__all__ = [
    # Locations
    'InventoryLocation',
    'InventoryLocationManager',

    # Movements
    'InventoryMovement',
    'InventoryMovementManager',

    # Items
    'InventoryItem',
    'InventoryBatch',
    'InventoryItemManager',
    'InventoryBatchManager',
]

# Version info
__version__ = '1.0.0'
__author__ = 'Your Company'