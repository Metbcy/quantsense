# QuantSense 📈🧠

**AI-powered quantitative trading platform** — backtest strategies, analyze market sentiment, and paper trade — all from a single dashboard.

![Next.js](https://img.shields.io/badge/Next.js_16-black?style=flat-square&logo=next.js)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=flat-square&logo=fastapi&logoColor=white)
![Python](https://img.shields.io/badge/Python_3.12+-3776AB?style=flat-square&logo=python&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?style=flat-square&logo=typescript&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)

---

## Features

### 📊 Backtesting Engine
- **5 built-in strategies**: Momentum (SMA), Mean Reversion (RSI), Sentiment-Weighted Momentum, Bollinger Bands, MACD
- **Configurable parameters**: Adjust periods, thresholds, and position sizing
- **Performance metrics**: Sharpe ratio, max drawdown, win rate, profit factor, equity curves
- **Risk management**: Trailing stops, take-profit, position concentration limits, daily loss circuit breaker

### 🧠 AI Sentiment Analysis
- **Two-tier NLP pipeline**: VADER (instant, offline) + LLM deep analysis (Groq/OpenAI/Anthropic)
- **Multiple news sources**: NewsAPI, Yahoo Finance RSS, Reddit (r/wallstreetbets, r/stocks)
- **Financial-tuned VADER**: Custom lexicon with 40+ financial terms for accurate market sentiment
- **Pluggable LLM providers**: Bring your own API key for Claude, GPT, Llama, or use free Groq tier

### 💰 Paper Trading
- **Virtual portfolio**: Start with $100K (configurable), simulate real trading
- **Order types**: Market, limit, and stop-loss orders
- **Position tracking**: Average cost, unrealized P&L, daily change
- **Trade logging**: Every trade recorded with strategy context and sentiment score

### 🖥️ Dashboard
- **Portfolio overview**: Value chart, holdings table, daily P&L
- **Backtest lab**: Configure strategies, visualize equity curves, compare results
- **Sentiment feed**: Color-coded news with sentiment scores, trend indicators
- **Stock screener**: RSI, SMA signals across your watchlist

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16, TypeScript, Tailwind CSS, shadcn/ui, Recharts, Lightweight Charts |
| Backend | Python 3.12+, FastAPI, SQLAlchemy 2.0, Pydantic v2 |
| NLP | VADER (nltk) with financial lexicon |
| LLM | Groq/Llama 3.3 (free), OpenAI, Anthropic (pluggable) |
| Market Data | yfinance, Alpha Vantage (pluggable provider interface) |
| Database | SQLite (dev), PostgreSQL-ready |
| Infra | Docker Compose |

---

## Quick Start

### Prerequisites
- Python 3.12+
- Node.js 18+
- npm

### 1. Clone & Setup

```bash
git clone https://github.com/Metbcy/quantsense.git
cd quantsense

# Backend
cd backend
python3 -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt
python -c "import nltk; nltk.download('vader_lexicon', quiet=True)"

# Frontend
cd ../frontend
npm install
```

### 2. Configure Environment

```bash
cp .env.example .env
# Edit .env with your API keys (all optional - app works without them)
```

### 3. Run

```bash
# Terminal 1: Backend
cd backend
source venv/bin/activate
uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend
npm run dev
```

Open **http://localhost:3000** 🚀

### Docker (Alternative)

```bash
docker-compose up --build
```

---

## Configuration

All API keys are **optional**. The app works with zero configuration using free data sources.

| Variable | Required | Description |
|----------|----------|-------------|
| `NEWSAPI_KEY` | No | [NewsAPI.org](https://newsapi.org) for news headlines |
| `GROQ_API_KEY` | No | [Groq](https://console.groq.com) for free LLM sentiment analysis |
| `ALPHA_VANTAGE_API_KEY` | No | [Alpha Vantage](https://www.alphavantage.co) for additional market data |
| `OPENAI_API_KEY` | No | OpenAI for GPT-powered sentiment |
| `ANTHROPIC_API_KEY` | No | Anthropic for Claude-powered sentiment |
| `REDDIT_CLIENT_ID` | No | Reddit API for crowd sentiment |
| `REDDIT_CLIENT_SECRET` | No | Reddit API secret |

---

## Architecture

```
quantsense/
├── frontend/                  # Next.js 16 (App Router)
│   ├── src/app/
│   │   ├── dashboard/         # Portfolio overview
│   │   ├── backtest/          # Strategy backtesting
│   │   ├── sentiment/         # News sentiment analysis
│   │   └── settings/          # Configuration
│   ├── src/components/        # Shared UI components
│   └── src/lib/               # API client, hooks, utilities
├── backend/                   # Python FastAPI
│   ├── api/                   # REST + WebSocket endpoints
│   ├── engine/                # Backtesting core + indicators + screener
│   ├── sentiment/             # NLP + LLM pipeline
│   ├── data/                  # Market data providers
│   ├── trading/               # Paper trading + risk management
│   └── models/                # Database + Pydantic schemas
├── docker-compose.yml
└── .env.example
```

---

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/market/quote/{ticker}` | Current stock quote |
| GET | `/api/market/ohlcv/{ticker}` | Historical OHLCV data |
| GET | `/api/market/screener` | Screen watchlist tickers |
| POST | `/api/backtest/run` | Run a backtest |
| GET | `/api/backtest/strategies` | List available strategies |
| GET | `/api/backtest/results` | List backtest history |
| GET | `/api/sentiment/analyze/{ticker}` | Analyze ticker sentiment |
| GET | `/api/sentiment/feed` | Sentiment feed |
| POST | `/api/trading/order` | Submit paper trade |
| GET | `/api/trading/portfolio` | Portfolio summary |
| GET | `/api/settings/watchlist` | Get watchlist |
| WS | `/api/ws/live` | Live price + sentiment updates |

Full API docs at **http://localhost:8000/docs** (Swagger UI)

---

## Strategies

| Strategy | Signal | Default Params |
|----------|--------|---------------|
| **Momentum** | Buy above SMA, sell below | `sma_period: 20` |
| **Mean Reversion** | Buy RSI < 30, sell RSI > 70 | `rsi_period: 14` |
| **Sentiment Momentum** | Momentum + sentiment weight | `sma_period: 20, sentiment_weight: 0.3` |
| **Bollinger Bands** | Buy at lower band, sell at upper | `period: 20, std_dev: 2.0` |
| **MACD** | Buy on bullish crossover | `fast: 12, slow: 26, signal: 9` |

---

## Future Roadmap

- [ ] Real brokerage integration (Alpaca API)
- [ ] Options and crypto support
- [ ] Walk-forward optimization
- [ ] Strategy marketplace / sharing
- [ ] Mobile app (React Native)
- [ ] Cloud deployment (Vercel + Railway)

---

## License

MIT License — see [LICENSE](LICENSE) for details.

---

<p align="center">Built with ❤️ by <a href="https://github.com/Metbcy">Amir Bredy</a></p>
