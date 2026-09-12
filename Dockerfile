FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir .

# Bind all interfaces *inside* the container so host publish works.
# Publish only to the host loopback: -p 127.0.0.1:4180:4180
ENV OPENBUNDLE_EXPOSE=1
EXPOSE 4180
CMD ["openbundle", "serve", "--host", "0.0.0.0", "--expose", "--port", "4180"]
