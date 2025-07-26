FROM python:3.11-slim
WORKDIR /app

# Install dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend and frontend code
COPY backend ./backend
COPY frontend ./frontend
COPY wsgi.py ./wsgi.py

CMD ["python", "wsgi.py"]
