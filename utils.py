import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any
import httpx
import re

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


# -----------------------------------------------------------------------------
# Test Results Aggregation Helper
# -----------------------------------------------------------------------------

def _find_reg_col(cols):
    for c in cols:
        cl = c.lower().replace(' ', '').replace('_', '').replace('.', '')
        if any(k in cl for k in ['regno', 'registerno', 'registrationno', 'registrationnumber', 'registernumber', 'reg', 'roll']):
            return c
    return None


def _find_name_col(cols):
    for c in cols:
        cl = c.lower().replace(' ', '').replace('_', '').replace('.', '')
        if 'name' in cl and 'test' not in cl and 'task' not in cl and 'dept' not in cl:
            return c
    return None


def _find_score_or_pct_col(cols):
    # 1. Look for explicit percentage column
    for c in cols:
        cl = c.lower()
        if 'percentage' in cl or '%' in cl:
            return c, True
    # 2. Look for total score column
    for c in cols:
        cl = c.lower()
        if 'total' in cl and 'attendance' not in cl and 'present' not in cl:
            return c, False
    # 3. Look for score / marks / result column
    for c in cols:
        cl = c.lower()
        if any(k in cl for k in ['score', 'mark', 'result', 'points', 'grade']):
            return c, False
    # 4. Fallback: last column if present
    if cols:
        return cols[-1], False
    return None, False


def _parse_num(val):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).strip().replace('%', '').replace(',', '')
    try:
        return float(s)
    except Exception:
        return None


def _normalize_reg(reg):
    if not reg:
        return ""
    r = str(reg).strip().upper()
    r = re.sub(r'[\s\-_]', '', r)
    # Correct letter 'O' mistyped instead of digit '0' in trailing roll numbers (e.g. 25BECYO17 -> 25BECY017)
    r = re.sub(r'O(\d{1,3})$', r'0\1', r)
    # Normalize section suffix like '094A' -> '094'
    r = re.sub(r'(\d{2,3})[A-Z]$', r'\1', r)
    return r


def _clean_name(name):
    if not name:
        return ""
    return re.sub(r'[^a-zA-Z0-9]', '', str(name).lower())


def calculate_aggregate_test_results(tests, class_students=None):
    """
    Computes an aggregate matrix across all given tests, mapped by student Register Number.
    Handles typos like letter 'O' vs digit '0', whitespace, and matches by student name fallback.
    Calculates overall average percentage across all tests in the class (penalizing absences).
    """
    if not tests:
        return {"tests": [], "rows": [], "total_students": 0}

    # Sort tests by upload date ascending so Test 1, Test 2... are ordered chronologically
    sorted_tests = sorted(tests, key=lambda t: t.upload_date if t.upload_date else "")

    student_map = {}
    reg_to_canonical = {}
    name_to_canonical = {}

    # Seed with class students if provided
    if class_students:
        for s in class_students:
            raw_reg = s.register_number or ""
            norm_reg = _normalize_reg(raw_reg)
            c_name = _clean_name(s.display_name or s.leetcode_username)
            canonical_key = norm_reg if norm_reg else c_name
            if not canonical_key:
                continue

            student_map[canonical_key] = {
                "reg_no": s.register_number or norm_reg,
                "name": s.display_name or s.leetcode_username or canonical_key,
                "scores": {}
            }
            if norm_reg:
                reg_to_canonical[norm_reg] = canonical_key
            if c_name:
                name_to_canonical[c_name] = canonical_key

    for t in sorted_tests:
        tid = str(t.id)
        cols = t.columns or []
        rows_data = t.data or []

        reg_c = _find_reg_col(cols)
        name_c = _find_name_col(cols)
        score_c, is_pct = _find_score_or_pct_col(cols)

        max_val = 100.0
        if not is_pct and score_c:
            numeric_vals = [_parse_num(r.get(score_c)) for r in rows_data if _parse_num(r.get(score_c)) is not None]
            if numeric_vals:
                m = max(numeric_vals)
                if m > 0 and m != 100.0:
                    max_val = m

        for r in rows_data:
            raw_reg = r.get(reg_c) if reg_c else None
            raw_name = r.get(name_c) if name_c else ""
            norm_reg = _normalize_reg(raw_reg)
            c_name = _clean_name(raw_name)

            if not norm_reg and not c_name:
                continue

            # Robust canonical student resolution:
            # 1. Match by normalized register number
            # 2. Match by clean student name as fallback
            canonical = None
            if norm_reg and norm_reg in reg_to_canonical:
                canonical = reg_to_canonical[norm_reg]
            elif c_name and c_name in name_to_canonical:
                canonical = name_to_canonical[c_name]
            elif norm_reg:
                canonical = norm_reg
                student_map[canonical] = {
                    "reg_no": str(raw_reg).strip().upper() if raw_reg else norm_reg,
                    "name": str(raw_name).strip() if raw_name else norm_reg,
                    "scores": {}
                }
                reg_to_canonical[norm_reg] = canonical
                if c_name:
                    name_to_canonical[c_name] = canonical
            elif c_name:
                canonical = c_name
                student_map[canonical] = {
                    "reg_no": str(raw_reg).strip().upper() if raw_reg else "",
                    "name": str(raw_name).strip(),
                    "scores": {}
                }
                name_to_canonical[c_name] = canonical

            raw_score = _parse_num(r.get(score_c)) if score_c else None

            pct = None
            if raw_score is not None:
                if is_pct:
                    pct = round(min(100.0, max(0.0, raw_score)), 2)
                else:
                    pct = round(min(100.0, max(0.0, (raw_score / max_val) * 100.0)), 2)

            if pct is not None and canonical:
                student_map[canonical]["scores"][tid] = pct

    total_test_count = len(sorted_tests)
    aggregated_rows = []

    for k, data in student_map.items():
        scores = data["scores"]
        attended = len(scores)
        # Calculate overall percentage for the whole (all tests uploaded):
        # Absences contribute 0% and reduce the overall average
        total_score = sum(scores.values())
        avg = round(total_score / total_test_count, 2) if total_test_count > 0 else 0.0

        aggregated_rows.append({
            "reg_no": data["reg_no"],
            "name": data["name"],
            "scores": scores,
            "average": avg,
            "attended": attended,
            "total_tests": total_test_count,
        })

    # Sort students: highest average score first, then most attended tests, then alphabetically by name
    aggregated_rows.sort(key=lambda x: (x["average"], x["attended"], x["name"]), reverse=True)

    for i, r in enumerate(aggregated_rows):
        r["rank"] = i + 1

    return {
        "tests": [{"id": str(t.id), "name": t.test_name} for t in sorted_tests],
        "rows": aggregated_rows,
        "total_students": len(aggregated_rows),
    }



