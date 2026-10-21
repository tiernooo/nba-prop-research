# NBA Daily Prop Research

A Streamlit dashboard which screens the selected NBA game date against **previous-season regular-season** usage rates, opponent NBA Fantasy Points Allowed, and historical PTS/REB/AST hit rates.

## Run

```bash
pip install -r requirements.txt
streamlit run app.py
```

Open the browser URL printed by Streamlit. Choose a US NBA game date, then press **Run daily screen**. Results can be downloaded as CSV.

## Defaults

- 2025–26 historical season
- Usage percentage >= 24%
- Opponent among 10 teams conceding the MOST NBA fantasy points per game in selected historical season
- At least 93% of the player's regular-season games CLEAR a displayed X.5 prop line
- At least 20 logged games by a player and 20 observed opponent team games (adjustable)

## Data sources

- NBA Stats via `nba_api` -> `PlayerGameLogs` for all player game logs and `LeagueDashPlayerStats(Advanced)` for USG_PCT.
- ESPN public NBA scoreboard endpoint for schedule.
- CSV upload option if NBA Stats access is blocked. Game log needs PLAYER_ID, PLAYER_NAME, TEAM_ABBREVIATION, GAME_ID, MATCHUP, PTS, REB, AST, STL, BLK, TOV, ideally GAME_DATE and NBA_FANTASY_PTS. Usage CSV needs PLAYER_ID and USG_PCT.

## Definitions & cautions

Defense score = **sum of fantasy points given up by every opposing player in a game**, averaged by opponent across games. Rank 1 is worst defense. This is total fantasy points conceded, NOT by position. It uses official NBA_FANTASY_PTS where present. If unavailable it calculates conventional NBA fantasy scoring: PTS + 1.2 REB + 1.5 AST + 3 STL + 3 BLK - TOV + 1.5 DD + 3 TD.

The 93% threshold is calculated against all historical regular-season games, not solely matchups against bad defenses. `Over 19.5` qualifies if a player scores 20+ points in >=93% of their games. Equal-to does not count for an over. Players with <20 games are removed by default to avoid 93% on a tiny sample. No bookmaker markets are fetched or verified: an empirically safe line is not proof a current betting market offers it, and historical frequency does not establish expected value.

**Important limitations:** Historical NBA Stats usage and game data may not reflect trades, season-opening roster changes, injuries, absences, minute restrictions, or projected starting lineups. A player traded AFTER the baseline season will not appear for their new team until a newer season is selected. NBA Stats endpoints may time out or block hosted/cloud IPs; CSV input is available as fallback. ESPN date selection follows US NBA calendar (not Australia/Perth day).
