"""CLI entry point for the task runner.

Reads --user-id, --task-name, and --token from argv and dispatches the matching
task. Designed to demonstrate cross-file root-cause tracing: most of the issues
the static tools flag downstream actually originate here, where untrusted input
enters the system.
"""
import sys

from auth import verify_token
from scheduler import dispatch


def parse_args(argv):
    args = {}
    for chunk in argv[1:]:
        if "=" in chunk and chunk.startswith("--"):
            key, value = chunk[2:].split("=", 1)
            args[key] = value
    return args


def main():
    args = parse_args(sys.argv)
    user_id = args.get("user-id", "anonymous")
    task = args.get("task-name", "")
    token = args.get("token", "")

    if not verify_token(user_id, token):
        print("auth failed")
        return 1

    result = dispatch(user_id, task, args)
    print(result)
    return 0


if __name__ == "__main__":
    sys.exit(main())
