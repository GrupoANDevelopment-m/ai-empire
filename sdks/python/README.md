# AI Empire Python SDK

Official Python client for the AI Empire API.

## Installation
```bash
pip install ai-empire
```

## Quick start
```python
import asyncio
from empire_client import EmpireClient

async def main():
    async with EmpireClient(base_url="https://empire.example.com") as c:
        await c.login("user@example.com", "password")
        response = await c.chat("Hello!")
        print(response["text"])

asyncio.run(main())
```

## Streaming
```python
async for chunk in client.chat_stream("Tell me a story"):
    print(chunk, end="")
```

## Tool calling
```python
result = await client.call_tool("browser_navigate", {"url": "https://example.com"})
```

## License
MIT — see LICENSE
