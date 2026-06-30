import json
import urllib.request
from functools import cache


FIFA_API = "https://api.fifa.com/api/v3/calendar/matches?idCompetition=17&idSeason=285023&count=500"
ID_COMPETITION = "17"
ID_SEASON = "285023"

TEAM_ALIASES = {
    "South Korea": "Korea Republic",
    "Czech Republic": "Czechia",
    "Bosnia-Herzegovina": "Bosnia and Herzegovina",
    "Ivory Coast": "Côte d'Ivoire",
    "Cape Verde": "Cabo Verde",
    "DR Congo": "Congo DR",
    "United States": "USA",
    "Iran": "IR Iran",
    "Turkey": "Türkiye",
}


def _normalize(name: str) -> str:
    return TEAM_ALIASES.get(name.strip(), name.strip())


def _score_to_result(home_score, away_score) -> str:
    if home_score is None or away_score is None:
        return ""
    try:
        h, a = int(home_score), int(away_score)
    except (ValueError, TypeError):
        return ""
    if h > a:
        return "1"
    if h < a:
        return "2"
    return "x"


@cache
def fetch_all() -> list[dict]:
    req = urllib.request.Request(FIFA_API, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"FIFA API error: {e}")
        return []

    return [
        m for m in data.get("Results", [])
        if m.get("IdCompetition") == ID_COMPETITION
        and m.get("IdSeason") == ID_SEASON
        and m.get("Home") is not None
        and m.get("Away") is not None
    ]


def _get_winner(m: dict) -> str:
    winner_id = m.get("Winner")
    if winner_id is None:
        return ""
    home_id = m.get("Home", {}).get("IdTeam")
    away_id = m.get("Away", {}).get("IdTeam")
    if winner_id == home_id:
        return "home"
    if winner_id == away_id:
        return "away"
    return ""


def get_match(home: str, away: str) -> dict | None:
    home_norm = _normalize(home)
    away_norm = _normalize(away)

    for m in fetch_all():
        api_home = m["Home"]["TeamName"][0]["Description"]
        api_away = m["Away"]["TeamName"][0]["Description"]
        stage_name = m["StageName"][0]["Description"] if m.get("StageName") else ""
        group_name = m["GroupName"][0]["Description"] if m.get("GroupName") else ""
        if api_home == home_norm and api_away == away_norm:
            hs = m["Home"].get("Score")
            aws = m["Away"].get("Score")
            return {
                "home_score": hs,
                "away_score": aws,
                "date": m["Date"],
                "result": _score_to_result(hs, aws),
                "home": api_home,
                "away": api_away,
                "stage_name": stage_name,
                "group_name": group_name,
                "winner": _get_winner(m),
            }
        if api_away == home_norm and api_home == away_norm:
            hs = m["Away"].get("Score")
            aws = m["Home"].get("Score")
            return {
                "home_score": hs,
                "away_score": aws,
                "date": m["Date"],
                "result": _score_to_result(hs, aws),
                "home": api_away,
                "away": api_home,
                "stage_name": stage_name,
                "group_name": group_name,
                "winner": _get_winner(m),
            }
    return None


@cache
def fetch_all_raw() -> list[dict]:
    """Fetch all matches including those with null Home/Away (TBD knockout slots)."""
    req = urllib.request.Request(FIFA_API, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read())
    except Exception as e:
        print(f"FIFA API error: {e}")
        return []
    return data.get("Results", [])


def show_all():
    for m in fetch_all():
        home = m["Home"]["TeamName"][0]["Description"]
        away = m["Away"]["TeamName"][0]["Description"]
        hs = m["Home"].get("Score")
        aws = m["Away"].get("Score")
        r = _score_to_result(hs, aws)
        hs_disp = hs if hs is not None else "?"
        aws_disp = aws if aws is not None else "?"
        print(f"{m['Date']}  {home} {hs_disp}-{aws_disp} {away}  ({r})")
