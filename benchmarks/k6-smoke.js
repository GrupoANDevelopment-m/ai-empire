// AI Empire — k6 smoke test (alternative to Locust).
//
// Run with:
//   k6 run benchmarks/k6-smoke.js
//   k6 run --out json=results.json benchmarks/k6-smoke.js
//
// Useful in CI for a quick check (30s vs 5min Locust run).

import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter, Rate, Trend } from 'k6/metrics';

const chatLatency = new Trend('chat_latency_ms');
const chatErrors = new Rate('chat_errors');
const toolCalls = new Counter('tool_calls');

export const options = {
  stages: [
    { duration: '10s', target: 10 },   // ramp up to 10 users
    { duration: '20s', target: 50 },   // ramp to 50
    { duration: '20s', target: 100 },  // ramp to 100
    { duration: '30s', target: 100 },  // hold 100
    { duration: '10s', target: 0 },    // ramp down
  ],
  thresholds: {
    // SLO: p99 < 2s, errors < 1%
    'chat_latency_ms': ['p(99)<2000'],
    'chat_errors': ['rate<0.01'],
    'http_req_duration': ['p(99)<3000'],
    'http_req_failed': ['rate<0.05'],
  },
};

const HOST = __ENV.HOST || 'http://localhost:8123';
const TOKEN = __ENV.TOKEN || 'eyJ-test-operator';

const PROMPTS = [
  'what can you do',
  'is everything healthy',
  'find 5 SaaS leads',
  'create a sunset image',
  'run the tests',
];

export default function () {
  const headers = {
    'Authorization': `Bearer ${TOKEN}`,
    'Content-Type': 'application/json',
  };

  // 1. Health check
  let r = http.get(`${HOST}/health`);
  check(r, { 'health 200': (r) => r.status === 200 });

  // 2. Chat (the main endpoint)
  const start = Date.now();
  r = http.post(
    `${HOST}/chat`,
    JSON.stringify({
      message: PROMPTS[Math.floor(Math.random() * PROMPTS.length)],
      session: `k6-${__VU}-${__ITER}`,
    }),
    { headers }
  );
  const latency = Date.now() - start;
  chatLatency.add(latency);
  const ok = check(r, {
    'chat 200 or 429': (r) => r.status === 200 || r.status === 429,
    'chat < 2s': (r) => r.timings.duration < 2000,
  });
  if (!ok) chatErrors.add(1);
  else chatErrors.add(0);
  if (r.status === 429) {
    // Rate limit is a valid response — system is working
    toolCalls.add(1);  // count as tool call
  } else if (r.status === 200) {
    toolCalls.add(1);
  }

  sleep(Math.random() * 2);
}

export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'reports/k6-summary.json': JSON.stringify(data, null, 2),
  };
}
