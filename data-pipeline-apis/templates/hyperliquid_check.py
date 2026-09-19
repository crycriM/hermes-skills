#!/usr/bin/env python3
"""Quick check of Hyperliquid info endpoint types to verify which ones work.
Run this when adding a new exchange or debugging API issues."""

import asyncio, httpx, json

async def main():
    test_types = [
        {"type": "meta"},
        {"type": "l2Book", "coin": "BTC"},
        {"type": "candleSnapshot", "coin": "BTC", "interval": "1H"},
    ]
    
    async with httpx.AsyncClient(timeout=30) as client:
        for body in test_types:
            try:
                resp = await client.post(
                    "https://api.hyperliquid.xyz/info",
                    json=body
                )
                
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"OK - {json.dumps(body)} -> {type(data).__name__} ({len(data) if isinstance(data, (list, dict)) else 'N/A'})")
                else:
                    print(f"FAIL HTTP {resp.status_code} - {json.dumps(body)}")
            except Exception as e:
                print(f"ERROR - {json.dumps(body)}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
