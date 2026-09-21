# App image: runs `mulitaminer` (extraction, experiment, evaluation, report).
# It talks to DeepSeek over the API and to the local NuExtract via the vllm
# service (see docker-compose.yml). No GPU needed here; the GPU belongs to vllm.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
WORKDIR /app

# Heavy eval metrics (bertscore + NLI need torch/transformers) are opt-in.
# Build with --build-arg INSTALL_EVAL=true to include them; otherwise those
# metrics are simply skipped at evaluation time.
ARG INSTALL_EVAL=false

# Those metrics on a GPU make triton JIT-compile kernels at runtime, which needs
# a C compiler the slim base does not ship. Without it every evaluation dies
# with "Failed to find C compiler".
RUN if [ "$INSTALL_EVAL" = "true" ]; then \
        apt-get update && apt-get install -y --no-install-recommends gcc \
        && rm -rf /var/lib/apt/lists/*; \
    fi

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN if [ "$INSTALL_EVAL" = "true" ]; then \
        uv sync --frozen --no-dev --group eval; \
    else \
        uv sync --frozen --no-dev; \
    fi

ENTRYPOINT ["uv", "run", "--no-sync", "mulitaminer"]
CMD ["--help"]
