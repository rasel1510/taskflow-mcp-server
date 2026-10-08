import sys
import uuid
import datetime
from typing import Optional, List, Dict, Any

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
)

# ─────────────────────────────────────────────────────────────────────────────
# MCP Tools (Callable by ChatGPT, Claude, Cursor, etc.)
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
    
    # Compute next task number (TF-001 format)
    count = await db.fetch_val('SELECT COUNT(*) FROM "Task";')
    task_number = f"TF-{(count or 0) + 1:03d}"
    
    # Resolve assignee if email provided
    assignee_id = None
    if assignee_email:
        user_row = await db.fetch_one('SELECT id FROM "User" WHERE email = $1;', assignee_email)
        if user_row:
            assignee_id = user_row["id"]
            
    # Resolve project if not provided
    if not project_id:
        proj_row = await db.fetch_one('SELECT id FROM "Project" ORDER BY "createdAt" ASC LIMIT 1;')
        if proj_row:
            project_id = proj_row["id"]
            
    # Parse due date
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
    """
    Update the status of a task by ID or taskNumber (e.g. 'TF-001').
    new_status: 'backlog', 'todo', 'in_progress', 'in_review', 'done'
    """
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
    """
    Get executive workspace metrics: total tasks, completed, in-progress, overdue count, and active projects.
    """
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
    """
    Manually triggers the daily reminder notification check.
    Queries incomplete tasks for all users and adds notification records directly into TaskFlow's Notification table.
    """
    return await scheduler.dispatch_daily_task_reminders()


@mcp.tool()
async def list_projects() -> List[Dict[str, Any]]:
    """
    List all active projects in the workspace with progress, health, and task counts.
    """
    query = """
    SELECT 
        p.id,
        p.name,
        p.description,
        p.health::text as health,
        p.progress,
        COUNT(t.id) as total_tasks,
        COUNT(t.id) FILTER (WHERE t.status::text = 'done') as done_tasks
    FROM "Project" p
    LEFT JOIN "Task" t ON t."projectId" = p.id
    GROUP BY p.id
    ORDER BY p."createdAt" DESC;
    """
    return await db.fetch_all(query)


# ─────────────────────────────────────────────────────────────────────────────
# MCP Prompts & Resources
# ─────────────────────────────────────────────────────────────────────────────

@mcp.resource("taskflow://workspace/summary")
async def workspace_summary_resource() -> str:
    """Live JSON resource of current workspace statistics."""
    summary = await get_workspace_summary()
    import json
    return json.dumps(summary, indent=2)


@mcp.prompt()
def daily_standup() -> str:
    """Generates a prompt for summarizing the user's daily standup and priority blockers."""
    return (
        "Please inspect my current workspace tasks using list_tasks, identify overdue "
        "and in-progress tasks, and generate a crisp 3-bullet daily standup summary."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Server Lifecycle & Entrypoint
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    transport = "sse"
    if "--stdio" in sys.argv:
        transport = "stdio"

    print(f"[STARTUP] Starting {config.MCP_SERVER_NAME} using transport: {transport}...")
    
    # Start background daily reminder cron scheduler
    try:
        scheduler.start_scheduler()
    except Exception as e:
        print(f"[WARN] Scheduler startup note: {e}")

    if transport == "sse":
        print(f"[READY] MCP SSE endpoint available at: http://{config.HOST}:{config.PORT}/sse")
        mcp.run(transport="sse")
    else:
        print("[READY] MCP STDIO stream active for Claude Desktop / Cursor integration.")
        mcp.run(transport="stdio")
