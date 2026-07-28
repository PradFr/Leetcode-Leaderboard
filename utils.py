import httpx

def fetch_leetcode_stats(username: str) -> dict | None:
    query = """
    query userProfile($username: String!) {
      matchedUser(username: $username) {
        profile { ranking }
        submitStats {
          acSubmissionNum { difficulty count }
        }
      }
    }
    """
    try:
        r = httpx.post(
            "https://leetcode.com/graphql",
            json={"query": query, "variables": {"username": username}},
            headers={"Content-Type": "application/json", "Referer": "https://leetcode.com"},
            timeout=10,
        )
        data = r.json()
        user = data.get("data", {}).get("matchedUser")
        if not user:
            return None
        ranking = user.get("profile", {}).get("ranking", 0)
        counts = {item["difficulty"]: item["count"]
                  for item in user.get("submitStats", {}).get("acSubmissionNum", [])}
        return {
            "easy": counts.get("Easy", 0),
            "medium": counts.get("Medium", 0),
            "hard": counts.get("Hard", 0),
            "total": counts.get("All", 0),
            "ranking": ranking or 0,
        }
    except Exception:
        return None
