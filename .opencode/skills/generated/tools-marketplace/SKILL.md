---
name: tools-marketplace
description: Marketplace tools - product listing, orders, synchronization
load: on-demand
tokens: ~130
---

# Tools Marketplace

## Module: `src/tools/marketplace/`
Multi-platform marketplace integration tools.

### Key Features
- **Product Listing**: Cross-platform publishing
- **Order Sync**: Centralized order management
- **Inventory Sync**: Real-time stock updates
- **Price Management**: Competitive pricing rules
- **Platform Support**: MercadoLibre, Shopify, WooCommerce

### Usage
```python
from src.tools.marketplace import MarketplaceTool
mp = MarketplaceTool()
mp.sync_inventory(platform="mercadolibre")
```

### Key Files
- `src/tools/marketplace/listing.py` - Product listings
- `src/tools/marketplace/orders.py` - Order management
- `src/tools/marketplace/sync.py` - Platform sync
