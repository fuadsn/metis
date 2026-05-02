# Metis - Market Intelligence Skill

## What Metis Does

Metis collects posts from Hacker News (top, new, best, ask, show) to identify pain points and generate product ideas with difficulty scores.

## Available Commands

Run from the `metis/` directory:

### python mcp_simple.py collect
Collect latest posts from Hacker News sources.
- Output: JSON with collected count, new count, total stored

### python mcp_simple.py analyze
Run full pipeline: collect posts → clean → extract pain points → cluster → generate ideas.
- Output: JSON with posts_processed, pain_points_count, clusters, ideas

### python mcp_simple.py ideas [limit]
Get latest product ideas sorted by novelty and demand.
- Input: limit (optional, default 10)
- Output: JSON list of ideas

### python mcp_simple.py clusters
Get current pain point clusters.
- Output: JSON list of clusters with topic, post count, sentiments

## Output Format

Each idea includes:
- `description`: Product description
- `topic`: Pain point topic (api, database, auth, etc.)
- `novelty_score`: 1-5 (5 = innovative)
- `novelty_label`: "obvious" | "interesting" | "innovative"
- `build_difficulty`: 1-10
- `market_difficulty`: 1-10
- `demand_signal`: Calculated from post count × score
- `evidence_count`: Number of posts supporting this idea

## Usage Example

```python
# Run full analysis
result = subprocess.run(
    ["python3", "mcp_simple.py", "analyze"],
    capture_output=True, cwd="metis"
)
ideas = json.loads(result.stdout)["ideas"]

# Get top 5 ideas
result = subprocess.run(
    ["python3", "mcp_simple.py", "ideas", "5"],
    capture_output=True, cwd="metis"
)
top_ideas = json.loads(result.stdout)["ideas"]
```

## For Agents

When asked to find product opportunities or analyze market pain points:
1. Run `python mcp_simple.py analyze` in metis directory
2. Parse JSON output for ideas
3. Filter by novelty_score for innovative ideas
4. Filter by build_difficulty if resource-constrained
5. Present top opportunities with evidence counts