FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./app ./app
COPY ./.streamlit ./.streamlit

ENV PYTHONPATH=/app
EXPOSE 8501 7860

# Shell form so $PORT (set by Railway/Heroku/etc.) is expanded. Defaults to
# 8501 for local Docker / docker compose.
CMD streamlit run app/main.py --server.port=${PORT:-8501} --server.address=0.0.0.0
