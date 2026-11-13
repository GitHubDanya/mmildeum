from pathlib import Path
from fastapi import FastAPI

app = FastAPI(title="Fullstack App")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "fastapi"}


frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "build"

if frontend_dist.exists():
    app.frontend("/", directory=str(frontend_dist))
else:

    @app.get("/")
    def dev_root():
        return {
            "status": "dev",
            "message": "Frontend build not found. Open http://localhost:5173 for Vite dev server or run `npm run build` in frontend/.",
        }
