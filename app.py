import streamlit as st
import pandas as pd
import plotly.express as px
from pathlib import Path
import re

st.set_page_config(
    page_title="T20 World Cup Cricket Analytics",
    page_icon="🏏",
    layout="wide"
)

DATA_FILE = Path(__file__).parent / "data" / "T20_Cricket_Analytics.xlsx"

@st.cache_data
def load_workbook(path):
    return pd.read_excel(path, sheet_name=None)

st.markdown("""
<style>
.stApp {background: #0b1220; color: #f8fafc;}
[data-testid="stMetric"] {
    background: #172338;
    border: 1px solid #26364f;
    padding: 16px;
    border-radius: 12px;
}
.player-card {
    background: #172338;
    border: 1px solid #26364f;
    border-radius: 12px;
    padding: 10px;
    text-align: center;
}
</style>
""", unsafe_allow_html=True)

st.sidebar.title("🏏 T20 ANALYTICS")
page = st.sidebar.radio(
    "Navigate",
    ["Overview", "Batting", "Bowling", "Best Playing XI", "Player Explorer"]
)

if not DATA_FILE.exists():
    st.error("Workbook not found. Keep T20_Cricket_Analytics.xlsx inside the data folder.")
    st.stop()

try:
    sheets = load_workbook(DATA_FILE)
except Exception as exc:
    st.error(f"Could not read Excel workbook: {exc}")
    st.stop()

batting = sheets.get("Batting_Analysis", pd.DataFrame()).copy()
bowling = sheets.get("Bowling_Analysis", pd.DataFrame()).copy()
players = sheets.get("Player_Information", pd.DataFrame()).copy()
best_xi = sheets.get("Final_Best_XI", pd.DataFrame()).copy()

def clean_name(value):
    if pd.isna(value):
        return ""
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

def canonical_player_name(value):
    """Normalize tournament name variants without merging different players."""
    if pd.isna(value):
        return ""
    name = re.sub(r"\s+", " ", str(value)).strip()
    # Remove common role/captain annotations, not parts of actual names.
    name = re.sub(r"\s*\((?:c|wk|vc)\)\s*$", "", name, flags=re.IGNORECASE).strip()
    name = re.sub(r"\s+(?:WK|C|VC)\s*$", "", name, flags=re.IGNORECASE).strip()
    aliases = {
        "kohli": "Virat Kohli",
        "virat kohli": "Virat Kohli",
        "rohit": "Rohit Sharma",
        "rohit sharma": "Rohit Sharma",
    }
    return aliases.get(name.casefold(), name)

def aggregate_player_stats(frame, kind):
    """Combine duplicate name variants and recalculate rate statistics."""
    if frame.empty or "player_name" not in frame.columns:
        return frame
    data = frame.copy()
    data["player_name"] = data["player_name"].map(canonical_player_name)
    numeric = [c for c in data.columns if c not in ("player_name", "team")]
    for col in numeric:
        data[col] = pd.to_numeric(data[col], errors="coerce")
    agg = {col: "sum" for col in numeric}
    if "team" in data.columns:
        agg["team"] = "first"
    result = data.groupby("player_name", as_index=False).agg(agg)
    if kind == "batting" and {"total_runs", "total_balls"}.issubset(result.columns):
        result["strike_rate"] = (
            result["total_runs"] / result["total_balls"].replace(0, pd.NA) * 100
        ).fillna(0)
    if kind == "bowling" and {"total_runs_conceded", "total_balls"}.issubset(result.columns):
        result["economy"] = (
            result["total_runs_conceded"] / (result["total_balls"].replace(0, pd.NA) / 6)
        ).fillna(0)
    return result

# The source workbook contains split name variants such as "Kohli" and
# "Virat Kohli", and "Rohit (c)" and "Rohit Sharma (c)".
batting = aggregate_player_stats(batting, "batting")
bowling = aggregate_player_stats(bowling, "bowling")

