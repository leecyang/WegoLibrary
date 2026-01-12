FROM python:3.9-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

# Ensure default sqlite directory exists
RUN mkdir -p /app/data

# Initialize empty DB
# RUN python -c "from app.database import create_db_and_tables; create_db_and_tables()"

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
