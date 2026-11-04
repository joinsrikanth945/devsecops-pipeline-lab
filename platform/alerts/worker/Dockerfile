FROM python:3.12-slim
RUN pip install --no-cache-dir confluent-kafka==2.6.1 \
 && useradd --uid 10001 --no-create-home app \
 && mkdir /state && chown app /state
WORKDIR /app
COPY app.py .
USER app
VOLUME /state
CMD ["python", "-u", "app.py"]
