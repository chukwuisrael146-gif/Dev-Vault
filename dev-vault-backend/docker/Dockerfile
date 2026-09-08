FROM python:3.14-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_READ_ENV_FILE=False
WORKDIR /app
COPY requirements/ requirements/
RUN python -m pip install --no-cache-dir -c requirements/constraints.txt -r requirements/production.txt \
    && groupadd --system --gid 10001 devvault \
    && useradd --system --uid 10001 --gid devvault --home-dir /app devvault
COPY --chown=10001:10001 . .
RUN mkdir -p /app/var/exports /app/staticfiles && chown -R 10001:10001 /app/var /app/staticfiles
USER 10001:10001
EXPOSE 8000
CMD ["gunicorn", "config.wsgi:application", "--config", "docker/gunicorn.conf.py"]
