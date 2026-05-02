# Metis - Market Intelligence System

A CLI tool that collects posts from Hacker News, extracts pain points, clusters them, and generates product ideas with novelty and difficulty scores.

## For AI Agents

### Installation
```bash
cd /path/to/metis
pip install -r requirements.txt
```

### Commands

**Collect new posts:**
```bash
python cli.py collect
```

**Run full pipeline (collect + analyze):**
```bash
python cli.py run
```

**Output latest ideas (JSON):**
```bash
python cli.py ideas
```

**Analyze stored posts:**
```bash
python cli.py analyze
```

### Output Format

`metis run` and `metis ideas` return JSON with this structure:

```json
{
  "status": "success",
  "ideas": [
    {
      "id": "idea_cluster_api_0",
      "cluster_id": "cluster_api",
      "topic": "api",
      "description": "API documentation generator from code",
      "novelty_score": 5,
      "novelty_label": "innovative",
      "build_difficulty": 3,
      "market_difficulty": 5,
      "demand_signal": 120,
      "evidence_count": 4,
      "subreddits": ["hackernews"]
    }
  ],
  "clusters": [
    {
      "id": "cluster_api",
      "topic": "api",
      "count": 4,
      "avg_score": 30,
      "pain_points": [...]
    }
  ]
}
```

### Novelty Labels
- **obvious** (1-2): Many founders would spot this
- **interesting** (3): Non-obvious but believable
- **innovative** (4-5): Unusual insight from weak signals

### Difficulty Scale
- Build: 1 (trivial) to 10 (complex system)
- Market: 1 (clear buyer) to 10 (hard to sell)

## Usage Example for Agent

1. Run: `python cli.py run`
2. Parse JSON output from stdout
3. Extract "ideas" array
4. For each idea, use:
   - topic: what domain
   - description: the product concept
   - novelty_label: obvious/interesting/innovative
   - build_difficulty: how hard to build (1-10)
   - market_difficulty: how hard to sell (1-10)
   - evidence_count: how many posts mentioned this pain

## Data Location
- Raw posts: data/raw/
- Processed: data/processed/latest_analysis.json

## Schedule
Run python main.py --watch to collect every 6 hours automatically.