# Build photo lookup from the Player_Information sheet.
# Store both the original and canonical keys so aliases still find the right image.
photo_lookup = {}
if {"player_name", "image"}.issubset(players.columns):
    for _, player_row in players.dropna(subset=["image"]).iterrows():
        image_url = str(player_row["image"]).strip()
        if not image_url:
            continue
        original_key = clean_name(player_row["player_name"])
        canonical_key = clean_name(canonical_player_name(player_row["player_name"]))
        if original_key:
            photo_lookup.setdefault(original_key, image_url)
        if canonical_key:
            photo_lookup.setdefault(canonical_key, image_url)

def get_photo(name):
    return photo_lookup.get(clean_name(canonical_player_name(name)), None)

@st.dialog("🏏 Player Career Profile", width="large")
def player_profile_popup(name):
    """Show the player details and statistics available in the supplied workbook."""
    key = clean_name(name)
    p_row = players[players["player_name"].astype(str).map(lambda x: clean_name(canonical_player_name(x))) == key] if "player_name" in players else pd.DataFrame()
    b_row = batting[batting["player_name"].astype(str).map(lambda x: clean_name(canonical_player_name(x))) == key] if "player_name" in batting else pd.DataFrame()
    w_row = bowling[bowling["player_name"].astype(str).map(lambda x: clean_name(canonical_player_name(x))) == key] if "player_name" in bowling else pd.DataFrame()

    left, right = st.columns([1, 2])
    with left:
        photo = get_photo(name)
        if photo:
            st.image(photo, use_container_width=True)
        else:
            st.markdown("## 🏏")
    with right:
        st.subheader(name)
        if not p_row.empty:
            info = p_row.iloc[0]
            st.write(f"**Team:** {info.get('team', 'N/A')}")
            st.write(f"**Role:** {info.get('role_clean', info.get('role', 'N/A'))}")
            st.write(f"**Batting style:** {info.get('batting_style_clean', info.get('batting_style', 'N/A'))}")
            st.write(f"**Bowling style:** {info.get('bowling_style', 'N/A')}")

    st.divider()
    st.caption("Statistics below come from the tournament workbook currently connected to this dashboard. They are not full-career totals.")
    if not b_row.empty:
        bat = b_row.iloc[0]
        st.markdown("#### 🏏 Batting (available tournament data)")
        m = st.columns(4)
        for col, label, field in zip(m, ["Runs", "Strike rate", "Innings", "Balls faced"], ["total_runs", "strike_rate", "innings", "total_balls"]):
            val = bat.get(field, "N/A")
            col.metric(label, f"{val:,.2f}" if isinstance(val, (int, float)) and pd.notna(val) else str(val))
    if not w_row.empty:
        bowl = w_row.iloc[0]
        st.markdown("#### 🎯 Bowling (available tournament data)")
        m = st.columns(4)
        for col, label, field in zip(m, ["Wickets", "Economy", "Matches", "Balls bowled"], ["total_wickets", "economy", "matches", "total_balls"]):
            val = bowl.get(field, "N/A")
            col.metric(label, f"{val:,.2f}" if isinstance(val, (int, float)) and pd.notna(val) else str(val))
    if b_row.empty and w_row.empty:
        st.info("No batting or bowling record for this player was found in the current workbook.")
    st.info("To show complete T20 career stats and recalculate an all-time Best XI, we need a separate all-career T20 dataset. The current workbook contains tournament analysis only.")

