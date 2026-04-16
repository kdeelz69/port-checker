# Port Checker Dashboard

A lightweight Flask dashboard that shows which processes are listening on which ports, grouped by project-like context (working directory, executable path, and command).

## What It Shows

- Listening TCP/UDP (inet) ports
- Process name and PID
- Executable path
- Working directory
- Full command line
- Smart grouping and filtering in the UI

## Tech Stack

- Python 3
- Flask
- psutil
- Docker SDK for Python

## Prerequisites

- Docker Desktop or Docker Engine
- Docker Compose v2

## Get the Code

From your terminal, clone the repository and move into it:

```bash
git clone https://github.com/kdeelz69/port-checker.git
cd port-checker
```

## Run with Docker Compose

```bash
docker compose up --build -d
```

Open:

- http://localhost:5001

To stop:

```bash
docker compose down
```

## Run with Docker (Without Compose)

```bash
docker build -t port-checker .
docker run --rm -p 5001:5001 --name port-checker port-checker
```

## Environment Variables

- `PORT_DASHBOARD_HOST` (default: `0.0.0.0`)
- `PORT_DASHBOARD_PORT` (default: `5001`)
- `INCLUDE_DOCKER_CONTAINERS` (default: `1`)

## Platform Notes (Important)

This app depends on `psutil` to inspect OS processes and listening ports.

- Docker on Linux: `psutil` sees the container namespace, but this project also queries Docker Engine (via `/var/run/docker.sock`) to list other running containers and their ports.
- Docker Desktop on Windows/macOS: host OS process visibility is still limited, but container port visibility works when Docker socket is mounted.

## Troubleshooting

- `ImportError: psutil`:
  - Rebuild the image: `docker compose up --build`
- Port `5001` already in use:
  - Change mapped port in `docker-compose.yml` (for example `5050:5001`).
- Empty or partial process list:
  - Check Docker socket mount and ensure other containers are running.

## Project Structure

- `port_project_dashboard.py`: Flask app and embedded dashboard UI
- `requirements.txt`: Python dependencies
- `Dockerfile`: container image definition
- `docker-compose.yml`: local container orchestration

## License

Add your preferred license here.
