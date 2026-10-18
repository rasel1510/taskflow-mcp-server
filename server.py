import sys
import uuid
import datetime
import json
from typing import Optional, List, Dict, Any
from starlette.responses import JSONResponse, HTMLResponse
from starlette.requests import Request

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

from mcp.server.fastmcp import FastMCP
import config
import db
import scheduler

# Initialize the official FastMCP server
mcp = FastMCP(
    name=config.MCP_SERVER_NAME,
    host=config.HOST,
    port=config.PORT,
    stateless_http=True,
)

# ─────────────────────────────────────────────────────────────────────────────
# MCP Tools (Callable by Claude Desktop, Cursor, and internal agents)
# ─────────────────────────────────────────────────────────────────────────────

@mcp.tool()
async def list_tasks(
    status: Optional[str] = None, 
    priority: Optional[str] = None,
    limit: int = 25
) -> List[Dict[str, Any]]:
    """
    List tasks from TaskFlow workspace with optional status and priority filtering.
    status options: 'backlog', 'todo', 'in_progress', 'in_review', 'done'
    priority options: 'low', 'medium', 'high', 'urgent'
    """
    conditions = []
    params = []
    
    if status:
        params.append(status.lower())
        conditions.append(f't.status::text = ${len(params)}')
    if priority:
        params.append(priority.lower())
        conditions.append(f't.priority::text = ${len(params)}')
        
    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    params.append(limit)
    limit_param = f"${len(params)}"
    
    query = f"""
    SELECT 
        t.id,
        COALESCE(t."taskNumber", 'TF-000') as "taskNumber",
        t.title,
        t.description,
        t.status::text as status,
        t.priority::text as priority,
        t."dueDate"::text as "dueDate",
        p.name as "projectName",
        u.name as "assigneeName",
        u.email as "assigneeEmail"
    FROM "Task" t
    LEFT JOIN "Project" p ON t."projectId" = p.id
    LEFT JOIN "User" u ON t."assigneeId" = u.id
    {where_clause}
    ORDER BY t."createdAt" DESC
    LIMIT {limit_param};
    """
    
    return await db.fetch_all(query, *params)


@mcp.tool()
async def create_task(
    title: str,
    description: Optional[str] = None,
    priority: str = "medium",
    status: str = "todo",
    due_date: Optional[str] = None,
    project_id: Optional[str] = None,
    assignee_email: Optional[str] = None
) -> Dict[str, Any]:
    """
    Create a new task in the TaskFlow workspace.
    due_date should be in YYYY-MM-DD format (e.g. 2026-10-15).
    priority: 'low', 'medium', 'high', 'urgent'
    """
    task_id = f"task_{uuid.uuid4().hex[:16]}"
    
    count = await db.fetch_val('SELECT COUNT(*) FROM "Task";')
    task_number = f"TF-{(count or 0) + 1:03d}"
    
    assignee_id = None
    if assignee_email:
        user_row = await db.fetch_one('SELECT id FROM "User" WHERE email = $1;', assignee_email)
        if user_row:
            assignee_id = user_row["id"]
            
    if not project_id:
        proj_row = await db.fetch_one('SELECT id FROM "Project" ORDER BY "createdAt" ASC LIMIT 1;')
        if proj_row:
            project_id = proj_row["id"]
            
    parsed_due_date = None
    if due_date:
        try:
            parsed_due_date = datetime.date.fromisoformat(due_date.strip())
        except Exception:
            parsed_due_date = None

    query = """
    INSERT INTO "Task" (
        "id", "taskNumber", "title", "description", 
        "status", "priority", "dueDate", "projectId", 
        "assigneeId", "createdAt", "updatedAt"
    )
    VALUES (
        $1, $2, $3, $4, 
        $5::"Status", $6::"Priority", $7, $8, 
        $9, NOW(), NOW()
    )
    RETURNING id, "taskNumber", title, status::text, priority::text;
    """
    
    created = await db.fetch_one(
        query,
        task_id, task_number, title.strip(), description,
        status.lower(), priority.lower(), parsed_due_date, project_id,
        assignee_id
    )
    return created or {"id": task_id, "taskNumber": task_number, "title": title}


@mcp.tool()
async def update_task_status(task_id: str, new_status: str) -> Dict[str, Any]:
    """Update the status of a task by ID or taskNumber (e.g. 'TF-001')."""
    query = """
    UPDATE "Task"
    SET status = $1::"Status", "updatedAt" = NOW()
    WHERE id = $2 OR "taskNumber" = $2
    RETURNING id, "taskNumber", title, status::text;
    """
    result = await db.fetch_one(query, new_status.lower(), task_id.strip())
    if not result:
        return {"error": f"Task '{task_id}' not found"}
    return result


