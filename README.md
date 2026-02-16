# GitHub Copilot as API

An Azure Functions app that exposes the GitHub Copilot CLI as OpenAI-compatible REST API endpoints. Send chat messages via HTTP and receive responses from GitHub Copilot, including any files it creates in a temporary workspace.

## Features

- **OpenAI-compatible API** — Drop-in replacement format for `chat.completions`
- **Multi-model support** — Claude Sonnet/Opus/Haiku, GPT-5, Gemini, and more
- **File output** — Copilot can create files in a temporary workspace; they are returned as base64 in the response
- **Streaming (SSE)** — Server-Sent Events endpoint for simulated streaming
- **API key auth** — Optional Bearer / ApiKey authentication
- **Docker ready** — Containerized deployment to Azure Container Apps or Azure Functions

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.11+ |
| GitHub Copilot CLI | `winget install GitHub.Copilot` / `brew install copilot-cli` / `npm install -g @github/copilot` |
| GitHub PAT | Fine-grained token with **Copilot Requests** permission ([create one here](https://github.com/settings/personal-access-tokens/new)) |
| Azure Functions Core Tools | For local development (`npm install -g azure-functions-core-tools@4`) |

## Quick Start

### 1. Clone & install dependencies

```bash
git clone https://github.com/<your-org>/fab-copilot-std-api-demo.git
cd fab-copilot-std-api-demo
pip install -r requirements.txt
```

### 2. Configure environment

Copy `local.settings.json` and set your values:

| Variable | Description | Required |
|---|---|---|
| `GH_TOKEN` | GitHub PAT with Copilot Requests permission | Yes |
| `COPILOT_MODEL` | Default model (e.g. `claude-sonnet-4`) | No |
| `API_KEY` | API key for endpoint auth (empty = allow all) | No |
| `COPILOT_PATH` | Path to copilot CLI binary (default: `copilot`) | No |

### 3. Run locally

```bash
func start
```

The API will be available at `http://localhost:7071/api/`.

## API Endpoints

### `POST /api/chat`

Send a chat completion request.

**Request:**

```json
{
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "Write a Python hello world script" }
  ],
  "model": "claude-sonnet-4"
}
```

**Response:**

```json
{
  "id": "copilot-abc12345",
  "object": "chat.completion",
  "model": "github-copilot-claude-sonnet-4",
  "choices": [
    {
      "index": 0,
      "message": {
        "role": "assistant",
        "content": "Here's a simple hello world script..."
      },
      "finish_reason": "stop"
    }
  ],
  "files": [
    {
      "path": "hello.py",
      "name": "hello.py",
      "extension": ".py",
      "size": 27,
      "is_binary": false,
      "mime_type": "text/x-python",
      "content_base64": "cHJpbnQoIkhlbGxvLCBXb3JsZCEiKQ==",
      "content_text": "print(\"Hello, World!\")"
    }
  ],
  "files_count": 1
}
```

### `POST /api/stream`

Streaming chat via Server-Sent Events. Same request body as `/api/chat`.

### `GET /api/health`

Health check — verifies Copilot CLI availability and authentication status.

### `GET /api/models`

Lists available models (requires authentication).

## Authentication

Include your API key in the `Authorization` header:

```
Authorization: Bearer <your-api-key>
```

or

```
Authorization: ApiKey <your-api-key>
```

If no `API_KEY` is configured, all requests are allowed (development mode).

## Docker

### Build & run

```bash
docker build -t copilot-api .
docker run -p 80:80 -e GH_TOKEN=<your-github-pat> copilot-api
```

### Deploy to Azure Container Apps

```bash
az containerapp up \
  --name copilot-api \
  --resource-group <rg> \
  --image <acr>.azurecr.io/copilot-api:latest \
  --env-vars GH_TOKEN=<your-github-pat>
```

## Project Structure

```
├── function_app.py          # Azure Functions HTTP endpoints
├── services/
│   ├── auth_service.py      # API key validation
│   └── copilot_service.py   # GitHub Copilot CLI wrapper
├── host.json                # Azure Functions host configuration
├── local.settings.json      # Local environment settings
├── requirements.txt         # Python dependencies
└── Dockerfile               # Container image definition
```

## License

MIT
