# TaskFlow MCP Server

Industry-standard, standalone Model Context Protocol (MCP) server for TaskFlow built with Python 3.11, Anthropic FastMCP, Docker, and Neon PostgreSQL.

---

## 🏛️ Architecture Overview

```
External AI (ChatGPT / Claude / Cursor)
           │
           │  HTTPS / SSE (Bearer Token)
           ▼
┌──────────────────────────────────────────────┐
│  VPS / Docker Container (taskflow-mcp-server)│
│                                              │
│  ├── FastMCP Server (Port 8000 /sse)         │
│  └── Daily Reminder Scheduler (APScheduler)  │
└──────────────────────┬───────────────────────┘
                       │
                       │  asyncpg (SSL)
                       ▼
            Neon PostgreSQL Database
        (Shared with TaskFlow Next.js App)
```

---

## 🚀 Features

1. **Standard MCP Tools**:
   * `list_tasks`: Filter tasks by status, priority, or project.
   * `create_task`: Create tasks with automatic `TF-XXX` task numbering.
   * `update_task_status`: Transition tasks between Kanban columns.
   * `get_workspace_summary`: High-level metrics (overdue, in-progress, completed).
   * `list_projects`: Inspect all active projects and health indicators.
   * `trigger_daily_reminder_notifications`: Manually dispatch daily reminder alerts.
2. **Daily Task Reminder Background Worker**:
   * Runs via `APScheduler` every morning (configurable via `DAILY_REMINDER_HOUR`).
   * Queries pending and overdue tasks across active users.
   * Inserts notification records directly into TaskFlow's `Notification` table in Neon DB.
3. **Multi-Transport Support**:
   * **SSE (`--sse`)**: For remote network access from ChatGPT or web clients.
   * **STDIO (`--stdio`)**: For Claude Desktop, Cursor, or local CLI integration.

---

## 🛠️ Local Setup & Testing

### Option A: Running with Docker (Recommended)

1. Ensure Docker is running.
2. Build and start the container:
   ```bash
   docker compose up --build
   ```
3. The MCP server will be active at `http://localhost:8000/sse`.

### Option B: Running with Python Virtualenv

1. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   # Windows:
   .venv\Scripts\activate
   # Linux/macOS:
   source .venv/bin/activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Run the automated test suite:
   ```bash
   python test_client.py
   ```
4. Start the server:
   ```bash
   python server.py
   ```

---

## 🤖 Connecting External AI Clients

### 1. Claude Desktop (`claude_desktop_config.json`)
```json
{
  "mcpServers": {
    "taskflow": {
      "command": "python",
      "args": ["C:\\Users\\DELL\\Desktop\\taskflow-mcp-server\\server.py", "--stdio"],
      "env": {
        "DATABASE_URL": "postgresql://..."
      }
    }
  }
}
```

### 2. ChatGPT (Custom GPT Action)
1. Expose `localhost:8000` via `ngrok http 8000` or deploy to your VPS.
2. Add your server endpoint URL `https://your-domain.com/sse` in Custom GPT Actions.

---

## 🌐 Deploying to a Production VPS

1. SSH into your VPS (Ubuntu 22.04+):
   ```bash
   ssh root@your-vps-ip
   ```
2. Clone this repository:
   ```bash
   git clone https://github.com/your-username/taskflow-mcp-server.git
   cd taskflow-mcp-server
   ```
3. Create `.env` with your Neon `DATABASE_URL`.
4. Run with Docker Compose in detached mode:
   ```bash
   docker compose up -d
   ```
5. Set up an Nginx reverse proxy with SSL (`certbot`) to expose `https://mcp.yourdomain.com`.
