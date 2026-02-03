#!/usr/bin/env python3
"""
IPO Calendar Alert Script
Alerts ONLY IPOs with CONFIRMED valuation >= $1B
"""

import os
import json
import requests
import time
from datetime import datetime, timedelta

# ===================== CONFIG =====================

FINNHUB_API_KEY = os.getenv("FINNHUB_API_KEY")
DISCORD_WEBHOOK = os.getenv("DISCORD_WEBHOOK_IPO_CALENDAR")
HISTORY_FILE = "data/ipo_calendar_history.json"

MIN_IPO_VALUE = 1_000_000_000  # $1B

# ===================== HELPERS =====================

def load_history():
    if not os.path.exists(HISTORY_FILE):
        return {}

    try:
        with open(HISTORY_FILE, "r") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def save_history(history):
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)


def get_ipo_calendar(from_date, to_date):
    url = "https://finnhub.io/api/v1/calendar/ipo"
    params = {
        "from": from_date,
        "to": to_date,
        "token": FINNHUB_API_KEY
    }

    try:
        r = requests.get(url, params=params, timeout=10)
        r.raise_for_status()
        return r.json().get("ipoCalendar", [])
    except Exception as e:
        print(f"Error fetching IPO calendar: {e}")
        return []


def create_ipo_id(ipo):
    return f"{ipo.get('symbol')}_{ipo.get('date')}"


def is_valid_billion_dollar_ipo(ipo):
    """
    STRICT filter:
    - Value must exist
    - Must be numeric
    - Must be >= $1B
    """
    value = ipo.get("totalSharesValue")

    if not isinstance(value, (int, float)):
        return False

    return value >= MIN_IPO_VALUE


def format_value(value):
    return f"${value / 1_000_000_000:.2f}B"


def format_embed(ipo, upcoming=False):
    title = "📅 Upcoming IPO" if upcoming else "🆕 Recent IPO"
    color = 3447003 if upcoming else 3066993

    value = ipo["totalSharesValue"]

    embed = {
        "title": f"{title}: {ipo.get('symbol', 'N/A')}",
        "description": f"**{ipo.get('name', 'Unknown Company')}**",
        "color": color,
        "fields": [
            {"name": "Date", "value": ipo.get("date", "N/A"), "inline": True},
            {"name": "Exchange", "value": ipo.get("exchange", "N/A"), "inline": True},
            {"name": "Valuation", "value": format_value(value), "inline": True},
            {"name": "Status", "value": ipo.get("status", "N/A"), "inline": True},
        ],
        "timestamp": datetime.utcnow().isoformat()
    }

    return embed


def send_discord(embeds):
    if not DISCORD_WEBHOOK:
        print("Discord webhook not set")
        return

    for i in range(0, len(embeds), 10):
        batch = embeds[i:i + 10]
        try:
            r = requests.post(DISCORD_WEBHOOK, json={"embeds": batch}, timeout=10)
            r.raise_for_status()
            print(f"✓ Sent {len(batch)} alerts")
            time.sleep(1)
        except Exception as e:
            print(f"✗ Discord send failed: {e}")

# ===================== MAIN =====================

def main():
    if not FINNHUB_API_KEY:
        print("FINNHUB_API_KEY missing")
        return

    history = load_history()
    today = datetime.utcnow()

    recent_from = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    recent_to = today.strftime("%Y-%m-%d")

    upcoming_from = recent_to
    upcoming_to = (today + timedelta(days=60)).strftime("%Y-%m-%d")

    new_alerts = []

    print(f"Checking recent IPOs {recent_from} → {recent_to}")
    for ipo in get_ipo_calendar(recent_from, recent_to):
        ipo_id = create_ipo_id(ipo)
        if ipo_id in history:
            continue

        if is_valid_billion_dollar_ipo(ipo):
            history[ipo_id] = {"seen": datetime.utcnow().isoformat()}
            new_alerts.append(format_embed(ipo, upcoming=False))
            print(f"✓ {ipo.get('symbol')} — {format_value(ipo['totalSharesValue'])}")

    print(f"\nChecking upcoming IPOs {upcoming_from} → {upcoming_to}")
    for ipo in get_ipo_calendar(upcoming_from, upcoming_to):
        ipo_id = create_ipo_id(ipo)
        if ipo_id in history:
            continue

        if is_valid_billion_dollar_ipo(ipo):
            history[ipo_id] = {"seen": datetime.utcnow().isoformat()}
            new_alerts.append(format_embed(ipo, upcoming=True))
            print(f"✓ {ipo.get('symbol')} — {format_value(ipo['totalSharesValue'])}")

    if new_alerts:
        send_discord(new_alerts)
    else:
        print("No confirmed $1B+ IPOs found")

    # Keep 90 days of history
    cutoff = datetime.utcnow() - timedelta(days=90)
    history = {
        k: v for k, v in history.items()
        if datetime.fromisoformat(v["seen"]) > cutoff
    }

    save_history(history)
    print(f"History size: {len(history)}")


if __name__ == "__main__":
    main()