@mcp.tool()
async def get_workspace_summary() -> Dict[str, Any]:
    """Get executive workspace metrics: total tasks, completed, in-progress, overdue count."""
    tasks_summary = await db.fetch_one("""
        SELECT 
            COUNT(*) as total_tasks,
            COUNT(*) FILTER (WHERE status::text = 'done') as completed_tasks,
            COUNT(*) FILTER (WHERE status::text = 'in_progress') as in_progress_tasks,
            COUNT(*) FILTER (WHERE status::text != 'done' AND "dueDate" < CURRENT_DATE) as overdue_tasks
        FROM "Task";
    """)
    projects_count = await db.fetch_val('SELECT COUNT(*) FROM "Project";')
    users_count = await db.fetch_val('SELECT COUNT(*) FROM "User";')
    return {
        "metrics": dict(tasks_summary) if tasks_summary else {},
        "total_projects": projects_count or 0,
        "team_members": users_count or 0
    }


@mcp.tool()
async def trigger_daily_reminder_notifications() -> Dict[str, Any]:
    """Manually triggers the daily reminder notification check."""
    return await scheduler.dispatch_daily_task_reminders()


# ─────────────────────────────────────────────────────────────────────────────
# REST Endpoints for ChatGPT Custom GPT Actions & Browser Dashboard
# ─────────────────────────────────────────────────────────────────────────────

