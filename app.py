import datetime as dt
import requests
import pandas as pd
import streamlit as st
from engine import screen
from alternative_data import get_archive
from current_rosters import get_current_rosters

st.set_page_config(page_title='NBA Prop Research', page_icon='🏀', layout='wide')
st.title('🏀 NBA Daily Prop Research')
st.caption('Historical NBA regular-season screening — not bookmaker odds or future outcome probabilities')

@st.cache_data(ttl=86400, show_spinner='Downloading season game logs…')
def fetch_games(season: str):
    from nba_api.stats.endpoints import playergamelogs
    # Bulk endpoint: one call for the full league, not a call per player.
    df = playergamelogs.PlayerGameLogs(
        season_nullable=season, season_type_nullable='Regular Season',
        timeout=60).get_data_frames()[0]
    if df.empty:
        raise ValueError('NBA game log endpoint returned no data.')
    return df

@st.cache_data(ttl=86400, show_spinner='Downloading usage statistics…')
def fetch_usage(season: str):
    from nba_api.stats.endpoints import leaguedashplayerstats
    df = leaguedashplayerstats.LeagueDashPlayerStats(
        season=season, season_type_all_star='Regular Season',
        measure_type_detailed_defense='Advanced', per_mode_detailed='Totals',
        timeout=60).get_data_frames()[0]
    if 'USG_PCT' not in df.columns:
        raise ValueError('NBA usage endpoint did not include USG_PCT.')
    return df

@st.cache_data(ttl=86400, show_spinner=False)
def fetch_archive(season):
    return get_archive(season)

@st.cache_data(ttl=21600, show_spinner='Loading current NBA rosters…')
def fetch_current_rosters():
    return get_current_rosters()

ESPN_TO_NBA = {'GS':'GSW','NY':'NYK','SA':'SAS','NO':'NOP','UTAH':'UTA', 'WSH':'WAS', 'PHO':'PHX'}

def normalize_team(code: str) -> str:
    code = code.upper()
    return ESPN_TO_NBA.get(code, code)

@st.cache_data(ttl=1800, show_spinner=False)
def fetch_schedule(day_iso: str):
    # ESPN public scoreboard, NBA game date in US local calendar.
    day = dt.date.fromisoformat(day_iso)
    url = 'https://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard'
    r = requests.get(url, params={'dates':day.strftime('%Y%m%d'),'limit':100},timeout=20)
    r.raise_for_status()
    events = r.json().get('events',[])
    rows = []
    for event in events:
        comp = event.get('competitions',[{}])[0]
        opponents = comp.get('competitors',[])
        if len(opponents) != 2:
            continue
        a, b = opponents
        for team, opp in [(a,b),(b,a)]:
            rows.append({'TEAM':normalize_team(team['team']['abbreviation']),
                         'OPP':normalize_team(opp['team']['abbreviation']),
                         'GAME_TIME':event.get('date','')})
    return pd.DataFrame(rows,columns=['TEAM','OPP','GAME_TIME'])

with st.sidebar:
    st.header('Screening settings')
    season = st.selectbox('Historical baseline', ['2025-26','2024-25','2023-24'])
    selected = st.date_input('NBA game date (US calendar)',value=dt.date.today())
    min_usage = st.number_input('Minimum usage %',0.,100.,24.,0.5)
    min_hit = st.number_input('Minimum historical hit rate %',1.,100.,93.,0.5)
    min_games = st.number_input('Minimum player games',1,82,20)
    min_team_games = st.number_input('Minimum opponent team games',1,82,20)
    st.caption('Opponent ranking: 1 = most NBA fantasy points allowed per game. Top 10 = 10 easiest historical defences.')

