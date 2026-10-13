# Browser-Automation API

13 tools wrapping Playwright. All tools require a `session_id` from
`browser_open_session` first.

## `browser_open_session`
Open a new persistent browser context.

**Input**:
```json
{
  "tenant_id": "string (required)",
  "profile": "string (default: 'default')",
  "headless": "bool (default: true)"
}
```

**Output**:
```json
{
  "session_id": "uuid",
  "profile_path": "string"
}
```

## `browser_navigate`
Navigate to a URL.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "url": "string (required, must be http/https)",
  "wait_until": "string (default: 'load')"
}
```

## `browser_click`
Click an element.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "selector": "string (required, CSS selector)",
  "timeout": "int (default: 30000)"
}
```

## `browser_fill`
Fill a form field.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "selector": "string (required)",
  "value": "string (required)"
}
```

## `browser_extract`
Extract structured data from a page.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "selector": "string (required, CSS)",
  "attr": "string (default: 'text')",
  "multiple": "bool (default: false)"
}
```

## `browser_screenshot`
Take a screenshot.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "full_page": "bool (default: false)",
  "path": "string (optional, save to file)"
}
```

## `browser_evaluate`
Run JavaScript in the page.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "script": "string (required, JavaScript)"
}
```

## `browser_wait`
Wait for an element/condition.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "selector": "string (optional)",
  "timeout": "int (default: 30000)",
  "state": "string (visible|hidden|attached|detached)"
}
```

## `browser_cookies`
Get/Set cookies.

**Input** (get):
```json
{
  "session_id": "uuid (required)",
  "action": "get"
}
```

**Input** (set):
```json
{
  "session_id": "uuid (required)",
  "action": "set",
  "cookies": [{"name": "string", "value": "string", "domain": "string"}]
}
```

## `browser_save_state`
Save current session state.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "path": "string (required, save to file)"
}
```

## `browser_load_state`
Load a saved session state.

**Input**:
```json
{
  "session_id": "uuid (required)",
  "path": "string (required, file to load)"
}
```

## `browser_list_sessions`
List all active sessions.

**Output**:
```json
{
  "sessions": [
    {
      "id": "uuid",
      "tenant_id": "string",
      "profile": "string",
      "created_at": "iso8601",
      "last_used_at": "iso8601"
    }
  ]
}
```

## `browser_close_session`
Close a session and clear cookies.

**Input**:
```json
{
  "session_id": "uuid (required)"
}
```
