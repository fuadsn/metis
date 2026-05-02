# Metis - Market Intelligence System

AI agent tool that scrapes Reddit to identify pain points and generate product ideas.

## Setup

```bash
pip install -r requirements.txt

# Optional: Set up PRAW for deeper data (requires Reddit dev app)
cp .env.example .env
# Edit .env with your Reddit API credentials
```

## Usage

```bash
python main.py
```

Runs immediately, then schedules collection every 6 hours.

## Output

Generated ideas saved to `data/processed/latest_analysis.json` — designed for AI agent consumption.

## Structure

```
metis/
├── collectors/     # Reddit data collection
├── storage/        # Data persistence
├── processors/     # Pain point extraction & clustering
├── generators/     # Product idea generation
└── main.py        # Entry point & scheduler
```

## Disclaimer

This tool uses Pushshift API for data collection. Review Reddit's terms and policies before commercial use.