st.info('Current team assignments come from current ESPN rosters. An asterisk (*) next to a player indicates their current team differs from their final historical-season team.')
st.info('For an early-season screen, the 2025–26 baseline is held fixed until you select a newer season. Team rosters and injuries can change.')
st.write('**Choose a data source:** hosted SportsDataverse ESPN box scores, live NBA endpoints, or your own CSVs. Historical NBA Stats endpoints may time out on cloud hosting.')
mode = st.radio('Input data', ['SportsDataverse ESPN archive (recommended)','Live NBA API','Upload CSVs'], horizontal=True)
st.caption('The ESPN archive computes an **estimated** usage rate from box scores, NOT official NBA USG%. For exact official USG%, upload an official season usage CSV.')
games = usage = None
if mode == 'Upload CSVs':
    c1,c2 = st.columns(2)
    with c1: game_file = st.file_uploader('Season player game logs CSV',type='csv')
    with c2: usage_file = st.file_uploader('Season advanced usage CSV',type='csv')
    if game_file is not None and usage_file is not None:
        games = pd.read_csv(game_file)
        usage = pd.read_csv(usage_file)

if st.button('Run daily screen',type='primary'):
    try:
        if mode == 'SportsDataverse ESPN archive (recommended)':
            with st.spinner('Downloading archived ESPN season box scores…'):
                games,usage = fetch_archive(season)
        elif mode == 'Live NBA API':
            with st.spinner('Fetching NBA data…'):
                games = fetch_games(season)
                usage = fetch_usage(season)
        elif games is None or usage is None:
            st.error('Upload both CSVs first.')
            st.stop()
        schedule = fetch_schedule(selected.isoformat())
        if schedule.empty:
            st.warning('No games found for this NBA date.')
            st.stop()
        # Validate archive is complete before showing opponent rankings or props.
        from engine import clean_games, defensive_rankings
        check = defensive_rankings(clean_games(games))
        if len(check) != 30 or check.OPP_GAMES.min() < 65:
            raise ValueError(f'Season dataset appears incomplete: {len(check)} opponent teams; minimum {int(check.OPP_GAMES.min()) if len(check) else 0} games. Refusing to rank incomplete defences.')
        rosters = fetch_current_rosters()
        results, defenses = screen(games,usage,schedule,min_usage,min_hit,min_games,min_team_games,rosters=rosters)
        st.session_state.results = results
        st.session_state.defenses = defenses
        st.session_state.run_info = (season,selected.isoformat(),len(games))
        st.session_state.source_mode = mode
    except Exception as e:
        st.error(f'Could not finish screen: {e}')
        st.info('If NBA Stats is unavailable, use the two CSV upload fields.')

if 'results' in st.session_state:
    results = st.session_state.results
    defenses = st.session_state.defenses
    season_used, date_used, rows = st.session_state.run_info
    st.subheader(f'Results · NBA game date {date_used}')
    if st.session_state.get('source_mode','').startswith('SportsDataverse'):
        st.warning('Usage % is ESTIMATED using ESPN box scores; current teams come from the latest ESPN rosters.')
    st.caption('***** Team changed since the historical baseline; PREVIOUS_TEAM shows their final team from that season. Roster status does not guarantee availability to play.')
    m1,m2,m3 = st.columns(3)
    m1.metric('Qualified props',len(results))
    m2.metric('Qualified players',results.PLAYER.nunique() if len(results) else 0)
    m3.metric('Historical player-game rows',f'{rows:,}')
    if results.empty:
        st.warning('No qualifying players/props found with the current rules.')
    else:
        st.dataframe(results,hide_index=True,use_container_width=True)
        st.download_button('Download qualified props CSV',results.to_csv(index=False),
                           file_name=f'nba_props_{date_used}.csv',mime='text/csv')
    with st.expander('Opponent fantasy points allowed — full rankings'):
        st.dataframe(defenses,hide_index=True,use_container_width=True)
        st.download_button('Download defense rankings CSV',defenses.to_csv(index=False),
                           file_name=f'nba_defenses_{season_used}.csv',mime='text/csv')
    st.caption('Hit rate denominator = all available regular-season games played by each player; no injury or minutes filters. Lines use 0.5 increments and strictly exceeded thresholds. Fantasy scoring comes from NBA_FANTASY_PTS when available.')
