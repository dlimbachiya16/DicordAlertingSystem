#!/usr/bin/env python3
"""
EPS Surprises Alert Script - TIME-BASED VERSION
Monitors earnings surprises and sends alerts to Discord

KEY IMPROVEMENT:
Instead of marking earnings as "seen forever", this version uses a time window.
It will re-check earnings that were added to Finnhub's API within the last 48 hours,
which catches earnings that get updated or fully populated after initial detection.
"""

import os
import json
import requests
import time
from datetime import datetime, timedelta

# Configuration
FINNHUB_API_KEY = os.getenv('FINNHUB_API_KEY')
FINNHUB_API_KEY_2 = os.getenv('FINNHUB_API_KEY_2')
FINNHUB_API_KEY_3 = os.getenv('FINNHUB_API_KEY_3')
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_EPS_SURPRISES')
HISTORY_FILE = 'data/eps_surprises_history.json'

# NEW: Alert window - only alert once within this time period for each earnings
ALERT_WINDOW_HOURS = 48  # Re-check earnings for 48 hours after first detection

# Create list of API keys (filter out None values)
API_KEYS = [key for key in [FINNHUB_API_KEY, FINNHUB_API_KEY_2, FINNHUB_API_KEY_3] if key]
api_key_index = 0

def get_next_api_key():
    """Round-robin through available API keys"""
    global api_key_index
    key = API_KEYS[api_key_index % len(API_KEYS)]
    api_key_index += 1
    return key

# Symbols to monitor - UPDATED with ARM, COHR, QCOM
SYMBOLS_TO_MONITOR = [
    'ABBV', 'ABT', 'ADBE', 'AEO', 'ALAB', 'ALGN', 'ALGT', 'AMD',
    'AMZN', 'APP', 'ARM', 'ASTS', 'BA', 'BABA', 'BE', 'BULL',
    'CDNS', 'CFLT', 'CMCL', 'CNC', 'COHR', 'COIN', 'COP', 'CPNG',
    'CRWV', 'CSCO', 'CVNA', 'CVS', 'CVX', 'DUOL',
    'ENPH', 'FIG', 'FLR', 'GE', 'GME', 'GOOGL',
    'HIMS', 'HOOD', 'IBM', 'IBRX', 'INTC', 'IONQ',
    'IREN', 'JNJ', 'JOBY', 'KO', 'LCID',
    'LLY', 'LMND', 'LNTH', 'LYFT', 'MARA',
    'META', 'MRVL', 'MSFT', 'MU', 'NEE',
    'NFLX', 'NKE', 'NRG', 'NVAX', 'NVDA',
    'OKLO', 'ONC', 'OPEN', 'ORCL', 'PANW',
    'PATH', 'PEP', 'PDD', 'PFE', 'PLTR',
    'PYPL', 'QBTS', 'QCOM', 'RGTI', 'RKLB',
    'RR', 'SHOP', 'SMCI', 'SMR', 'SNOW',
    'SOFI', 'SOUN', 'SPOT', 'SYNA', 'TEM',
    'TMC', 'TSLA', 'TSM', 'TTD', 'UBER',
    'UAMY', 'UNH', 'USAR', 'UUUU', 'XOM',
    'XPEV', 'Z', 'ZBRA'
]

# Threshold for significant surprises (%)
SURPRISE_THRESHOLD = 5.0


def load_history():
    """Load earnings history"""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, 'r') as f:
                content = f.read().strip()
                if content:
                    return json.loads(content)
                else:
                    return {}
        except (json.JSONDecodeError, ValueError) as e:
            print(f"Warning: Could not parse history file, starting fresh: {e}")
            return {}
    return {}


