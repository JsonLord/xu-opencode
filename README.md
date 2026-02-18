---
title: OpenCode API
emoji: 🤖
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
license: mit
---

# OpenCode API

LLM Agent API Server - ported from TypeScript [opencode](https://github.com/anomalyco/opencode) to Python.

## Features

- **Multi-provider LLM support**: Anthropic (Claude), OpenAI (GPT-4)
- **Tool system**: Web search, web fetch, todo management
- **Session management**: Persistent conversations with history
- **SSE streaming**: Real-time streaming responses
- **REST API**: FastAPI with automatic OpenAPI docs

## API Endpoints

### Sessions

- `GET /session` - List all sessions
- `POST /session` - Create a new session
- `GET /session/{id}` - Get session details
- `DELETE /session/{id}` - Delete a session
- `POST /session/{id}/message` - Send a message (SSE streaming response)
- `POST /session/{id}/abort` - Cancel ongoing generation

### Providers

- `GET /provider` - List available LLM providers
- `GET /provider/{id}` - Get provider details
- `GET /provider/{id}/model` - List provider models

### Events

- `GET /event` - Subscribe to real-time events (SSE)

## Environment Variables

Set these as Hugging Face Space secrets:

| Variable                   | Description                         |
| -------------------------- | ----------------------------------- |
| `ANTHROPIC_API_KEY`        | Anthropic API key for Claude models |
| `OPENAI_API_KEY`           | OpenAI API key for GPT models       |
| `OPENCODE_SERVER_PASSWORD` | Optional: Basic auth password       |

## Local Development

```bash
# Install dependencies
pip install -r requirements.txt

# Run server
python app.py

# Or with uvicorn
uvicorn app:app --host 0.0.0.0 --port 7860 --reload
```

## API Documentation

Once running, visit:

- Swagger UI: `http://localhost:7860/docs`
- ReDoc: `http://localhost:7860/redoc`

## Example Usage

```python
import httpx

# Create a session
response = httpx.post("http://localhost:7860/session")
session = response.json()
session_id = session["id"]

# Send a message (with SSE streaming)
with httpx.stream(
    "POST",
    f"http://localhost:7860/session/{session_id}/message",
    json={"content": "Hello, what can you help me with?"}
) as response:
    for line in response.iter_lines():
        if line.startswith("data: "):
            print(line[6:])
```

## License

MIT
