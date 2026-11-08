FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y --no-install-recommends \
    bash build-essential python3 coreutils ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
ENV HOME=/tmp
CMD ["sleep", "infinity"]
