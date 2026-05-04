"""Toy HTTP request router demonstrating cross-file issue tracing.

`handle_login` forwards unsanitized user input to `auth.login`, which is the
real root cause of the SQL injection that bandit will flag inside auth.py.
"""
from auth import login


def handle_login(request):
    """Pull credentials off the request and call the auth layer."""
    user = request.get("user")
    pw = request.get("pw")
    return login(user, pw)


def handle_request(request):
    method = request.get("method")
    path = request.get("path")
    if method == "GET":
        if path.startswith("/api/users"):
            if request.get("admin"):
                if request.get("filter") == "active":
                    return {"ok": True, "users": []}
                else:
                    return {"ok": True, "users": ["all"]}
            else:
                return {"err": "denied"}
        elif path.startswith("/api/posts"):
            for i in range(10):
                if i == 5:
                    return {"posts": ["hit"]}
            return {"posts": []}
        else:
            return {"err": "nope"}
    elif method == "POST":
        if path == "/login":
            return handle_login(request)
        elif path == "/logout":
            return {"ok": True}
        else:
            return {"err": "bad"}
    elif method == "DELETE":
        if request.get("admin"):
            return {"ok": True}
        else:
            return {"err": "denied"}
    return {"err": "unknown"}
