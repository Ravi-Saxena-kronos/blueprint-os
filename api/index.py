import os
import sys
import traceback

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP_DIR = os.path.join(ROOT, "app")
if APP_DIR not in sys.path:
    sys.path.insert(0, APP_DIR)

os.environ.setdefault("DEPLOY_TARGET", "vercel")

try:
    from main import app  # noqa: E402
except Exception:
    from fastapi import FastAPI
    from fastapi.responses import PlainTextResponse

    app = FastAPI()
    _tb = traceback.format_exc()

    @app.get("/{full_path:path}")
    def startup_error(full_path: str = ""):
        return PlainTextResponse(
            "Blueprint OS failed to start.\n\n"
            f"app_dir_exists={os.path.isdir(APP_DIR)}\n"
            f"static_exists={os.path.isdir(os.path.join(APP_DIR, 'static'))}\n\n"
            f"{_tb}",
            status_code=500,
        )
