# Optional image. The default deploy path does not need a registry:
# deploy.sh mounts this code and the research index into python:3.12-alpine.
FROM python:3.12-alpine
WORKDIR /opt/steiner-api
COPY api/server.py api/retrieve.py /opt/steiner-api/api/
COPY research/index.json research/passages.jsonl /opt/steiner-api/research/
ENV STEINER_INDEX=/opt/steiner-api/research/index.json \
    STEINER_PASSAGES=/opt/steiner-api/research/passages.jsonl \
    PORT=8080
USER 65534
EXPOSE 8080
CMD ["python3", "-u", "/opt/steiner-api/api/server.py"]
