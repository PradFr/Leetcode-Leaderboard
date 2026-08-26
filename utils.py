import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx

def fetch_leetcode_stats(username: str, retries: int = 3, retry_delay: float = 0.5) -> Optional[Dict[str, Any]]:
    """
    Fetches public LeetCode statistics and most recent submission date.
    Respects rate limits with exponential backoff and retry mechanism.
    """
    if not username:
        return None

    query = """
    query userProfileAndRecent($username: String!) {
      matchedUser(username: $username) {
        profile { ranking }
        submitStats {
          acSubmissionNum { difficulty count }
        }
      }
      recentAcSubmissionList(username: $username, limit: 1) {
        id
        title
        timestamp
      }
    }
    """

    for attempt in range(retries):
        try:
            with httpx.Client(timeout=10) as client:
                r = client.post(
                    "https://leetcode.com/graphql",
                    json={"query": query, "variables": {"username": username.strip()}},
                    headers={
                        "Content-Type": "application/json",
                        "Referer": "https://leetcode.com",
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                    }
                )
                if r.status_code == 200:
                    data = r.json()
                    user = data.get("data", {}).get("matchedUser")
                    if not user:
                        return None
                    
                    ranking = user.get("profile", {}).get("ranking", 0)
                    counts = {
                        item["difficulty"]: item["count"]
                        for item in user.get("submitStats", {}).get("acSubmissionNum", [])
                    }

                    # Parse last accepted submission date if available
                    recent_subs = data.get("data", {}).get("recentAcSubmissionList", [])
                    last_sub_date = None
                    if recent_subs and len(recent_subs) > 0 and recent_subs[0].get("timestamp"):
                        try:
                            ts = int(recent_subs[0]["timestamp"])
                            last_sub_date = datetime.fromtimestamp(ts, tz=timezone.utc)
                        except Exception:
                            last_sub_date = None

                    return {
                        "easy": counts.get("Easy", 0),
                        "medium": counts.get("Medium", 0),
                        "hard": counts.get("Hard", 0),
                        "total": counts.get("All", 0),
                        "ranking": ranking or 0,
                        "last_submission_time": last_sub_date,
                    }
                elif r.status_code in (429, 502, 503, 504):
                    # Rate limit or temporary gateway error, backoff
                    time.sleep(retry_delay * (2 ** attempt))
                else:
                    return None
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(retry_delay * (attempt + 1))
            else:
                print(f"[LeetCode API Error] {username}: {e}")
                return None
    return None


def format_relative_time(dt: Optional[datetime]) -> str:
    """Formats a datetime into accurate human relative time for superadmin (exact days/hours)."""
    if not dt:
        return "Never"
    
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    diff = now - dt
    seconds = int(diff.total_seconds())
    
    if seconds < 0:
        return "Just now"
    if seconds < 60:
        return "Just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins}m ago"
    if seconds < 86400:
        hours = seconds // 3600
        return f"{hours}h ago"
    if seconds < 5184000:  # Up to 60 days, show exact days (e.g. 10d ago, 24d ago, 45d ago)
        days = seconds // 86400
        return f"{days}d ago"
    if seconds < 31536000:
        months = seconds // 2592000
        return f"{months}mo ago"
    years = seconds // 31536000
    return f"{years}y ago"


def get_inactivity_days(dt: Optional[datetime]) -> int:
    """Returns the integer count of days since last active timestamp."""
    if not dt:
        return 999
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    return max(0, diff.days)


def format_bucketed_inactivity(dt: Optional[datetime]) -> str:
    """
    Formats inactivity timestamp into coarse bucketed categories for non-superadmin staff:
    - less than 1 day ago
    - less than 3 days ago
    - less than a week ago
    - less than 2 weeks ago
    - less than 3 weeks ago
    - less than a month ago
    - inactive for more than a month
    """
    if not dt:
        return "Never"

    days = get_inactivity_days(dt)
    if days >= 999:
        return "Never"
    if days < 1:
        return "less than 1 day ago"
    elif days <= 3:
        return "less than 3 days ago"
    elif days <= 7:
        return "less than 1 week ago"
    elif days <= 14:
        return "less than 2 weeks ago"
    elif days <= 21:
        return "less than 3 weeks ago"
    elif days <= 30:
        return "less than 1 month ago"
    else:
        return "inactive for more than a month"


def get_inactivity_status(dt: Optional[datetime], is_superadmin: bool = False) -> dict:
    """
    Returns inactivity status metadata:
    - If is_superadmin: precise relative time ('2d ago', '18d ago') and detailed tooltips.
    - If not superadmin: bucketed categories ('less than 1 day ago', 'less than 3 days ago', 'less than a week ago', 'less than 2 weeks ago', 'less than 3 weeks ago', 'less than a month ago', 'inactive for more than a month').
    """
    days = get_inactivity_days(dt)

    if is_superadmin:
        relative = format_relative_time(dt)
        tooltip = f"Inactive for {days} days" if days > 0 else f"Active ({relative})"
    else:
        relative = format_bucketed_inactivity(dt)
        tooltip = relative

    # 7 Distinct Color & Status Tiers:
    # 1. > 30 days: Critical / Dark Red (🛑)
    if days > 30:
        return {
            "days": days,
            "status": "critical",
            "color": "darkred",
            "badge_class": "dot-dark-red",
            "pill_class": "pill-critical",
            "icon": "🛑",
            "tooltip": tooltip,
            "relative": relative,
            "is_inactive": True
        }
    # 2. 22 - 30 days: Danger / Red (🔴)
    elif days >= 22:
        return {
            "days": days,
            "status": "danger",
            "color": "red",
            "badge_class": "dot-red",
            "pill_class": "pill-danger",
            "icon": "🔴",
            "tooltip": tooltip,
            "relative": relative,
            "is_inactive": True
        }
    # 3. 15 - 21 days: High Warning / Orange (🟠)
    elif days >= 15:
        return {
            "days": days,
            "status": "warning-high",
            "color": "orange",
            "badge_class": "dot-orange",
            "pill_class": "pill-orange",
            "icon": "🟠",
            "tooltip": tooltip,
            "relative": relative,
            "is_inactive": True
        }
    # 4. 8 - 14 days: Warning / Amber (🟡)
    elif days >= 8:
        return {
            "days": days,
            "status": "warning",
            "color": "amber",
            "badge_class": "dot-amber",
            "pill_class": "pill-warning",
            "icon": "🟡",
            "tooltip": tooltip,
            "relative": relative,
            "is_inactive": True
        }
    # 5. 4 - 7 days: Low Warning / Yellow (🟡)
    elif days >= 4:
        return {
            "days": days,
            "status": "warning-low",
            "color": "yellow",
            "badge_class": "dot-yellow",
            "pill_class": "pill-yellow",
            "icon": "🟡",
            "tooltip": tooltip,
            "relative": relative,
            "is_inactive": False
        }
    # 6. 1 - 3 days: Recent / Teal (🟢)
    elif days >= 1:
        return {
            "days": days,
            "status": "recent",
            "color": "teal",
            "badge_class": "dot-teal",
            "pill_class": "pill-teal",
            "icon": "🟢",
            "tooltip": tooltip,
            "relative": relative,
            "is_inactive": False
        }
    # 7. < 1 day (0 days): Active / Green (🟢)
    else:
        return {
            "days": days,
            "status": "active",
            "color": "green",
            "badge_class": "dot-green",
            "pill_class": "pill-green",
            "icon": "🟢",
            "tooltip": tooltip,
            "relative": relative,
            "is_inactive": False
        }


