#!/usr/bin/env python3
"""
Insider Transactions Alert Script
Monitors insider transactions and sends alerts to Discord

ALERT THRESHOLDS:
- Transaction value >= $100,000 OR
- Number of shares changed >= 10,000
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
DISCORD_WEBHOOK = os.getenv('DISCORD_WEBHOOK_INSIDER_TRANSACTIONS')
HISTORY_FILE = 'data/insider_transactions_history.json'

# Alert thresholds
MIN_TRANSACTION_VALUE = 100_000  # $100k
MIN_SHARES_CHANGED = 10_000      # 10k shares

# Create list of API keys (filter out None values)
API_KEYS = [key for key in [FINNHUB_API_KEY, FINNHUB_API_KEY_2, FINNHUB_API_KEY_3] if key]
api_key_index = 0

def get_next_api_key():
    """Round-robin through available API keys"""
    global api_key_index
    key = API_KEYS[api_key_index % len(API_KEYS)]
    api_key_index += 1
    return key

# Symbols to monitor
SYMBOLS_TO_MONITOR = [
    'ABBV', 'ABT', 'ADBE', 'AEO', 'ALAB', 'ALGN', 'ALGT', 'AMD',
    'AMZN', 'APP', 'ASTS', 'BA', 'BABA', 'BE', 'BULL',
    'CDNS', 'CFLT', 'CMCL', 'CNC', 'COIN', 'COP', 'CPNG',
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


def load_history():
    """Load transaction history to avoid duplicates"""
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
    """Save transaction history"""
    os.makedirs(os.path.dirname(HISTORY_FILE), exist_ok=True)
    with open(HISTORY_FILE, 'w') as f:
        json.dump(history, f, indent=2)


def get_insider_transactions(symbol, from_date, to_date, max_retries=3):
    """Fetch insider transactions from Finnhub with retry logic"""
    url = 'https://finnhub.io/api/v1/stock/insider-transactions'
    
    for attempt in range(max_retries):
        params = {
            'symbol': symbol,
            'from': from_date,
            'to': to_date,
            'token': get_next_api_key()  # Use round-robin API key
        }
        
        try:
            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429:  # Rate limit hit
                wait_time = (attempt + 1) * 5  # 5, 10, 15 seconds
                print(f"  Rate limit hit, waiting {wait_time}s...")
                time.sleep(wait_time)
                continue
            else:
                print(f"Error fetching transactions for {symbol}: {e}")
                return None
        except Exception as e:
            print(f"Error fetching transactions for {symbol}: {e}")
            return None
    
    print(f"  Failed after {max_retries} retries")
    return None


def create_transaction_id(transaction):
    """Create unique ID for transaction"""
    return f"{transaction.get('symbol')}_{transaction.get('name')}_{transaction.get('transactionDate')}_{transaction.get('share')}_{transaction.get('transactionCode')}"


def get_transaction_code_description(code):
    """Get human-readable description for transaction code"""
    code_descriptions = {
        'P': 'Open Market Purchase',
        'S': 'Open Market Sale',
        'A': 'Grant/Award',
        'D': 'Sale to Issuer',
        'F': 'Tax Withholding',
        'I': 'Discretionary Transaction',
        'M': 'Exercise of Options',
        'C': 'Conversion',
        'E': 'Expiration',
        'H': 'Held',
        'J': 'Other',
        'G': 'Gift',
        'L': 'Small Acquisition',
        'W': 'Acquisition/Disposition by Will',
        'Z': 'Deposit/Withdrawal from Voting Trust',
        'U': 'Tender of Shares'
    }
    return code_descriptions.get(code, 'Other Transaction')


def is_significant_transaction(transaction):
    """Check if transaction meets significance thresholds"""
    change = transaction.get('change', 0)
    transaction_price = transaction.get('transactionPrice', 0)
    
    # Calculate transaction value
    transaction_value = abs(change * transaction_price) if transaction_price else 0
    
    # Check thresholds: $100k+ in value OR 10k+ shares
    return transaction_value >= MIN_TRANSACTION_VALUE or abs(change) >= MIN_SHARES_CHANGED


def format_discord_embed(transaction):
    """Format transaction data as Discord embed"""
    symbol = transaction.get('symbol', 'N/A')
    name = transaction.get('name', 'Unknown')
    change = transaction.get('change', 0)
    shares = transaction.get('share', 0)
    transaction_code = transaction.get('transactionCode', 'N/A')
    transaction_date = transaction.get('transactionDate', 'N/A')
    filing_date = transaction.get('filingDate', 'N/A')
    transaction_price = transaction.get('transactionPrice', 0)
    
    # Get transaction code description
    code_description = get_transaction_code_description(transaction_code)
    
    # Calculate transaction value
    transaction_value = change * transaction_price if transaction_price else 0
    
    # Determine transaction type and color based on change (positive = buy, negative = sell)
    if change > 0:
        transaction_type = '🟢 BUY'
        color = 3066993  # Green
    elif change < 0:
        transaction_type = '🔴 SELL'
        color = 15158332  # Red
    else:
        transaction_type = f'📊 {transaction_code}'
        color = 3447003  # Blue
    
    # Format values
    change_formatted = f"{change:+,}"  # +/- with commas
    shares_formatted = f"{shares:,}" if shares else "N/A"
    value_formatted = f"${transaction_value:,.2f}" if transaction_value else "N/A"
    price_formatted = f"${transaction_price:.2f}" if transaction_price else "N/A"
    
    embed = {
        "title": f"{transaction_type} - {symbol}",
        "description": f"**{name}**",
        "color": color,
        "fields": [
            {
                "name": "Change",
                "value": change_formatted,
                "inline": True
            },
            {
                "name": "Transaction Value",
                "value": value_formatted,
                "inline": True
            },
            {
                "name": "Transaction Price",
                "value": price_formatted,
                "inline": True
            },
            {
                "name": "Shares Held After",
                "value": shares_formatted,
                "inline": True
            },
            {
                "name": "Transaction Code",
                "value": f"{transaction_code} - {code_description}",
                "inline": False
            },
            {
                "name": "Transaction Date",
                "value": transaction_date,
                "inline": True
            },
            {
                "name": "Filing Date",
                "value": filing_date,
                "inline": True
            }
        ],
        "footer": {
            "text": "Finnhub Insider Transactions"
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    return embed


def send_discord_alert(embeds):
    """Send alert to Discord webhook"""
    if not DISCORD_WEBHOOK:
        print("Discord webhook not configured")
        return False
    
    # Discord allows max 10 embeds per message
    for i in range(0, len(embeds), 10):
        batch = embeds[i:i+10]
        payload = {
            "embeds": batch
        }
        
        try:
            response = requests.post(DISCORD_WEBHOOK, json=payload, timeout=10)
            response.raise_for_status()
            print(f"Sent {len(batch)} alerts to Discord")
        except Exception as e:
            print(f"Error sending Discord alert: {e}")
            return False
    
    return True


def main():
    """Main execution function"""
    if not API_KEYS:
        print("Error: No FINNHUB_API_KEY configured")
        return
    
    print(f"Using {len(API_KEYS)} API key(s)")
    
    # Load history
    history = load_history()
    
    # Calculate date range (last 7 days to catch any delayed filings)
    to_date = datetime.now().strftime('%Y-%m-%d')
    from_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
    
    print(f"Checking insider transactions from {from_date} to {to_date}")
    
    new_transactions = []
    
    # Check each symbol
    for symbol in SYMBOLS_TO_MONITOR:
        print(f"Checking {symbol}...")
        data = get_insider_transactions(symbol, from_date, to_date)
        
        # Rate limit with 3 API keys: 180 API calls per minute = 0.33s per call
        # Using 0.4s for safety buffer
        time.sleep(0.4)
        
        if data and 'data' in data:
            for transaction in data['data']:
                transaction_id = create_transaction_id(transaction)
                
                # Check if we've seen this transaction before
                if transaction_id not in history:
                    # Check if transaction is significant ($100k+ or 10k+ shares)
                    if is_significant_transaction(transaction):
                        new_transactions.append(transaction)
                        change = transaction.get('change', 0)
                        price = transaction.get('transactionPrice', 0)
                        value = abs(change * price) if price else 0
                        print(f"  New transaction: {transaction.get('name')} - {transaction.get('transactionCode')} - {change:+,} shares (${value:,.2f})")
                    
                    history[transaction_id] = {
                        'first_seen': datetime.utcnow().isoformat(),
                        'transaction': transaction
                    }
    
    # Send alerts for new transactions
    if new_transactions:
        print(f"\nFound {len(new_transactions)} new transactions")
        embeds = [format_discord_embed(t) for t in new_transactions]
        send_discord_alert(embeds)
    else:
        print("No new transactions found")
    
    # Clean up old history (keep last 30 days)
    cutoff_date = datetime.utcnow() - timedelta(days=30)
    history = {
        k: v for k, v in history.items()
        if 'first_seen' in v and datetime.fromisoformat(v['first_seen']) > cutoff_date
    }
    
    # Save updated history
    save_history(history)
    print(f"History contains {len(history)} transactions")


if __name__ == '__main__':
    main()
