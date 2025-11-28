# High-Throughput Distributed Poker Analysis Engine

A cloud-native, asynchronous simulation pipeline for analyzing poker hands using Monte Carlo methods.

## 🏗 Architecture
This project uses a **Microservices Architecture** to handle high-compute workloads without blocking the user interface.

* **Ingestion API (Python/Flask + Gunicorn):** Handles file uploads and parses unstructured log files using Regex.
* **Message Broker (Redis):** Decouples the API from the Compute Engine, allowing for instant "202 Accepted" responses.
* **Compute Engine (Python Workers):** Horizontally scalable worker nodes that consume jobs from Redis and run 10,000+ Monte Carlo simulations per hand.
* **Frontend (React + Vite):** A real-time dashboard that polls for results and visualizes equity data.

## 🚀 Tech Stack
* **Infrastructure:** Docker & Docker Compose
* **Backend:** Python 3.11, Flask, Redis
* **Frontend:** React 18, Nginx
* **DevOps:** (We will add CI/CD here later)

## ⚡️ Key Engineering Challenges Solved
1.  **The Thundering Herd:** Implemented a Redis Queue to handle backpressure when analyzing session logs with 500+ hands.
2.  **Data Consistency:** Solved a critical list mutation bug in the Python simulation loop using defensive copying and immutable tuples.
3.  **Latency:** Optimized the ingestion pipeline to parse and queue 100 hands in <50ms.

## 🛠 How to Run Locally
```bash
git clone [https://github.com/abansal300/pokertrainer.git](https://github.com/abansal300/pokertrainer.git)
docker-compose up -d --build
# Access dashboard at http://localhost:3000