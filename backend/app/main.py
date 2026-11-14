from pathlib import Path
from fastapi import FastAPI
from app.routes import router
from asyncio import to_thread
from contextlib import asynccontextmanager
from app.services.raster_download import ensure_terrain_maps

@asynccontextmanager
async def lifespan(_app: FastAPI):
    await to_thread(ensure_terrain_maps)
    yield

app = FastAPI(title="Fullstack App", lifespan=lifespan)
app.include_router(router)


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
