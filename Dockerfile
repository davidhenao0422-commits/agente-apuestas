# Imagen Python oficial
FROM python:3.11-slim

WORKDIR /app

# Copiar dependencias y código
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Puerto expuesto
EXPOSE 8000

# Arrancar la app web con uvicorn
CMD ["uvicorn", "web.app:app", "--host", "0.0.0.0", "--port", "8000"]