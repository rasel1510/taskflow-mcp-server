import sys
import asyncio
import os
import json
import httpx
from dotenv import load_dotenv

# Ensure UTF-8 output on Windows consoles
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import db
import scheduler
from server import list_tasks, create_task, get_workspace_summary

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = os.getenv("OPENROUTER_MODEL", "openai/gpt-4o-mini")

async def test_tools_directly():
    print("=" * 60)
    print("[TEST] 1. Testing MCP Tools Direct Execution against Neon DB")
    print("=" * 60)
    
    # 1. Summary
    summary = await get_workspace_summary()
    print("\n[METRICS] Workspace Summary:")
    print(json.dumps(summary, indent=2))
    
    # 2. List Tasks
    tasks = await list_tasks(limit=5)
    print(f"\n[TASKS] Retrieved {len(tasks)} sample task(s):")
    for t in tasks:
        print(f"   [{t.get('taskNumber')}] {t.get('title')} ({t.get('status')}) - Priority: {t.get('priority')}")
        
    # 3. Test Daily Reminder Notification Dispatch
    print("\n[SCHEDULER] Testing Daily Reminder Worker (Notification Table Insertion):")
    reminder_result = await scheduler.dispatch_daily_task_reminders()
    print("Reminder result:", json.dumps(reminder_result, indent=2))

async def test_with_openrouter(prompt: str):
    print("\n" + "=" * 60)
    print(f"[AI AGENT] 2. Testing with OpenRouter ({OPENROUTER_MODEL})")
    print(f"Prompt: \"{prompt}\"")
    print("=" * 60)
    
    if not OPENROUTER_API_KEY:
        print("[WARN] OPENROUTER_API_KEY is not set in .env. Skipping AI invocation test.")
        return

    # Tools schema matching our MCP tools
    tools_schema = [
        {
            "type": "function",
            "function": {
                "name": "list_tasks",
                "description": "List tasks from TaskFlow workspace with status and priority filtering.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["backlog", "todo", "in_progress", "in_review", "done"]},
                        "priority": {"type": "string", "enum": ["low", "medium", "high", "urgent"]}
                    }
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "get_workspace_summary",
                "description": "Get high level metrics of the workspace (counts, overdue tasks, etc).",
                "parameters": {"type": "object", "properties": {}}
            }
        }
    ]

    async with httpx.AsyncClient(timeout=30) as client:
        payload = {
            "model": OPENROUTER_MODEL,
            "messages": [
                {"role": "system", "content": "You are TaskFlow AI assistant. Use the provided tools to answer user questions about workspace tasks."},
                {"role": "user", "content": prompt}
            ],
            "tools": tools_schema,
            "tool_choice": "auto"
        }
        headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json"
        }
        res = await client.post("https://openrouter.ai/api/v1/chat/completions", json=payload, headers=headers)
        data = res.json()
        
        message = data.get("choices", [{}])[0].get("message", {})
        tool_calls = message.get("tool_calls", [])
        
        if tool_calls:
            print(f"\n[DECISION] Model decided to call {len(tool_calls)} tool(s):")
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                args = json.loads(tc["function"].get("arguments", "{}"))
                print(f"   Executing: {func_name}({args})")
                
                # Execute tool
                if func_name == "list_tasks":
                    tool_output = await list_tasks(**args)
                elif func_name == "get_workspace_summary":
                    tool_output = await get_workspace_summary()
                else:
                    tool_output = {"error": "Unknown tool"}
                
                print(f"   Tool Response (truncated): {str(tool_output)[:200]}...")
        else:
            print(f"\n[REPLY] Model Reply: {message.get('content')}")

async def main():
    try:
        await test_tools_directly()
        await test_with_openrouter("What is the current status of my workspace and what tasks are in progress?")
    finally:
        await db.close_pool()

if __name__ == "__main__":
    asyncio.run(main())
