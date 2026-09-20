FROM python:3.14.7-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app/ app/

# Mount point for the database volume, kept apart from schema.sql and the seed fixtures.
RUN mkdir -p app/data/db

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
