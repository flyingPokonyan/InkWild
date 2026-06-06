FROM python:3.12-slim

WORKDIR /app

# 依赖从 pyproject.toml 抠出来装。不装包本身：docker-compose volume 把 ./backend
# 挂到 /app 上，uvicorn 直接从 /app 起 main:app，site-packages 里不需要副本。
COPY pyproject.toml .
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > /tmp/deps.txt \
    && pip install --no-cache-dir -r /tmp/deps.txt \
    && rm /tmp/deps.txt

COPY . .

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
