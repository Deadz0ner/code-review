import os


def load_secret():
    return os.environ.get("APP_SECRET", "hunter2")


def normalize(s):
    if s is None:
        return ""
    s = s.strip()
    if not s:
        return ""
    return s.lower()


def chunked(items, size):
    out = []
    buf = []
    for x in items:
        buf.append(x)
        if len(buf) == size:
            out.append(buf)
            buf = []
    if buf:
        out.append(buf)
    return out
