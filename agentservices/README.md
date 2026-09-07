# Agent Services

Independent microservices that extend AgentMesh capabilities.

## Structure

```
agentservices/
├── mcp/              # Model Context Protocol (MCP) tool servers
├── ingestion/        # Future: Specialized ingestion services
└── a2aservers/       # Future: Agent-to-Agent communication servers
```

## Philosophy

Each subdirectory contains **independent microservices** that:
- Have their own Dockerfile and requirements.txt
- Can be developed, versioned, and deployed independently
- Follow single-responsibility principle
- Communicate via well-defined APIs (REST, SSE, gRPC)
- Can be scaled independently based on load

## Current Services

### MCP (Model Context Protocol) - 3 servers
Tool servers exposing capabilities to AI agents via the MCP protocol:
- **mcp-documents** (8081) - Document management and search
- **mcp-search** (8082) - Web search and corpus overview
- **mcp-memory** (8083) - Long-term memory operations

See [mcp/README.md](mcp/README.md) for details.

## Future Services

### Ingestion
Specialized document processing services:
- PDF processing service
- OCR service
- Table extraction service
- Media transcription service

### A2A Servers (Agent-to-Agent)
Inter-agent communication protocols:
- Task delegation server
- Result aggregation server
- Agent coordination server
- Multi-agent orchestration hub

## Adding New Services

1. Create a new subdirectory in the appropriate category
2. Structure as an independent project with:
   - `Dockerfile`
   - `requirements.txt` (minimal dependencies)
   - `README.md` (usage, API docs)
   - `.env.example`
   - `.gitignore`
   - `app/` directory with server code
3. Add service to `docker-compose.yml`
4. Document in this README

## Development Principles

- **Loose coupling**: Services communicate via APIs, not shared code
- **Independent deployment**: Each service can be deployed separately
- **Technology agnostic**: Services can use different languages/frameworks
- **Single responsibility**: Each service does one thing well
- **Fault isolation**: Service failure doesn't cascade
- **Observable**: Each service exposes health checks and metrics