def show_player_cards(df, name_col, subtitle_col=None, max_cards=10, image_width=140):
    """Show player photos and names in a responsive row of Streamlit columns."""
    if df.empty or name_col not in df.columns:
        return
    subset = df.head(max_cards)
    cols_per_row = 5
    for start in range(0, len(subset), cols_per_row):
        row = subset.iloc[start:start + cols_per_row]
        cols = st.columns(cols_per_row)
        for col, (_, player) in zip(cols, row.iterrows()):
            name = str(player.get(name_col, "Unknown"))
            photo = get_photo(name)
            with col:
                if photo:
                    try:
                        st.image(photo, width=image_width)
                    except Exception:
                        st.markdown("🏏")
                else:
                    st.markdown("🏏")
                st.markdown(f"**{name}**")
                if subtitle_col and subtitle_col in player.index and pd.notna(player[subtitle_col]):
                    st.caption(str(player[subtitle_col]))
                if st.button("View profile", key=f"profile_{clean_name(name)}_{start}", use_container_width=True):
                    player_profile_popup(name)

def metric_sum(df, col):
    if col not in df.columns:
        return 0
    return pd.to_numeric(df[col], errors="coerce").fillna(0).sum()

if page == "Overview":
    st.title("🏏 T20 World Cup Cricket Analytics")
    st.caption("Tournament insights powered by Python, Pandas, Streamlit and Plotly")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Players", f"{players['player_id'].nunique():,}" if "player_id" in players else f"{len(players):,}")
    c2.metric("Runs in batting summary", f"{metric_sum(batting, 'total_runs'):,.0f}")
    c3.metric("Wickets in bowling summary", f"{metric_sum(bowling, 'total_wickets'):,.0f}")
    c4.metric("Selected Best XI", f"{len(best_xi):,}")

    left, right = st.columns(2)
    with left:
        st.subheader("Top 10 Run Scorers")
        if {"player_name", "total_runs"}.issubset(batting.columns):
            top = batting.nlargest(10, "total_runs").sort_values("total_runs")
            fig = px.bar(top, x="total_runs", y="player_name", orientation="h",
                         color="total_runs", title="Runs by player")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Required batting columns are unavailable.")
    with right:
        st.subheader("Top 10 Wicket Takers")
        if {"player_name", "total_wickets"}.issubset(bowling.columns):
            top = bowling.nlargest(10, "total_wickets").sort_values("total_wickets")
            fig = px.bar(top, x="total_wickets", y="player_name", orientation="h",
                         color="total_wickets", title="Wickets by player")
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Required bowling columns are unavailable.")

    st.divider()
    st.subheader("⭐ Tournament Star Players")
    star_players = batting.nlargest(5, "total_runs") if {"player_name", "total_runs"}.issubset(batting.columns) else pd.DataFrame()
    show_player_cards(star_players, "player_name", max_cards=5)

elif page == "Batting":
    st.title("🏏 Batting Analysis")
    if batting.empty:
        st.warning("Batting sheet is empty.")
        st.stop()
    view = batting.copy()
    if "team" in view.columns:
        teams = ["All teams"] + sorted(view["team"].dropna().astype(str).unique().tolist())
        team = st.selectbox("Filter by team", teams)
        if team != "All teams":
            view = view[view["team"].astype(str) == team]
    if {"player_name", "total_runs"}.issubset(view.columns):
        top = view.nlargest(10, "total_runs").sort_values("total_runs")
        fig = px.bar(top, x="total_runs", y="player_name", orientation="h",
                     color="total_runs", title="Top 10 batsmen")
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("📸 Top Batsmen")
        show_player_cards(top.sort_values("total_runs", ascending=False), "player_name", max_cards=10)
    if {"total_runs", "strike_rate"}.issubset(view.columns):
        fig = px.scatter(view, x="total_runs", y="strike_rate",
                         hover_name="player_name" if "player_name" in view else None,
                         color="team" if "team" in view else None,
                         title="Runs vs strike rate")
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("Batting records")
    st.dataframe(view, use_container_width=True, hide_index=True)

