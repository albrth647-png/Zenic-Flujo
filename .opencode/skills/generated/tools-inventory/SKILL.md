---
name: tools-inventory
description: Inventory management - stock control, products, warehouses, movements
load: on-demand
tokens: ~140
---

# Tools Inventory

## Module: `src/tools/inventory/`
Inventory and stock management tools.

### Key Features
- **Product Management**: Products, variants, SKUs
- **Stock Control**: Real-time inventory tracking
- **Warehouse Management**: Multi-warehouse support
- **Movements**: Transfers, adjustments, write-offs
- **Low Stock Alerts**: Automated reorder notifications

### Usage
```python
from src.tools.inventory import InventoryTool
inv = InventoryTool()
product = inv.create_product(name="Widget", sku="WID-001", stock=100)
```

### Key Files
- `src/tools/inventory/products.py` - Product management
- `src/tools/inventory/stock.py` - Stock control
- `src/tools/inventory/warehouse.py` - Warehouse ops
