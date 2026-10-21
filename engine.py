"""NBA prop screen calculation functions; independent of web and Streamlit."""
import math
import re
import pandas as pd

STATS = ['PTS','REB','AST']


def opponent_from_matchup(matchup: str) -> str | None:
    match = re.search(r'(?:vs\.|@)\s*([A-Z]{3})\s*$', str(matchup))
    return match.group(1) if match else None


def clean_games(frame: pd.DataFrame) -> pd.DataFrame:
    df = frame.copy()
    needed = {'PLAYER_ID','PLAYER_NAME','TEAM_ABBREVIATION','GAME_ID','MATCHUP','PTS','REB','AST','STL','BLK','TOV'}
    missing = needed.difference(df.columns)
    if missing:
        raise ValueError(f'Missing game-log columns: {", ".join(sorted(missing))}')
    for col in ['PTS','REB','AST','STL','BLK','TOV']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['PTS','REB','AST','STL','BLK','TOV'])
    df['OPP'] = df['MATCHUP'].map(opponent_from_matchup)
    df = df.dropna(subset=['OPP'])
    # NBA Fantasy scoring, including bonuses for double/triple doubles.
    # NBA official fantasy points are preferred when supplied.
    if 'NBA_FANTASY_PTS' in df.columns:
        df['FANTASY'] = pd.to_numeric(df['NBA_FANTASY_PTS'], errors='coerce')
    else:
        df['FANTASY'] = float('nan')
    categories = (df[['PTS','REB','AST','STL','BLK']] >= 10).sum(axis=1)
    calculated = (df['PTS'] + 1.2*df['REB'] + 1.5*df['AST'] +
                  3*df['STL'] + 3*df['BLK'] - df['TOV'] +
                  (categories >= 2)*1.5 + (categories >= 3)*3)
    df['FANTASY'] = df['FANTASY'].fillna(calculated)
    return df.drop_duplicates(subset=['PLAYER_ID','GAME_ID'], keep='last')


def defensive_rankings(games: pd.DataFrame) -> pd.DataFrame:
    # Total fantasy points conceded by team per game, not per opposing player-game.
    total = games.groupby(['OPP','GAME_ID'], as_index=False)['FANTASY'].sum()
    ranking = (total.groupby('OPP', as_index=False)
               .agg(FP_ALLOWED=('FANTASY','mean'), OPP_GAMES=('GAME_ID','nunique'))
               .sort_values(['FP_ALLOWED','OPP'], ascending=[False,True])
               .reset_index(drop=True))
    ranking['DEF_RANK'] = ranking.index + 1
    return ranking


def safe_line(values: pd.Series, minimum_pct=93.0):
    vals = pd.to_numeric(values, errors='coerce').dropna()
    if vals.empty:
        return None
    # Strictly surpassing a .5 line means stat >= next integer.
    # Find the highest threshold achieved at least target % of games.
    required = math.ceil(len(vals) * minimum_pct / 100 - 1e-12)
    ascending = sorted(vals.astype(int).tolist())
    threshold = ascending[len(ascending)-required]
    if threshold < 1:
        return None  # do not surface Over -0.5
    hits = int((vals >= threshold).sum())
    return {'line': threshold-0.5, 'hits': hits, 'games': len(vals),
            'hit_rate': hits / len(vals)*100, 'threshold': threshold}


def screen(games: pd.DataFrame, usage: pd.DataFrame, schedule: pd.DataFrame,
           min_usage=24.0, min_hit=93.0, min_games=20, min_team_games=20):
    df = clean_games(games)
    rank = defensive_rankings(df)
    eligible_opponents = set(rank.loc[(rank.DEF_RANK <= 10) & (rank.OPP_GAMES >= min_team_games),'OPP'])
    u = usage.copy()
    if not {'PLAYER_ID','USG_PCT'}.issubset(u.columns):
        raise ValueError('Usage data needs PLAYER_ID and USG_PCT columns.')
    u['USG_PCT'] = pd.to_numeric(u['USG_PCT'], errors='coerce')
    # Some data providers use 0.24, others 24, for 24%.
    if u['USG_PCT'].dropna().median() <= 1:
        u['USG_PCT'] *= 100
    u = u.loc[u.USG_PCT >= min_usage, ['PLAYER_ID','USG_PCT']].drop_duplicates('PLAYER_ID')
    g = df.merge(u, on='PLAYER_ID', how='inner')
    s = schedule.copy()
    if not {'TEAM','OPP','GAME_TIME'}.issubset(s.columns):
        raise ValueError('Schedule needs TEAM, OPP and GAME_TIME columns.')
    s = s[s.OPP.isin(eligible_opponents)].copy()
    # Current team is the most recent log for the player; no player/team trade extrapolation.
    if 'GAME_DATE' in g.columns:
        g = g.sort_values('GAME_DATE')
    current_team = g.groupby('PLAYER_ID').tail(1)[['PLAYER_ID','TEAM_ABBREVIATION']]
    candidates = current_team.merge(s, left_on='TEAM_ABBREVIATION', right_on='TEAM', how='inner')
    outputs = []
    for cand in candidates.itertuples(index=False):
        hist = g[g.PLAYER_ID == cand.PLAYER_ID]
        if len(hist) < min_games:
            continue
        for stat in STATS:
            result = safe_line(hist[stat], min_hit)
            if result is None:
                continue
            outputs.append({'PLAYER': hist.iloc[-1]['PLAYER_NAME'], 'TEAM': cand.TEAM,
                            'OPPONENT': cand.OPP, 'GAME_TIME': cand.GAME_TIME,
                            'USAGE_%': round(float(hist.iloc[-1]['USG_PCT']),1),
                            'DEF_RANK': int(rank.set_index('OPP').loc[cand.OPP,'DEF_RANK']),
                            'STAT': stat, 'OVER_LINE': result['line'],
                            'HITS': result['hits'], 'GAMES': result['games'],
                            'HIT_RATE_%': round(result['hit_rate'],1)})
    cols = ['PLAYER','TEAM','OPPONENT','GAME_TIME','USAGE_%','DEF_RANK','STAT',
            'OVER_LINE','HITS','GAMES','HIT_RATE_%']
    result = pd.DataFrame(outputs, columns=cols)
    if not result.empty:
        result = result.sort_values(['HIT_RATE_%','GAMES','PLAYER'],ascending=[False,False,True])
    return result, rank
