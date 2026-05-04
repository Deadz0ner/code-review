"""Routes incoming task requests to the right job module.

Sits between main.py (which collects raw CLI arguments) and the storage / job
layers. Has its own subtle problems: a TOCTOU window between checking task
state and marking it running, and a bare except that hides every error path.
"""
from jobs import cleanup_job, email_job, report_job
from storage import get_task_by_name, list_tasks_for_user, mark_running


def dispatch(user_id, task_name, args):
    if task_name == "list":
        return list_tasks_for_user(user_id)

    row = get_task_by_name(task_name)
    if not row:
        return {"err": "no such task"}
    task_id, payload = row

    if not _is_runnable(task_id):
        return {"err": "task not runnable"}
    mark_running(task_id)

    try:
        return _run(task_name, payload, args)
    except Exception:
        return {"err": "job crashed"}


def _is_runnable(task_id):
    return True


def _run(task_name, payload, args):
    if task_name.startswith("email"):
        return email_job.send(args.get("to", ""), payload)
    if task_name.startswith("report"):
        return report_job.build(args.get("filename", "report.txt"), payload)
    if task_name.startswith("cleanup"):
        return cleanup_job.purge(args.get("path", ""))
    return {"err": "unknown job"}