elif page == "Bowling":
    st.title("🎯 Bowling Analysis")
    if bowling.empty:
        st.warning("Bowling sheet is empty.")
        st.stop()
    view = bowling.copy()
    if "team" in view.columns:
        teams = ["All teams"] + sorted(view["team"].dropna().astype(str).unique().tolist())
        team = st.selectbox("Filter by team", teams)
        if team != "All teams":
            view = view[view["team"].astype(str) == team]
    if {"player_name", "total_wickets"}.issubset(view.columns):
        top = view.nlargest(10, "total_wickets").sort_values("total_wickets")
        fig = px.bar(top, x="total_wickets", y="player_name", orientation="h",
                     color="total_wickets", title="Top 10 wicket takers")
        st.plotly_chart(fig, use_container_width=True)
        st.subheader("📸 Top Bowlers")
        show_player_cards(top.sort_values("total_wickets", ascending=False), "player_name", max_cards=10)
    if {"economy", "total_wickets"}.issubset(view.columns):
        fig = px.scatter(view, x="economy", y="total_wickets",
                         hover_name="player_name" if "player_name" in view else None,
                         color="team" if "team" in view else None,
                         title="Economy vs wickets")
        st.plotly_chart(fig, use_container_width=True)
    st.subheader("Bowling records")
    st.dataframe(view, use_container_width=True, hide_index=True)

elif page == "Best Playing XI":
    st.title("🏆 Final Best Playing XI")
    if best_xi.empty:
        st.warning("Best XI sheet is empty.")
    else:
        # The workbook contains the selected XI and player metadata.
        xi_name_col = "player_name" if "player_name" in best_xi.columns else "player_name_x"
        st.subheader("📸 Your Selected 11")
        show_player_cards(best_xi, xi_name_col, "final_xi_role" if "final_xi_role" in best_xi.columns else None,
                          max_cards=11, image_width=150)
        display_cols = [c for c in [
            "player_name", "player_name_x", "team", "team_x",
            "final_xi_role", "dashboard_role", "total_runs",
            "strike_rate", "total_wickets", "economy", "overall_impact"
        ] if c in best_xi.columns]
        st.subheader("Best XI performance")
        st.dataframe(best_xi[display_cols], use_container_width=True, hide_index=True)
        st.caption("This XI is the selection already present in your supplied tournament workbook; it is not yet an all-time career-based XI.")
        st.warning("The workbook does not contain complete career statistics. Upload an all-time T20 career dataset before we replace this with a genuine career-based Best XI.")

elif page == "Player Explorer":
    st.title("🔎 Player Explorer")
    if players.empty:
        st.warning("Player information sheet is empty.")
    elif "player_name" in players.columns:
        query = st.text_input("Search player")
        result = players[players["player_name"].astype(str).str.contains(query, case=False, na=False)]
        st.subheader(f"Player profiles ({len(result)})")
        if result.empty:
            st.info("No player found. Try another name.")
        else:
            for start in range(0, len(result), 3):
                row = result.iloc[start:start + 3]
                cols = st.columns(3)
                for col, (_, player) in zip(cols, row.iterrows()):
                    with col:
                        photo = player.get("image")
                        if pd.notna(photo) and str(photo).strip():
                            try:
                                st.image(str(photo), use_container_width=True)
                            except Exception:
                                st.markdown("🏏")
                        else:
                            st.markdown("🏏")
                        st.markdown(f"### {player.get('player_name', 'Unknown')}")
                        st.write(f"**Team:** {player.get('team', 'N/A')}")
                        st.write(f"**Role:** {player.get('role_clean', player.get('role', 'N/A'))}")
                        st.write(f"**Batting:** {player.get('batting_style_clean', player.get('batting_style', 'N/A'))}")
                        st.write(f"**Bowling:** {player.get('bowling_style', 'N/A')}")
                        if st.button("View career profile", key=f"explorer_{clean_name(player.get('player_name', 'Unknown'))}", use_container_width=True):
                            player_profile_popup(str(player.get('player_name', 'Unknown')))
    else:
        st.dataframe(players, use_container_width=True, hide_index=True)

st.divider()
st.caption("T20 World Cup Cricket Analytics | College project and portfolio")
