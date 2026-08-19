# Aegis — Real-Time Trust Intelligence Platform for Digital Lending

> Multi-signal fraud intelligence with explainable decisioning and human-in-the-loop review

---

## ⚠️ Synthetic Data Notice

Every record, applicant, device fingerprint, transaction, and behavioral signal in this repository is **synthetic** — programmatically generated for demonstration purposes only. Nothing here is derived from, sampled from, or representative of any real financial institution, any real customer, or any real customer behavior. No production data, no scraped data, and no personally identifiable information of any kind is used. Model metrics reported in this project describe performance on synthetic data and should not be interpreted as claims about real-world fraud detection accuracy.

---

## Problem Statement

**Synchrony Problem 1 — Real-Time Fraud Detection and Prevention in Digital Lending Ecosystems**

## Problem Statement

**Real-Time Fraud Detection and Prevention in Digital Lending Ecosystems**

**Objective:** To develop a real-time fraud detection platform that integrates machine learning and behavioral analytics to identify, prevent, and respond to fraudulent activities across digital lending channels, ensuring secure and seamless customer experiences.

**Challenge:** With the rapid growth of digital lending, fraud patterns are becoming increasingly sophisticated and dynamic. Traditional rule-based systems struggle to keep pace with evolving threats. The key challenge is to create a proactive, self-learning system capable of detecting anomalies in real time, reducing false positives, and adapting to new fraud vectors without compromising customer trust or operational efficiency.

*Source: Synchrony Hackathon 2026 official problem brief.*

---

## Tech Stack

- **Backend:** FastAPI (Python 3.11)
- **Database:** PostgreSQL 16 + `pgvector` extension
- **ML:** XGBoost, scikit-learn, SHAP
- **Embeddings:** `sentence-transformers` / `all-MiniLM-L6-v2` (local inference, no external API)
- **LLM:** Groq API — `openai/gpt-oss-20b` (primary), Gemini 2.5 Flash (fallback)
- **Frontend:** React 18 + Vite + TypeScript + Tailwind CSS + shadcn/ui + Recharts
- **Container:** Docker Compose

---

## Quick Start

1. Copy the environment template and fill in your API keys:
   ```bash
   cp .env.example .env
   ```
2. Build and start the stack:
   ```bash
   docker compose up --build
   ```
3. Verify the API is live: <http://localhost:8000/health>

---

## Architecture

See [docs/architecture.md](docs/architecture.md).

---

## Repo Layout

```
aegis/
├── backend/            FastAPI service
│   ├── app/
│   │   ├── models/     SQLAlchemy ORM models
│   │   ├── schemas/    Pydantic request/response schemas
│   │   ├── routers/    API route modules
│   │   ├── services/   Business logic + integrations
│   │   └── ml/         Inference-time ML helpers
│   └── tests/          pytest suite
├── frontend/           React + Vite dashboard (scaffolded later)
├── ml/                 Offline data generation, training, evaluation
├── data/               Synthetic datasets (gitignored)
├── docs/               Architecture notes and demo script
├── scripts/            Dev and demo utilities
└── docker-compose.yml
```

---

## Status

🚧 **Work in progress.** Repository skeleton only — features not yet implemented.