def save_history(history):
    """Save earnings history"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_earnings_surprises(symbol, max_retries=3):
    """Fetch earnings surprises from Finnhub with retry logic"""
    url = 'https://finnhub.io/api/v1/stock/earnings'
    
    for attempt in range(max_retries):
        params = {
            'symbol': symbol,
            'token': get_next_api_key()
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:
                wait_time = (attempt + 1) * 5
                print(f"  Rate limit hit, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"Error fetching earnings for {symbol}: {e}")
                return None
        except Exception as e:
            print(f"Error fetching earnings for {symbol}: {e}")
            return None
    
    print(f"  Failed after {max_retries} retries")
    return None


def create_earnings_id(symbol, earnings):
    """Create unique ID for earnings report"""
    return f"{symbol}_{earnings.get('period')}"


def calculate_surprise_pct(actual, estimate):
    """Calculate surprise percentage"""
    if estimate == 0:
        return 0
    return ((actual - estimate) / abs(estimate)) * 100


def should_alert(earnings_id, history, surprise_pct):
    """
    Determine if we should send an alert for this earnings report.
    
    NEW LOGIC:
    - If never seen before AND significant: ALERT
    - If seen before but within alert window AND not yet alerted: ALERT
    - If seen before and already alerted: DON'T ALERT
    - If seen before and outside alert window: DON'T ALERT
    """
    if earnings_id not in history:
        # Never seen before, and we know it's significant (caller checks)
        return True
    
    record = history[earnings_id]
    first_seen = datetime.fromisoformat(record.get('first_seen'))
    already_alerted = record.get('alerted', False)
    
    # Check if within alert window
    hours_since_first_seen = (datetime.utcnow() - first_seen).total_seconds() / 3600
    
    if hours_since_first_seen <= ALERT_WINDOW_HOURS:
        # Within alert window
        if not already_alerted and abs(surprise_pct) >= SURPRISE_THRESHOLD:
            # Haven't alerted yet and it's significant
            return True
    
    return False


def format_quarter(period_str):
    """Format period string to readable quarter"""
    try:
        date_obj = datetime.strptime(period_str, '%Y-%m-%d')
        year = date_obj.year
        month = date_obj.month
        
        if month in [1, 2, 3]:
            quarter = "Q1"
        elif month in [4, 5, 6]:
            quarter = "Q2"
        elif month in [7, 8, 9]:
            quarter = "Q3"
        else:
            quarter = "Q4"
        
        return f"{quarter} {year}"
    except:
        return period_str


def format_discord_embed(symbol, earnings):
    """Format earnings data as Discord embed"""
    actual = earnings.get('actual', 0)
    estimate = earnings.get('estimate', 0)
    period = earnings.get('period', 'N/A')
    surprise = earnings.get('surprise', 0)
    surprise_pct = earnings.get('surprisePercent', 0)
    
    if surprise_pct == 0 and estimate != 0:
        surprise_pct = calculate_surprise_pct(actual, estimate)
    
    # Determine if beat or miss
    if actual > estimate:
        result = "🟢 BEAT"
        color = 3066993  # Green
        emoji = "📈"
    elif actual < estimate:
        result = "🔴 MISS"
        color = 15158332  # Red
        emoji = "📉"
    else:
        result = "🟡 MET"
        color = 16776960  # Yellow
        emoji = "➡️"
    
    surprise_pct_str = f"{surprise_pct:+.2f}%"
    quarter_formatted = format_quarter(period)
    report_date = datetime.now().strftime('%B %d, %Y')
    
    embed = {
        "title": f"{emoji} Earnings {result}: {symbol}",
        "description": f"**{quarter_formatted} Earnings**\nDetected: {report_date}",
        "color": color,
        "fields": [
            {
                "name": "Actual EPS",
                "value": f"${actual:.2f}",
                "inline": True
            },
            {
                "name": "Estimated EPS",
                "value": f"${estimate:.2f}",
                "inline": True
            },
            {
                "name": "Surprise",
                "value": f"${surprise:.2f}",
                "inline": True
            },
            {
                "name": "Surprise %",
                "value": surprise_pct_str,
                "inline": True
            },
            {
                "name": "Period Ended",
                "value": period,
                "inline": True
            },
            {
                "name": "Quarter",
                "value": quarter_formatted,
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub Earnings Surprises"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed


def send_discord_alert(embeds):
    """Send alert to Discord webhook with proper batching and rate limiting"""
    if not DISCORD_WEBHOOK:
        print("Discord webhook not configured")
        return False
    
    total_sent = 0
    
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {"embeds": batch}
        
        try:
            response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            response.raise_for_status()
            total_sent += len(batch)
            print(f"Sent batch of {len(batch)} alerts to Discord (total: {total_sent}/{len(embeds)})")
            
            if i + 10 < len(embeds):
                time.sleep(0.5)
                
        except requests.exceptions.HTTPError as e:
            print(f"Error sending Discord alert batch: {e}")
            print(f"Response: {e.response.text if e.response else 'No response'}")
            continue
        except Exception as e:
            print(f"Error sending Discord alert: {e}")
            continue
    
    return total_sent > 0


def main():
    """Main execution function"""
    if not API_KEYS:
        print("Error: No FINNHUB_API_KEY configured")
        return
    
    print(f"Using {len(API_KEYS)} API key(s)")
    print(f"Current time (UTC): {datetime.utcnow().isoformat()}")
    print(f"Alert window: {ALERT_WINDOW_HOURS} hours")
    
    history = load_history()
    print(f"Loaded history with {len(history)} records")
    
    print("\nChecking earnings surprises...")
    
    significant_surprises = []
    
    # Check each symbol
    for symbol in SYMBOLS_TO_MONITOR:
        print(f"Checking {symbol}...")
        data = get_earnings_surprises(symbol)
        
        time.sleep(0.4)  # Rate limiting
        
        if data and len(data) > 0:
            latest = data[0]
            earnings_id = create_earnings_id(symbol, latest)
            
            actual = latest.get('actual', 0)
            estimate = latest.get('estimate', 0)
            surprise_pct = latest.get('surprisePercent', 0)
            
            if surprise_pct == 0 and estimate != 0:
                surprise_pct = calculate_surprise_pct(actual, estimate)
            
            # NEW: Use should_alert logic
            if should_alert(earnings_id, history, surprise_pct):
                significant_surprises.append((symbol, latest))
                print(f"  ✅ ALERT: {surprise_pct:+.2f}%")
                
                # Mark as alerted
                if earnings_id not in history:
                    history[earnings_id] = {
                        'first_seen': datetime.utcnow().isoformat(),
                        'earnings': latest,
                        'alerted': True,
                        'alerted_at': datetime.utcnow().isoformat()
                    }
                else:
                    history[earnings_id]['alerted'] = True
                    history[earnings_id]['alerted_at'] = datetime.utcnow().isoformat()
            else:
                # Update history even if not alerting
                if earnings_id not in history:
                    history[earnings_id] = {
                        'first_seen': datetime.utcnow().isoformat(),
                        'earnings': latest,
                        'alerted': False
                    }
                else:
                    # Just update the earnings data
                    history[earnings_id]['earnings'] = latest
    
    # Send alerts
    if significant_surprises:
        print(f"\nFound {len(significant_surprises)} significant earnings surprises")
        embeds = [
            format_discord_embed(symbol, earnings)
            for symbol, earnings in significant_surprises
        ]
        send_discord_alert(embeds)
    else:
        print("No significant earnings surprises found")
    
    # Clean up old history (keep last 2 years)
    cutoff_date = datetime.utcnow() - timedelta(days=730)
    history = {
        k: v for k, v in history.items()
        if 'first_seen' in v and datetime.fromisoformat(v['first_seen']) > cutoff_date
    }
    
    save_history(history)
    print(f"History contains {len(history)} earnings reports")


if __name__ == '__main__':
    main()
