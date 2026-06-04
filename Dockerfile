FROM python:3.12-slim
WORKDIR /code
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
EXPOSE 8000
ENV DATABASE_URL=/data/app.db
VOLUME ["/data"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