@mcp.custom_route("/", methods=["GET"])
async def root_dashboard(request: Request):
    """Clean browser landing page confirming server status."""
    summary = await get_workspace_summary()
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>TaskFlow MCP Server</title>
        <meta charset="utf-8">
        <style>
            body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #0F172A; color: #F8FAFC; margin: 0; padding: 40px 20px; display: flex; justify-content: center; }}
            .card {{ background: #1E293B; border: 1px solid #334155; border-radius: 16px; padding: 32px; max-width: 600px; width: 100%; box-shadow: 0 10px 25px rgba(0,0,0,0.3); }}
            h1 {{ margin-top: 0; font-size: 24px; color: #38BDF8; display: flex; align-items: center; gap: 10px; }}
            .badge {{ display: inline-block; background: #059669; color: white; padding: 4px 10px; border-radius: 9999px; font-size: 12px; font-weight: 600; }}
            .metric {{ background: #0F172A; border-radius: 10px; padding: 16px; margin-top: 16px; }}
            .endpoints {{ margin-top: 24px; font-size: 13px; color: #94A3B8; }}
            code {{ background: #334155; padding: 3px 6px; border-radius: 4px; color: #38BDF8; font-family: monospace; }}
            a {{ color: #38BDF8; text-decoration: none; }}
            a:hover {{ text-decoration: underline; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>TaskFlow MCP Server <span class="badge">ONLINE</span></h1>
            <p style="color: #94A3B8; font-size: 14px;">Anthropic Model Context Protocol & ChatGPT Actions Bridge</p>
            
            <div class="metric">
                <div style="font-size: 12px; color: #94A3B8; text-transform: uppercase; font-weight: 600;">Neon Database Connected</div>
                <div style="font-size: 20px; font-weight: bold; margin-top: 6px;">
                    {summary.get('metrics', {}).get('total_tasks', 0)} Tasks | {summary.get('total_projects', 0)} Projects | {summary.get('team_members', 0)} Team Members
                </div>
            </div>

            <div class="endpoints">
                <p><strong>Endpoints:</strong></p>
                <ul>
                    <li>Streamable HTTP (MCP): <code>POST /mcp</code></li>
                    <li>ChatGPT Action Schema: <a href="/openapi.json"><code>/openapi.json</code></a></li>
                    <li>Tasks REST API: <a href="/api/tasks"><code>/api/tasks</code></a></li>
                    <li>Workspace Summary: <a href="/api/summary"><code>/api/summary</code></a></li>
                    <li>Daily Reminders: <code>POST /api/reminders</code></li>
                </ul>
            </div>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(html)


@mcp.custom_route("/openapi.json", methods=["GET"])
async def openapi_schema(request: Request):
    """Dynamic OpenAPI 3.0 schema for ChatGPT Custom GPT Actions."""
    base_url = str(request.base_url).rstrip("/")
    schema = {
        "openapi": "3.0.0",
        "info": {
            "title": "TaskFlow Workspace API",
            "description": "API for querying, creating, and updating TaskFlow workspace tasks and metrics.",
            "version": "1.0.0"
        },
        "servers": [
            {"url": base_url}
        ],
        "paths": {
            "/api/tasks": {
                "get": {
                    "operationId": "listTasks",
                    "summary": "List tasks from TaskFlow workspace",
                    "description": "Retrieve tasks filtered by status (todo, in_progress, done) or priority (low, medium, high, urgent).",
                    "parameters": [
                        {
                            "name": "status",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["backlog", "todo", "in_progress", "in_review", "done"]},
                            "description": "Filter tasks by status"
                        },
                        {
                            "name": "priority",
                            "in": "query",
                            "required": False,
                            "schema": {"type": "string", "enum": ["low", "medium", "high", "urgent"]},
                            "description": "Filter tasks by priority"
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "List of tasks returned successfully",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "array", "items": {"type": "object"}}
                                }
                            }
                        }
                    }
                },
                "post": {
                    "operationId": "createTask",
                    "summary": "Create a new task",
                    "description": "Add a task to the user workspace with optional title, description, priority, and due date.",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "title": {"type": "string", "description": "Title of the task"},
                                        "description": {"type": "string", "description": "Optional details"},
                                        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"], "default": "medium"},
                                        "due_date": {"type": "string", "description": "YYYY-MM-DD"}
                                    },
                                    "required": ["title"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Task created successfully",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            },
            "/api/summary": {
                "get": {
                    "operationId": "getWorkspaceSummary",
                    "summary": "Get workspace summary metrics",
                    "description": "Returns counts of total tasks, completed, in-progress, and overdue items.",
                    "responses": {
                        "200": {
                            "description": "Summary returned successfully",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            },
            "/api/tasks/status": {
                "post": {
                    "operationId": "updateTaskStatus",
                    "summary": "Update task progress status",
                    "description": "Transitions task status (e.g. backlog, todo, in_progress, in_review, done) by ID or taskNumber (e.g. TF-001).",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "task_id": {"type": "string", "description": "Task UUID or taskNumber (e.g. TF-001)"},
                                        "status": {"type": "string", "enum": ["backlog", "todo", "in_progress", "in_review", "done"], "description": "New target status"}
                                    },
                                    "required": ["task_id", "status"]
                                }
                            }
                        }
                    },
                    "responses": {
                        "200": {
                            "description": "Task status updated successfully",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            },
            "/api/reminders": {
                "post": {
                    "operationId": "triggerDailyReminders",
                    "summary": "Trigger daily standup reminder notifications",
                    "description": "Checks incomplete tasks and creates notifications for assignees in TaskFlow.",
                    "responses": {
                        "200": {
                            "description": "Reminders dispatched",
                            "content": {
                                "application/json": {
                                    "schema": {"type": "object"}
                                }
                            }
                        }
                    }
                }
            }
        }
    }
    return JSONResponse(schema)


@mcp.custom_route("/api/tasks", methods=["GET"])
async def rest_list_tasks(request: Request):
    status = request.query_params.get("status")
    priority = request.query_params.get("priority")
    tasks = await list_tasks(status=status, priority=priority)
    return JSONResponse(tasks)


@mcp.custom_route("/api/tasks", methods=["POST"])
async def rest_create_task(request: Request):
    body = await request.json()
    res = await create_task(
        title=body.get("title", ""),
        description=body.get("description"),
        priority=body.get("priority", "medium"),
        due_date=body.get("due_date")
    )
    return JSONResponse(res)


@mcp.custom_route("/api/tasks/status", methods=["POST", "PATCH"])
async def rest_update_task_status(request: Request):
    body = await request.json()
    res = await update_task_status(
        task_id=body.get("task_id", ""),
        new_status=body.get("status", "")
    )
    return JSONResponse(res)


@mcp.custom_route("/api/summary", methods=["GET"])
async def rest_get_summary(request: Request):
    summary = await get_workspace_summary()
    return JSONResponse(summary)


@mcp.custom_route("/api/reminders", methods=["POST"])
async def rest_trigger_reminders(request: Request):
    result = await trigger_daily_reminder_notifications()
    return JSONResponse(result)


# ─────────────────────────────────────────────────────────────────────────────
# ASGI Application (Exported for Vercel Serverless & Production ASGI Servers)
# ─────────────────────────────────────────────────────────────────────────────
app = mcp.streamable_http_app()


# ─────────────────────────────────────────────────────────────────────────────
# Standalone Server Entrypoint
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    transport = "streamable-http"
    if "--stdio" in sys.argv:
        transport = "stdio"
    elif "--sse" in sys.argv:
        transport = "sse"

    print(f"[STARTUP] Starting {config.MCP_SERVER_NAME} using transport: {transport}...")
    
    # Standalone mode can run APScheduler
    try:
        scheduler.start_scheduler()
    except Exception as e:
        print(f"[WARN] Scheduler startup note: {e}")

    if transport == "streamable-http":
        print(f"[READY] MCP Streamable HTTP endpoint: http://{config.HOST}:{config.PORT}/mcp")
        print(f"[READY] ChatGPT OpenAPI Spec: http://{config.HOST}:{config.PORT}/openapi.json")
        mcp.run(transport="streamable-http")
    elif transport == "sse":
        print(f"[READY] MCP SSE endpoint available at: http://{config.HOST}:{config.PORT}/sse")
        print(f"[READY] ChatGPT OpenAPI Spec: http://{config.HOST}:{config.PORT}/openapi.json")
        mcp.run(transport="sse")
    else:
        print("[READY] MCP STDIO stream active for Claude Desktop / Cursor integration.")
        mcp.run(transport="stdio")
