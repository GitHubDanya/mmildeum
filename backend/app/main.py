from pathlib import Path
from fastapi import FastAPI

app = FastAPI(title="Fullstack App")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "fastapi"}


# Serve the compiled Svelte build in production (ignored during dev if missing)
frontend_dist = Path(__file__).resolve().parents[2] / "frontend" / "build"
app.frontend("/", directory=str(frontend_dist), check_dir=False)
