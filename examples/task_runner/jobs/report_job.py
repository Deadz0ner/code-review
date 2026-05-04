"""Report-building task.

Writes a payload to disk under REPORT_OUTPUT_DIR using a caller-supplied
filename. The filename is joined with the output directory using os.path.join,
which does not prevent traversal — a filename like "../../etc/passwd" escapes
the intended directory.
"""
import os

from config import REPORT_OUTPUT_DIR


def build(filename, payload):
    if not os.path.isdir(REPORT_OUTPUT_DIR):
        os.makedirs(REPORT_OUTPUT_DIR, exist_ok=True)

    target = os.path.join(REPORT_OUTPUT_DIR, filename)

    with open(target, "w") as f:
        f.write(str(payload))
    return {"ok": True, "path": target}


def render_html(payload, theme="light", show_header=True, show_footer=True,
                include_summary=True, include_details=True, max_rows=100):
    out = []
    if show_header:
        if theme == "light":
            out.append("<header style='background:#fff'>")
        elif theme == "dark":
            out.append("<header style='background:#222;color:#eee'>")
        else:
            out.append("<header>")
        out.append("</header>")
    if include_summary:
        if isinstance(payload, dict):
            for k, v in payload.items():
                if v is None:
                    continue
                if isinstance(v, list):
                    out.append("<p>%s: %d items</p>" % (k, len(v[:max_rows])))
                elif isinstance(v, dict):
                    out.append("<p>%s: %d keys</p>" % (k, len(v)))
                else:
                    out.append("<p>%s: %s</p>" % (k, v))
        elif isinstance(payload, list):
            for i, item in enumerate(payload[:max_rows]):
                out.append("<p>%d: %s</p>" % (i, item))
        else:
            out.append("<p>%s</p>" % payload)
    if include_details:
        out.append("<hr>")
    if show_footer:
        if theme == "dark":
            out.append("<footer style='background:#222'>end</footer>")
        else:
            out.append("<footer>end</footer>")
    return "\n".join(out)
