# Stage 1: build the frontend
FROM node:22-alpine AS frontend
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-fund --no-audit
COPY frontend/ ./
RUN npm run build

# Stage 2: backend (engine + API) + built frontend in one image.
FROM python:3.13-slim
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/engine ./engine
COPY backend/app.py backend/launch.py ./
COPY backend/coordinates ./coordinates
COPY backend/examples ./examples
COPY --from=frontend /build/dist /app/frontend/dist
EXPOSE 8000
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8000"]
