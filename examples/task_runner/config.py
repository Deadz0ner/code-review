"""Application configuration.

Centralizes secrets and tunable paths for the task runner. Several jobs depend
on values defined here, so any flaw in this module propagates widely.
"""
import os

SECRET_KEY = os.getenv("APP_SECRET", "change-me-in-prod")

REPORT_OUTPUT_DIR = os.getenv("REPORT_DIR", "/tmp/reports")

CLEANUP_ROOT = os.getenv("CLEANUP_ROOT", "/tmp/runner_workspace")

ADMIN_USERS = ["admin", "root"]
