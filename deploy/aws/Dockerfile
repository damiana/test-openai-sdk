# Nenhum segredo é argumento de build ou parte das camadas da imagem.
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY test-ui/frontend/package.json test-ui/frontend/package-lock.json ./
RUN npm ci
COPY test-ui/frontend/ ./
RUN npm run build

FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000 \
    FRONTEND_DIST=/app/frontend-dist \
    APP_ENV=production
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt \
    && useradd --create-home --uid 10001 finai
COPY assistente-organizacao-financeira/*.py ./assistente-organizacao-financeira/
COPY test-ui/*.py ./test-ui/
COPY test-ui/widgets/ ./test-ui/widgets/
COPY test-ui/startup.sh ./test-ui/startup.sh
COPY --from=frontend /frontend/dist/ ./frontend-dist/
USER finai
EXPOSE 8000
CMD ["sh", "test-ui/startup.sh"]
