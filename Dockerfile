FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8766

CMD ["python", "-m", "shouwang", "serve", "--host", "0.0.0.0"]
