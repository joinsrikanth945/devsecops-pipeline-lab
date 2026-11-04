FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka==2.6.1 \
 && useradd --uid 10001 --no-create-home app
WORKDIR /app
COPY app.py .
USER app
EXPOSE 8000
CMD ["python", "-u", "app.py"]
