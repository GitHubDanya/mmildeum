.PHONY: dev build types kill

# Run FastAPI (port 8000) and Vite (port 5173) concurrently
dev:
	@trap 'trap - INT TERM EXIT; kill $$(jobs -p) 2>/dev/null; wait 2>/dev/null; fuser -k 8000/tcp 5173/tcp 2>/dev/null || true' INT TERM EXIT; \
	(cd backend && uv run fastapi dev app/main.py --host 127.0.0.1 --port 8000) & \
	(cd frontend && npm run dev) & \
	wait

# Manually clear stuck processes on dev ports
kill:
	@fuser -k 8000/tcp 5173/tcp 2>/dev/null || true

# Generate TypeScript interfaces directly from FastAPI's OpenAPI schema
types:
	cd frontend && npx openapi-typescript http://127.0.0.1:8000/openapi.json -o src/lib/api-types.d.ts

# Build frontend static bundle and serve everything via FastAPI
build:
	cd frontend && npm run build
	cd backend && uv run fastapi run app/main.py --port 8000
