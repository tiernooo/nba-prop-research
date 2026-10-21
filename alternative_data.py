"""SportsDataverse ESPN NBA archived player box scores (GitHub release asset)."""
import io
import requests
import pandas as pd

TEAM_FIX = {'GS':'GSW', 'NY':'NYK', 'SA':'SAS', 'NO':'NOP', 'UTAH':'UTA', 'WSH':'WAS', 'PHO':'PHX', 'BKN':'BKN'}
def norm(s):
    s = str(s).upper().strip()
    return TEAM_FIX.get(s,s)

def get_archive(season):
    ending_year = int(season[:4]) + 1
    url = ("https://github.com/sportsdataverse/sportsdataverse-data/releases/download/"
           f"espn_nba_player_boxscores/player_box_{ending_year}.rds")
    response = requests.get(url, timeout=(15,90), headers={'User-Agent':'NBA-Research/1.0'})
    response.raise_for_status()
    if len(response.content) < 10000:
        raise ValueError('Season archive was unexpectedly small or empty.')
    try:
        import pyreadr
        raw = pyreadr.read_r(io.BytesIO(response.content))
    except Exception:
        # pyreadr requires a local file path in many versions
        import os, tempfile, pyreadr
        with tempfile.NamedTemporaryFile(suffix='.rds',delete=False) as f:
            f.write(response.content)
            path=f.name
        try:
            raw=pyreadr.read_r(path)
        finally:
            os.unlink(path)
    frame=next(iter(raw.values()))
    return normalize_archive(frame)

def normalize_archive(raw):
    d=raw.copy()
    if 'season_type' in d:
        d=d[d['season_type'].astype(str).isin(['2','2.0','Regular Season'])]
    if 'did_not_play' in d:
        d=d[~d.did_not_play.fillna(False).astype(bool)]
    columns={'athlete_id':'PLAYER_ID','athlete_display_name':'PLAYER_NAME',
             'team_abbreviation':'TEAM_ABBREVIATION','game_id':'GAME_ID',
             'game_date':'GAME_DATE','opponent_team_abbreviation':'OPP',
             'points':'PTS','rebounds':'REB','assists':'AST','steals':'STL',
             'blocks':'BLK','turnovers':'TOV','field_goals_attempted':'FGA',
             'free_throws_attempted':'FTA','minutes':'MIN'}
    missing=set(columns).difference(d.columns)
    if missing: raise ValueError('Archived box-score columns missing: '+', '.join(sorted(missing)))
    d=d.rename(columns=columns)
    d['TEAM_ABBREVIATION']=d['TEAM_ABBREVIATION'].map(norm)
    d['OPP']=d['OPP'].map(norm)
    for c in ['PTS','REB','AST','STL','BLK','TOV','FGA','FTA']:
        d[c]=pd.to_numeric(d[c],errors='coerce')
    def as_minutes(x):
        if ':' in str(x):
            a,b=str(x).split(':',1)
            try: return float(a)+float(b)/60
            except ValueError: return float('nan')
        return pd.to_numeric(x,errors='coerce')
    d['MIN']=d['MIN'].map(as_minutes)
    d=d.dropna(subset=['PLAYER_ID','GAME_ID','PTS','REB','AST','STL','BLK','TOV','FGA','FTA','MIN'])
    d=d[d.MIN>0]
    d['MATCHUP']=d['TEAM_ABBREVIATION']+' vs. '+d['OPP']
    d=d.drop_duplicates(['PLAYER_ID','GAME_ID'])
    # Approximate box-score USG% formula; does NOT replace official play-by-play USG%.
    # Player share of possessions, minutes-adjusted using full team box-score totals.
    d['PLAYER_POSS']=d.FGA+0.44*d.FTA+d.TOV
    teams=(d.groupby(['GAME_ID','TEAM_ABBREVIATION'],as_index=False)
             .agg(TEAM_POSS=('PLAYER_POSS','sum'),TEAM_MIN=('MIN','sum')))
    d=d.merge(teams,on=['GAME_ID','TEAM_ABBREVIATION'],how='left')
    d['EST_PLAYER_POSS_SHARE']=d['PLAYER_POSS']*d['TEAM_MIN']/(d['MIN']*d['TEAM_POSS'])*100/5
    # One per game estimated usage; weigh season average by minutes and team totals, not a simple unweighted mean.
    usage=d.assign(W_USAGE=d.EST_PLAYER_POSS_SHARE*d.MIN).groupby('PLAYER_ID',as_index=False).agg(W_USAGE=('W_USAGE','sum'),MIN=('MIN','sum'))
    usage['USG_PCT']=usage.W_USAGE/usage.MIN
    return d,usage[['PLAYER_ID','USG_PCT']]
