import time
import pandas as pd
import streamlit as st
from nba_api.stats.static import teams
from nba_api.stats.endpoints import leaguegamefinder, playbyplayv3

# --- 1. Setup and Fetch Team Data ---
st.set_page_config(page_title="NBA Playoff Play-by-Play Fetcher", page_icon="🏀")

# Get all 30 NBA teams from the API's static dictionary
nba_teams = teams.get_teams()
team_names = sorted([team['full_name'] for team in nba_teams])
team_dict = {team['full_name']: team for team in nba_teams}

st.title("🏀 NBA Playoff Data Fetcher")
st.markdown("Select a season and a playoff matchup to instantly download the raw play-by-play data.")

# --- 2. User Input (Dropdowns) ---
st.subheader("Select Matchup")

col1, col2, col3 = st.columns(3)

with col1:
    # A list of recent seasons (format must be YYYY-YY)
    season_options = [f"{year}-{str(year+1)[-2:]}" for year in range(2025, 2010, -1)]
    selected_season = st.selectbox("Season:", season_options)

with col2:
    default_team_a = team_names.index("San Antonio Spurs") if "San Antonio Spurs" in team_names else 0
    team_a_name = st.selectbox("Team 1:", team_names, index=default_team_a)

with col3:
    default_team_b = team_names.index("Oklahoma City Thunder") if "Oklahoma City Thunder" in team_names else 1
    team_b_name = st.selectbox("Team 2:", team_names, index=default_team_b)


# --- 3. Search and Fetch Logic ---
if st.button("Search & Fetch Data"):
    
    if team_a_name == team_b_name:
        st.error("Please select two different teams!")
        st.stop()
        
    team_a = team_dict[team_a_name]
    team_b = team_dict[team_b_name]
    
    # Using Streamlit's modern status container context manager
    with st.status("Connecting to NBA Servers...", expanded=True) as status:
        
        status.update(label=f"Searching for {team_a['abbreviation']} vs {team_b['abbreviation']} ({selected_season})...")
        
        # A. Search for the games
        try:
            gamefinder = leaguegamefinder.LeagueGameFinder(
                team_id_nullable=team_a['id'],
                season_nullable=selected_season,
                season_type_nullable='Playoffs'
            )
            
            all_games = gamefinder.get_data_frames()
            
            if not all_games or len(all_games[0]) == 0:
                st.error(f"No playoff games found for the {team_a_name} in {selected_season}.")
                st.stop()
                
            playoff_games = all_games[0]
            
            # Filter for the specific opponent
            series_games = playoff_games[playoff_games['MATCHUP'].str.contains(team_b['abbreviation'])]
            
            if series_games.empty:
                st.error(f"The {team_a_name} and {team_b_name} did not play each other in the {selected_season} playoffs.")
                st.stop()
                
            # Sort games chronologically
            series_games = series_games.sort_values('GAME_DATE')
            game_ids = series_games['GAME_ID'].unique().tolist()
            
            status.update(label=f"Match found! Fetching plays for a {len(game_ids)}-game series...")
            
        except Exception as e:
            st.error("The NBA database rejected the search request. Try again in a moment.")
            st.stop()

        # B. Fetch the Play-by-Play using the found IDs
        all_plays = []

        for i, game_id in enumerate(game_ids):
            status.update(label=f"Downloading Game {i+1} of {len(game_ids)} (ID: {game_id})...")
            
            try:
                pbp = playbyplayv3.PlayByPlayV3(game_id=game_id)
                raw_dict = pbp.get_dict()
                plays_list = raw_dict['game']['actions']
                
                df = pd.DataFrame(plays_list)
                df['GAME_ID'] = game_id
                all_plays.append(df)
                
                time.sleep(1) # API breathing room
                
            except Exception as e:
                st.warning(f"Could not download Game {i+1}. Skipping...")

        # C. Combine and Provide the Download
        if len(all_plays) > 0:
            status.update(label="Processing data and generating file...", state="running")
            series_pbp_df = pd.concat(all_plays, ignore_index=True)
            csv_data = series_pbp_df.to_csv(index=False).encode('utf-8')
            
            # Close out the status box cleanly
            status.update(label="Data successfully downloaded!", state="complete", expanded=False)
            
            st.success(f"Captured {len(series_pbp_df)} total plays!")
            
            file_name = f'nba_pbp_{team_a["abbreviation"]}_vs_{team_b["abbreviation"]}_{selected_season}.csv'
            
            st.download_button(
                label="⬇️ Download Play-by-Play CSV",
                data=csv_data,
                file_name=file_name,
                mime='text/csv',
            )
        else:
            status.update(label="Failed to fetch any data.", state="error")