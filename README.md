# hook-sink

**Local webhook catcher: receive, inspect, edit, and replay webhooks without ngrok.**

Stop guessing what webhooks look like. Catch them locally, inspect every header and byte, then replay them wherever you want.

```
pip install hook-sink
hook-sink serve
```

> Send webhooks to `http://localhost:8765/hook/anything` and see them instantly in the dashboard.

## Why hook-sink?

- **Zero config** - One command to start catching webhooks
- **Full inspection** - Headers, body, query params, source IP, content type
- **Replay engine** - Resend any webhook to any URL with optional payload editing
- **Provider detection** - Auto-detects GitHub, Stripe, Shopify, Slack webhooks
- **Signature validation** - Verify HMAC signatures from major providers
- **Web dashboard** - Real-time feed with search, filter, and one-click replay
- **SQLite storage** - Persistent, searchable, zero-dependency storage
- **CLI-first** - Full functionality from the terminal

## Quick Start

```bash
# Start the server
hook-sink serve --port 8765

# In another terminal, send a test webhook
curl -X POST http://localhost:8765/hook/github/push \
  -H "Content-Type: application/json" \
  -d '{"event":"push","repo":"my-app","branch":"main"}'

# List captured webhooks
hook-sink list

# Inspect a specific webhook
hook-sink inspect abc123def456

# Replay to your local server
hook-sink replay abc123def456 --target http://localhost:3000

# Replay with payload modifications
hook-sink replay abc123def456 --target http://localhost:3000 \
  --patch "event=pull_request" --patch "branch=develop"

# Clear all webhooks
hook-sink clear
```

## Web Dashboard

Open `http://localhost:8765` for the live dashboard:

- Real-time webhook feed with auto-refresh
- Click any webhook to see full details (pretty-printed JSON, headers table)
- One-click replay to any target URL
- Search by path or body content
- Filter by HTTP method

## CLI Commands

| Command | Description |
|---------|-------------|
| `hook-sink serve` | Start webhook catcher server + dashboard |
| `hook-sink list` | List captured webhooks |
| `hook-sink inspect <id>` | View full webhook details |
| `hook-sink replay <id> --target <url>` | Replay webhook to target |
| `hook-sink clear` | Delete all captured webhooks |

## Signature Validation

hook-sink auto-detects and can validate webhook signatures from:

| Provider | Header | Algorithm |
|----------|--------|-----------|
| GitHub | `X-Hub-Signature-256` | HMAC-SHA256 |
| Stripe | `Stripe-Signature` | HMAC-SHA256 (timestamped) |
| Shopify | `X-Shopify-Hmac-Sha256` | HMAC-SHA256 (base64) |
| Slack | `X-Slack-Signature` | HMAC-SHA256 (versioned) |

## Webhook Endpoints

| Endpoint | Description |
|----------|-------------|
| `POST /hook/{anything}` | Catch-all webhook receiver |
| `POST /webhook` | Root webhook receiver |
| `GET /api/webhooks` | List webhooks (JSON API) |
| `GET /api/webhooks/{id}` | Get webhook details |
| `POST /api/replay/{id}` | Replay a webhook |

## License

MIT
