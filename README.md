# BS Detector

> **Decentralized AI fact-checking for social media posts**

Built for the [GenLayer Bradbury Hackathon](https://genlayer.com) · Track: **AI Governance**

![GenLayer](https://img.shields.io/badge/Powered%20by-GenLayer-7b68ee)
![Python](https://img.shields.io/badge/Python-3.10+-blue)
![License](https://img.shields.io/badge/License-MIT-green)

## 🔴 Live Demo

**[https://bullshit-detector-wv8w.onrender.com](https://bullshit-detector-wv8w.onrender.com)**

Deployed on GenLayer Testnet Bradbury
Contract: `0x6500d5ED0bCb805cDF35cFfCcAB118C9485AE7A2`

## What is this?

Social media is full of misleading claims, fake gurus, and hype. **BS Detector** uses [GenLayer's](https://genlayer.com) decentralized AI infrastructure to fact-check posts: not one model, but **multiple independent AI validators** that must reach consensus on whether a claim is legit or bullshit.

### How it works

```
Tweet URL → Extract content → Submit to GenLayer contract
                                        ↓
                              Lead validator analyzes
                              (evidence gathering + fact-checking)
                                        ↓
                              Co-validators verify independently
                                        ↓
                              Consensus via Equivalence Principle
                                        ↓
                              On-chain verdict: BULLSHIT / LEGIT / INCONCLUSIVE
```

### Key features

- **Multi-validator consensus**: Multiple independent AI validators must agree on the verdict (Optimistic Democracy + Comparative Equivalence Principle)
- **On-chain verifiable**: Results are stored on GenLayer's blockchain, not a centralized database
- **Evidence-based**: Fetches URLs from claims, checks author credibility, detects manipulation tactics
- **No single point of failure**: Decentralized infrastructure means no one entity controls the truth

## Vision

The long-term goal of BS Detector goes beyond a hackathon project. As misinformation spreads faster than ever, large platforms and online communities need tools to quickly fact-check posts before they go viral.

**BS Detector is designed to be the infrastructure layer for this**: platforms, newsrooms, Discord communities, or browser extensions could plug directly into the contract and get a decentralized, censorship-resistant fact-check on any post in seconds: without relying on a single company or AI model to decide what's true.

Because truth shouldn't be controlled by one entity.

## Demo

1. Paste a tweet URL (x.com or twitter.com)
2. The app extracts the content (including quoted tweets)
3. GenLayer's validators analyze the claim from multiple angles
4. You get a verdict with confidence score, red flags, and detailed reasoning

### Verdicts

| Verdict | Meaning |
|---------|---------|
| **BULLSHIT** | False, exaggerated, technically implausible, or deliberately misleading |
| **LEGIT** | Plausible, supported by evidence, not manipulative |
| **INCONCLUSIVE** | Mixed or insufficient evidence |

## Architecture

```
┌─────────────────────────────────────────────┐
│                  Frontend                    │
│           (Vanilla JS + CSS)                │
│     Tweet embed + verdict display            │
└──────────────────┬──────────────────────────┘
                   │ REST API
┌──────────────────▼──────────────────────────┐
│              FastAPI Backend                  │
│         Async job queue + polling            │
│         In-memory cache (SHA256)             │
│         GenLayer service wrapper             │
└──────────────────┬──────────────────────────┘
                   │ genlayer-py SDK
┌──────────────────▼──────────────────────────┐
│      GenLayer Testnet Bradbury               │
│    ┌─────────────────────────────┐          │
│    │   BullshitDetector Contract │          │
│    │  - Evidence gathering       │          │
│    │  - Multi-angle analysis     │          │
│    │  - Equivalence Principle    │          │
│    │  - TreeMap result storage   │          │
│    └─────────────────────────────┘          │
│    Validator 1 ←→ Validator 2 ←→ ...        │
└─────────────────────────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.10+
- A GenLayer account with a deployed contract

### 1. Clone & install

```bash
git clone https://github.com/instasamer/bullshit-detector.git
cd bullshit-detector
pip install -r requirements.txt
```

### 2. Deploy the contract

```bash
python deploy_contract.py
```

This will:
- Generate a new private key
- Deploy the `BullshitDetector` contract to GenLayer StudioNet
- Save the config to `deploy_config.json`

### 3. Configure environment

```bash
cp .env.example .env
```

Edit `.env` with the values from `deploy_config.json`:

```env
GENLAYER_CONTRACT_ADDRESS=0x...
GENLAYER_PRIVATE_KEY=0x...
GENLAYER_CHAIN=testnet_bradbury
```

### 4. Run

```bash
python backend/main.py
```

Open http://localhost:8000

### Docker

```bash
docker compose up --build
```

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/verify/text` | Verify a claim by text + optional source URL |
| `POST` | `/api/verify/url` | Fetch URL content and verify |
| `GET` | `/api/poll/{job_id}` | Poll for verification result (async) |
| `GET` | `/api/results` | Get all previously verified claims |
| `GET` | `/api/health` | Health check with contract info |

### Example request

```bash
curl -X POST http://localhost:8000/api/verify/text \
  -H "Content-Type: application/json" \
  -d '{
    "claim_text": "I made $100k in 2 weeks with this AI trading bot",
    "source_url": "https://x.com/user/status/123"
  }'
```

### Example response

```json
{
  "job_id": "0xabc123...",
  "status": "pending"
}
```

Then poll:

```bash
curl http://localhost:8000/api/poll/0xabc123...
```

```json
{
  "verdict": "BULLSHIT",
  "confidence": 92,
  "reason": "The claim of $100k profit in 2 weeks from an AI trading bot is highly implausible...",
  "red_flags": [
    "Unrealistic profit claims",
    "DM-based sales funnel",
    "Artificial scarcity (only 10 spots)"
  ],
  "evidence_summary": "No verifiable evidence of profits. Classic pump-and-dump pattern.",
  "status": "done"
}
```

## Intelligent Contract

The `BullshitDetector` contract (`contracts/bullshit_detector.py`) runs on GenLayer and performs:

1. **Evidence gathering**: Fetches URLs found in the claim (max 2 web requests)
2. **Multi-angle analysis**: Evidence vs claims, technical feasibility, manipulation detection, author credibility
3. **Consensus**: Uses `eq_principle.prompt_comparative()` to ensure multiple validators reach the same verdict
4. **Storage**: Results persisted on-chain in a `TreeMap`

## Tech Stack

| Component | Technology |
|-----------|------------|
| Frontend | Vanilla JS, CSS3 |
| Backend | FastAPI, Uvicorn, Pydantic |
| Contract | GenLayer Intelligent Contract (Python) |
| Chain | GenLayer Testnet Bradbury |
| SDK | genlayer-py |
| Deploy | Render (Docker) |

## License

MIT
