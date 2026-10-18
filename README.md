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

### 2. ChatGPT (Custom GPT Actions)
OpenAI Custom GPTs connect via standard OpenAPI REST schemas:
1. Copy your OpenAPI schema URL: `https://your-domain.vercel.app/openapi.json`
2. In ChatGPT GPT Builder -> **Configure** -> **Actions** -> **Create new action**.
3. Click **Import from URL** and paste `https://your-domain.vercel.app/openapi.json`.
4. ChatGPT will automatically discover and generate actions for:
   * `listTasks`: `GET /api/tasks`
   * `createTask`: `POST /api/tasks`
   * `updateTaskStatus`: `POST /api/tasks/status`
   * `getWorkspaceSummary`: `GET /api/summary`
   * `triggerDailyReminders`: `POST /api/reminders`

---

## ⚡ Deploying to Vercel (Serverless)

This server is pre-configured with **Streamable HTTP** (`stateless_http=True`) and standard ASGI routes for zero-configuration Vercel deployment:

1. **Push your code to GitHub**:
   ```bash
   git add .
   git commit -m "Convert MCP server to Streamable HTTP and Vercel ASGI"
   git push origin main
   ```
2. **Import into Vercel**:
   * Go to [vercel.com/new](https://vercel.com/new).
   * Select your `taskflow-mcp-server` repository.
   * Add the following **Environment Variables**:
     * `DATABASE_URL`: Your Neon PostgreSQL connection string.
     * `MCP_SERVER_NAME`: `taskflow-mcp-server`
3. **Deploy**:
   * Vercel will install dependencies from `requirements.txt` and automatically serve `api/index.py` via `vercel.json`.
   * MCP Streamable HTTP endpoint: `https://your-project.vercel.app/mcp`
   * OpenAI OpenAPI Specification: `https://your-project.vercel.app/openapi.json`
   * Daily standup reminder cron: configured automatically via `vercel.json` (`0 9 * * *`).

---

## 🌐 Alternative: Deploying to a Production VPS (Docker)

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
4. Run with Docker Compose:
   ```bash
   docker compose up -d
   ```
