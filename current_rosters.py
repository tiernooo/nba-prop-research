"""Resolve players to current ESPN NBA rosters. Fail closed if roster coverage is incomplete."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import re
import requests
import pandas as pd

BASE = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba'
FIX = {'GS':'GSW','NY':'NYK','SA':'SAS','NO':'NOP','UTAH':'UTA','WSH':'WAS','PHO':'PHX'}

def clean_name(value):
    return re.sub(r'[^a-z0-9]', '', str(value).casefold())

def get_current_rosters():
    r = requests.get(f'{BASE}/teams', params={'limit':100}, timeout=25)
    r.raise_for_status()
    leagues = r.json().get('sports',[{}])[0].get('leagues',[{}])
    teams = leagues[0].get('teams',[]) if leagues else []
    teams = [t.get('team',{}) for t in teams]
    teams = [t for t in teams if t.get('id') and t.get('abbreviation')]
    if len(set(t['id'] for t in teams)) != 30:
        raise ValueError(f'Current ESPN team directory returned {len(teams)} teams, not 30; refusing to guess current rosters.')

    def load(team):
        response = requests.get(f"{BASE}/teams/{team['id']}/roster",timeout=25)
        response.raise_for_status()
        payload = response.json()
        athletes = payload.get('athletes',[])
        if not athletes:
            raise ValueError(f"Missing current roster for {team['abbreviation']}")
        entries = []
        for item in athletes:
            for athlete in item.get('items',[item]):
                if athlete.get('id') and athlete.get('displayName'):
                    entries.append({'ESPN_ID':str(athlete['id']), 'NAME_KEY':clean_name(athlete['displayName']),
                                    'CURRENT_TEAM':FIX.get(team['abbreviation'],team['abbreviation'])})
        return entries
    rows = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for future in as_completed([pool.submit(load,t) for t in teams]):
            rows.extend(future.result())
    frame = pd.DataFrame(rows)
    if frame.empty:
        raise ValueError('Current roster source returned no players.')
    # Only use unambiguous player ids; names only for NBA API IDs, which differ from ESPN.
    return frame.drop_duplicates()
