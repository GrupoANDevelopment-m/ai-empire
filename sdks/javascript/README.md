# AI Empire JavaScript SDK

Official TypeScript client for the AI Empire API.

## Installation
```bash
npm install @grupoan/ai-empire
```

## Usage
```typescript
import { EmpireClient } from '@grupoan/ai-empire';

const client = new EmpireClient({ baseUrl: 'https://empire.example.com' });
await client.login('user@example.com', 'password');

const response = await client.chat('Hello!');
console.log(response.response);
```

## Streaming
```typescript
for await (const chunk of client.chatStream('Tell me a story')) {
  process.stdout.write(chunk);
}
```
