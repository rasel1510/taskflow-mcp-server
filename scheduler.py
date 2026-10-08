import sys
import asyncio
import uuid
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")

import db
import config

scheduler = AsyncIOScheduler()

async def dispatch_daily_task_reminders() -> dict:
    """
    Queries Neon DB for all users with incomplete tasks (status != 'done')
    and creates a daily reminder Notification in the database.
    """
    print("[Daily Reminder] Starting daily task reminder check...")
    
    query = """
    SELECT 
        u.id as user_id, 
        u.name as user_name, 
        u.email as user_email,
        COUNT(t.id) as pending_count,
        ARRAY_AGG(COALESCE(t."taskNumber", 'Task') || ': ' || t.title) as task_titles
    FROM "User" u
    JOIN "Task" t ON t."assigneeId" = u.id
    WHERE t.status != 'done'
    GROUP BY u.id, u.name, u.email;
    """
    
    users_with_tasks = await db.fetch_all(query)
    reminders_sent = 0
    
    for row in users_with_tasks:
        user_id = row["user_id"]
        user_name = row["user_name"]
        count = row["pending_count"]
        task_list = row["task_titles"][:5] # top 5
        
        sample_tasks = ", ".join(task_list)
        if count > 5:
            sample_tasks += f" (and {count - 5} more)"
            
        title = f"Daily Reminder: {count} remaining task{'s' if count > 1 else ''}"
        body = f"Good morning {user_name}! You have {count} pending task(s) today: {sample_tasks}. Check your board to keep your velocity on track."
        notif_id = f"notif_{uuid.uuid4().hex[:16]}"
        
        insert_query = """
        INSERT INTO "Notification" ("id", "userId", "type", "title", "body", "read", "createdAt")
        VALUES ($1, $2, 'daily_reminder', $3, $4, false, NOW());
        """
        await db.execute(insert_query, notif_id, user_id, title, body)
        reminders_sent += 1
        print(f"   [Notification] Dispatched to {user_name} ({row['user_email']}) -> {count} tasks")
        
    print(f"[Daily Reminder] Completed. Sent notifications to {reminders_sent} user(s).")
    return {
        "status": "success",
        "users_notified": reminders_sent,
        "details": [
            {"user": r["user_name"], "pending_tasks": r["pending_count"]} 
            for r in users_with_tasks
        ]
    }

def start_scheduler():
    """Starts the APScheduler background worker."""
    trigger = CronTrigger(
        hour=config.DAILY_REMINDER_HOUR, 
        minute=config.DAILY_REMINDER_MINUTE
    )
    scheduler.add_job(
        dispatch_daily_task_reminders,
        trigger=trigger,
        id="daily_task_reminder",
        replace_existing=True
    )
    scheduler.start()
    print(f"[Scheduler] Background Scheduler active. Reminders configured for {config.DAILY_REMINDER_HOUR:02d}:{config.DAILY_REMINDER_MINUTE:02d} daily.")
