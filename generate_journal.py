import os
import sys
import csv
import time
import json
import hmac
import hashlib
import requests
from datetime import datetime, date
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse as urlparse

# --- Helper Functions ---

def load_env(filepath=".env"):
    """Load configuration variables from a .env file."""
    config = {}
    if os.path.exists(filepath):
        with open(filepath, "r") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config

def get_target_date():
    """Get target date from command line argument, or default to today's date."""
    if len(sys.argv) > 1:
        date_str = sys.argv[1].strip()
        print(f"Using date from command line argument: {date_str}")
        try:
            return datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            print("Invalid command line date format. Expecting YYYY-MM-DD. Defaulting to today.")
            return date.today()

    today_val = date.today()
    print(f"No date provided. Defaulting to today: {today_val.strftime('%Y-%m-%d')}")
    return today_val

def get_usdt_inr_rate():
    """Fetch the platform's active futures conversion rate from CoinDCX API."""
    config = load_env()
    api_key = config.get("COINDCX_API")
    api_secret = config.get("COINDCX_SECRATE")
    
    # 1. Try to fetch the active futures conversion rate from derivatives endpoint
    if api_key and api_secret:
        try:
            url = "https://api.coindcx.com/exchange/v1/derivatives/futures/data/conversions"
            body = ""
            signature = hmac.new(api_secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()
            headers = {
                "X-AUTH-APIKEY": api_key,
                "X-AUTH-SIGNATURE": signature
            }
            res = requests.get(url, headers=headers, timeout=5)
            if res.status_code == 200:
                data = res.json()
                if isinstance(data, list):
                    for item in data:
                        if item.get("symbol") == "USDTINR":
                            price = float(item.get("conversion_price") or 0)
                            if price > 0:
                                return price
        except Exception as e:
            print(f"[CoinDCX] Failed to fetch active conversion rate: {e}")
            
    # 2. Fallback to Spot ticker rate if futures API fails
    try:
        url = "https://api.coindcx.com/exchange/ticker"
        res = requests.get(url, timeout=5)
        if res.status_code == 200:
            data = res.json()
            for ticker in data:
                if ticker.get("market") == "USDTINR":
                    price = float(ticker.get("last_price") or ticker.get("lastPrice") or 0)
                    if price > 0:
                        return price
    except Exception as e:
        print(f"[CoinDCX] Failed to fetch live USDT-INR rate: {e}")
    return 100.22 # Fallback to today's verified rate

def fetch_coindcx_trades(api_key, api_secret, target_date):
    """Fetch private trade history from CoinDCX (both Spot and Futures) and filter by target date."""
    if not api_key or not api_secret:
        print("[CoinDCX] API Key or Secret missing. Skipping CoinDCX.")
        return []

    print("[CoinDCX] Fetching trade history...")
    usdt_inr_rate = get_usdt_inr_rate()
    print(f"[CoinDCX] Active USDT-INR conversion rate: Rs. {usdt_inr_rate}")
    
    timestamp_ms = int(time.time() * 1000)
    filtered = []
    
    # 1. Fetch Spot Trades
    spot_url = "https://api.coindcx.com/exchange/v1/orders/trade_history"
    spot_payload = {
        "timestamp": timestamp_ms,
        "limit": 500
    }
    body = json.dumps(spot_payload, separators=(',', ':'))
    signature = hmac.new(api_secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-AUTH-APIKEY": api_key,
        "X-AUTH-SIGNATURE": signature
    }
    try:
        res = requests.post(spot_url, data=body, headers=headers)
        if res.status_code == 200:
            trades = res.json()
            if isinstance(trades, list):
                spot_filtered_count = 0
                for t in trades:
                    ts = t.get("timestamp")
                    if not ts:
                        continue
                    trade_dt = datetime.fromtimestamp(ts / 1000.0)
                    if trade_dt.date() == target_date:
                        symbol = t.get("symbol", "")
                        # Convert to INR if it is a USDT trading pair
                        is_usdt = symbol.endswith("_USDT") or symbol.endswith("USDT")
                        rate = usdt_inr_rate if is_usdt else 1.0
                        
                        filtered.append({
                            "symbol": symbol,
                            "qty": float(t.get("quantity", 0)),
                            "price": float(t.get("price", 0)) * rate,
                            "side": t.get("side", "").upper(),
                            "time": trade_dt,
                            "fee": float(t.get("fee_amount", 0)) * rate,
                            "source": "CoinDCX (Spot)"
                        })
                        spot_filtered_count += 1
                if spot_filtered_count > 0:
                    print(f"[CoinDCX] Found {spot_filtered_count} Spot trades matching date {target_date}.")
            else:
                print(f"[CoinDCX] Spot trades response is not a list: {trades}")
        else:
            print(f"[CoinDCX] Spot fetch returned status code {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[CoinDCX] Spot fetch failed: {e}")

    # 2. Fetch Futures Trades
    futures_url = "https://api.coindcx.com/exchange/v1/derivatives/futures/trades"
    futures_payload = {
        "timestamp": timestamp_ms,
        "size": 100,
        "sort": "desc"
    }
    body = json.dumps(futures_payload, separators=(',', ':'))
    signature = hmac.new(api_secret.encode('utf-8'), body.encode('utf-8'), hashlib.sha256).hexdigest()
    headers = {
        "Content-Type": "application/json",
        "X-AUTH-APIKEY": api_key,
        "X-AUTH-SIGNATURE": signature
    }
    try:
        res = requests.post(futures_url, data=body, headers=headers)
        if res.status_code == 200:
            trades = res.json()
            if isinstance(trades, list):
                futures_filtered_count = 0
                for t in trades:
                    ts = t.get("timestamp")
                    if not ts:
                        continue
                    trade_dt = datetime.fromtimestamp(ts / 1000.0)
                    if trade_dt.date() == target_date:
                        symbol = t.get("pair") or t.get("symbol") or ""
                        is_usdt = symbol.endswith("_USDT") or symbol.endswith("USDT")
                        rate = usdt_inr_rate if is_usdt else 1.0
                        
                        filtered.append({
                            "symbol": symbol,
                            "qty": float(t.get("quantity", 0)),
                            "price": float(t.get("price", 0)) * rate,
                            "side": t.get("side", "").upper(),
                            "time": trade_dt,
                            "fee": float(t.get("fee_amount", 0)) * rate,
                            "source": "CoinDCX (Futures)"
                        })
                        futures_filtered_count += 1
                if futures_filtered_count > 0:
                    print(f"[CoinDCX] Found {futures_filtered_count} Futures trades matching date {target_date}.")
            else:
                print(f"[CoinDCX] Futures trades response is not a list: {trades}")
        else:
            print(f"[CoinDCX] Futures fetch returned status code {res.status_code}: {res.text}")
    except Exception as e:
        print(f"[CoinDCX] Futures fetch failed: {e}")
        
    print(f"[CoinDCX] Total trades found: {len(filtered)} for {target_date}.")
    return filtered

# --- Fyers API Integration ---

class TokenReceiverHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        # Suppress logging to keep console clean
        return

    def do_GET(self):
        parsed_url = urlparse.urlparse(self.path)
        query = urlparse.parse_qs(parsed_url.query)
        
        auth_code = query.get("auth_code")
        
        if auth_code:
            auth_code = auth_code[0]
            success = exchange_and_save_token(self.server.app_id, self.server.secret_id, auth_code, self.server.redirect_uri)
            
            if success:
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                success_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Authentication Successful</title>
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            background-color: #121212;
                            color: #e0e0e0;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            margin: 0;
                        }
                        .card {
                            background-color: #1e1e1e;
                            padding: 40px;
                            border-radius: 12px;
                            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                            text-align: center;
                            max-width: 450px;
                        }
                        h1 { color: #4CAF50; margin-bottom: 20px; }
                        p { color: #b0b0b0; line-height: 1.6; }
                        code { background-color: #333; padding: 2px 6px; border-radius: 4px; }
                        .badge {
                            background-color: #2e7d32;
                            color: #ffffff;
                            padding: 8px 16px;
                            border-radius: 20px;
                            font-size: 0.9em;
                            display: inline-block;
                            margin-top: 20px;
                            font-weight: bold;
                        }
                    </style>
                </head>
                <body>
                    <div class="card">
                        <h1>Authentication Successful!</h1>
                        <p>Your Fyers access token has been generated and saved locally to <code>fyers_token.txt</code>.</p>
                        <p>You can close this tab and return to the terminal. The script will proceed automatically.</p>
                        <span class="badge">Success</span>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(success_html.encode("utf-8"))
                self.server.auth_completed = True
            else:
                self.send_response(400)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                error_html = """
                <!DOCTYPE html>
                <html>
                <head>
                    <title>Authentication Failed</title>
                    <style>
                        body {
                            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
                            background-color: #121212;
                            color: #e0e0e0;
                            display: flex;
                            align-items: center;
                            justify-content: center;
                            height: 100vh;
                            margin: 0;
                        }
                        .card {
                            background-color: #1e1e1e;
                            padding: 40px;
                            border-radius: 12px;
                            box-shadow: 0 4px 20px rgba(0,0,0,0.5);
                            text-align: center;
                            max-width: 400px;
                        }
                        h1 { color: #f44336; margin-bottom: 20px; }
                        p { color: #b0b0b0; line-height: 1.6; }
                    </style>
                </head>
                <body>
                    <div class="card">
                        <h1>Authentication Failed</h1>
                        <p>We could not exchange your authorization code for an access token. Please check your Fyers API dashboard keys in <code>.env</code>.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(error_html.encode("utf-8"))
                self.server.auth_completed = True
        else:
            self.send_response(400)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"No auth_code parameter found in redirect.")

def exchange_and_save_token(app_id, secret_id, auth_code, redirect_uri):
    # Try 1: with suffix (as in app_id)
    concat_str_1 = f"{app_id}:{secret_id}"
    app_id_hash_1 = hashlib.sha256(concat_str_1.encode('utf-8')).hexdigest()
    
    # Try 2: without suffix (e.g. remove -100 or -200 or whatever)
    app_id_no_suffix = app_id.split("-")[0]
    concat_str_2 = f"{app_id_no_suffix}:{secret_id}"
    app_id_hash_2 = hashlib.sha256(concat_str_2.encode('utf-8')).hexdigest()
    
    token_url = "https://api-t1.fyers.in/api/v3/validate-authcode"
    
    for attempt, app_id_hash in enumerate([app_id_hash_1, app_id_hash_2], start=1):
        payload = {
            "grant_type": "authorization_code",
            "appIdHash": app_id_hash,
            "code": auth_code
        }
        try:
            target_id = app_id if attempt == 1 else app_id_no_suffix
            print(f"[Fyers] Token exchange attempt {attempt} (using hash of App ID: {target_id})...")
            res = requests.post(token_url, json=payload)
            if res.status_code == 200:
                res_data = res.json()
                access_token = res_data.get("access_token")
                if access_token:
                    with open("fyers_token.txt", "w") as f:
                        f.write(access_token)
                    print("[Fyers] Authentication successful! Access token saved.")
                    return True
                else:
                    print(f"[Fyers] Attempt {attempt} response error: {res_data}")
            else:
                print(f"[Fyers] Attempt {attempt} failed (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"[Fyers] Attempt {attempt} error: {e}")
            
    return False



def get_fyers_token(app_id, secret_id):
    """Retrieve or generate Fyers access token, running a local redirect server if needed."""
    token_file = "fyers_token.txt"
    config = load_env()
    
    # 1. Try reading cached token
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            token = f.read().strip()
            if token:
                # Basic test call to verify if cached token works
                test_url = "https://api-t1.fyers.in/api/v3/profile"
                headers = {
                    "Authorization": f"{app_id}:{token}",
                    "Content-Type": "application/json"
                }
                res = requests.get(test_url, headers=headers)
                if res.status_code == 200:
                    return token
                else:
                    print("[Fyers] Cached token is invalid or expired. Re-authenticating...")

    # 2. Automated Web Server Flow
    print("\n--- Fyers Login Verification Required ---")
    redirect_uri = config.get("FYERS_REDIRECT_URI", "http://localhost:5005/")
    
    # Parse port from redirect URI (default to 5005)
    port = 5005
    try:
        parsed_uri = urlparse.urlparse(redirect_uri)
        if parsed_uri.port:
            port = int(parsed_uri.port)
    except Exception:
        pass
        
    # Generate the login authorization URL
    auth_url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={app_id}&redirect_uri={redirect_uri}&response_type=code&state=tradejournal"
    print(f"Please log in and authorize the app using the link below:\n\n{auth_url}\n")
    print(f"[Fyers] Starting temporary redirect handler on port {port}...")
    
    server = HTTPServer(('127.0.0.1', port), TokenReceiverHandler)
    server.app_id = app_id
    server.secret_id = secret_id
    server.redirect_uri = redirect_uri
    server.auth_completed = False
    
    # Wait for the redirect request
    while not server.auth_completed:
        server.handle_request()
        
    server.server_close()
    print("[Fyers] Temporary redirect handler closed.")
    
    # Read the saved token
    if os.path.exists(token_file):
        with open(token_file, "r") as f:
            return f.read().strip()
            
    return None

def calculate_fyers_charges(symbol, side, qty, price, product_type):
    """
    Calculate estimated Fyers transaction charges and taxes.
    Includes: Brokerage, STT, Exchange Transaction Charges (ETC), SEBI turnover fee, GST, and Stamp Duty.
    """
    trade_value = qty * price
    sym_name = symbol.split(":")[-1] if ":" in symbol else symbol
    
    # Check if Options (symbols ending in CE/PE)
    is_option = sym_name.endswith("CE") or sym_name.endswith("PE")
    
    if is_option:
        # F&O Options charges matching Fyers platform exactly
        brokerage = 20.0
        
        # 1. Transaction (Exchange + clearing): 0.04353%
        etc = 0.0004353 * trade_value
        
        # 2. SEBI Fee: Rs 10 per crore (0.0001%)
        sebi = 0.000001 * trade_value
        
        # 3. GST: 18% on (Brokerage + ETC + SEBI)
        gst = 0.18 * (brokerage + etc + sebi)
        
        # 4. Stamp Duty: 0.003% on BUY side
        stamp = 0.00003 * trade_value if side == "BUY" else 0.0
        
        # 5. NSE IPFT: Rs 50 per crore (0.0005%)
        ipft = 0.000005 * trade_value
        
        # 6. STT: 0.15% on SELL side
        stt = 0.0015 * trade_value if side == "SELL" else 0.0
        
        total = brokerage + etc + sebi + gst + stamp + ipft + stt
        return total
        
    elif product_type == "INTRADAY":
        # Equity Intraday charges
        brokerage = min(20.0, 0.0003 * trade_value)
        stt = 0.00025 * trade_value if side == "SELL" else 0.0
        etc = 0.0000297 * trade_value
        sebi = 0.000001 * trade_value
        gst = 0.18 * (brokerage + etc + sebi)
        stamp = 0.00003 * trade_value if side == "BUY" else 0.0
        ipft = 0.0000001 * trade_value # Rs 10 per crore for Equity
        
        total = brokerage + stt + etc + sebi + gst + stamp + ipft
        return total
        
    return 0.0

def fetch_fyers_trades(app_id, secret_id, target_date):
    """Fetch tradebook from Fyers and filter/match by target date."""
    if not app_id or not secret_id:
        print("[Fyers] App ID or Secret ID missing. Skipping Fyers.")
        return []

    access_token = get_fyers_token(app_id, secret_id)
    if not access_token:
        return []

    print("[Fyers] Fetching tradebook...")
    url = "https://api-t1.fyers.in/api/v3/tradebook"
    
    # v3 expects client_id:token as the Authorization header
    headers = {
        "Authorization": f"{app_id}:{access_token}",
        "Content-Type": "application/json"
    }

    try:
        response = requests.get(url, headers=headers)
        if response.status_code != 200:
            print(f"[Fyers] Error (HTTP {response.status_code}): {response.text}")
            return []

        res_data = response.json()
        if res_data.get("s") != "ok":
            print(f"[Fyers] API returned error: {res_data}")
            return []

        tradebook = res_data.get("tradeBook", [])
        # Group fills by orderNumber to handle split fills correctly
        grouped_orders = {}
        for t in tradebook:
            trade_time_str = t.get("orderDateTime") or t.get("tradeTime") # e.g. "29-Jul-2026 10:15:30"
            if not trade_time_str:
                continue
            
            try:
                # Common formats: "29-Jul-2026 10:15:30" or timestamp
                if isinstance(trade_time_str, (int, float)):
                    trade_dt = datetime.fromtimestamp(trade_time_str)
                else:
                    trade_dt = datetime.strptime(trade_time_str, "%d-%b-%Y %H:%M:%S")
            except Exception:
                try:
                    trade_dt = datetime.strptime(trade_time_str, "%Y-%m-%d %H:%M:%S")
                except Exception:
                    trade_dt = datetime.combine(date.today(), datetime.min.time())
            
            if trade_dt.date() == target_date:
                # Group by orderNumber if present, fallback to tradeNumber, symbol+time, etc.
                order_num = t.get("orderNumber") or t.get("tradeNumber") or f"unknown_{t.get('symbol')}_{trade_time_str}"
                
                if order_num not in grouped_orders:
                    grouped_orders[order_num] = {
                        "symbol": t.get("symbol"),
                        "side_val": t.get("side"),
                        "productType": t.get("productType", ""),
                        "time": trade_dt,
                        "fills": []
                    }
                grouped_orders[order_num]["fills"].append(t)
                
        filtered = []
        for order_num, order_info in grouped_orders.items():
            symbol = order_info["symbol"]
            # side: 1 = BUY, -1 = SELL
            side_str = "BUY" if order_info["side_val"] == 1 else "SELL"
            product_type = order_info["productType"]
            trade_dt = order_info["time"]
            
            total_qty = 0.0
            total_value = 0.0
            for fill in order_info["fills"]:
                qty = float(fill.get("tradedQty") or fill.get("tradeQty") or 0)
                price = float(fill.get("tradePrice", 0))
                total_qty += qty
                total_value += qty * price
                
            if total_qty > 0:
                avg_price = total_value / total_qty
            else:
                avg_price = 0.0
                
            # Calculate total transaction charges on the merged order quantity & avg price
            charges = calculate_fyers_charges(symbol, side_str, total_qty, avg_price, product_type)
            
            filtered.append({
                "symbol": symbol,
                "qty": total_qty,
                "price": avg_price,
                "side": side_str,
                "time": trade_dt,
                "fee": charges,
                "source": "Fyers"
            })
        print(f"[Fyers] Found {len(filtered)} trades (grouped by order) for {target_date}.")
        return filtered
    except Exception as e:
        print(f"[Fyers] Request failed: {e}")
        return []

def get_fyers_symbol_multiplier(symbol):
    """Return the lot size multiplier for Fyers symbols, especially MCX commodities."""
    if not symbol:
        return 1.0
        
    symbol = symbol.upper()
    if symbol.startswith("MCX:"):
        underlying = symbol.replace("MCX:", "")
        
        if underlying.startswith("CRUDEOILM"):
            return 10.0
        elif underlying.startswith("CRUDEOIL"):
            return 100.0
        elif underlying.startswith("NATURALGASM"):
            return 250.0
        elif underlying.startswith("NATURALGAS"):
            return 1250.0
        elif underlying.startswith("SILVERMIC"):
            return 1.0
        elif underlying.startswith("SILVERM"):
            return 5.0
        elif underlying.startswith("SILVER"):
            return 30.0
        elif underlying.startswith("GOLDM"):
            return 10.0
        elif underlying.startswith("GOLD"):
            return 100.0
        elif underlying.startswith("COPPER"):
            return 2500.0
        elif underlying.startswith("NICKEL"):
            return 1500.0
        elif underlying.startswith("ALUMINIUM") or underlying.startswith("ZINC") or underlying.startswith("LEAD"):
            return 5000.0
            
    return 1.0

def preprocess_executions(executions):
    """
    Merge executions that occurred at the same timestamp and side using weighted average price.
    This prevents split fills at slightly different prices from being treated as separate trades.
    """
    grouped = {}
    for ex in executions:
        key = (ex["time"], ex["side"], ex["symbol"], ex.get("source"))
        if key not in grouped:
            grouped[key] = {
                "symbol": ex["symbol"],
                "qty": 0.0,
                "price_accum": 0.0,
                "side": ex["side"],
                "time": ex["time"],
                "fee": 0.0,
                "source": ex.get("source")
            }
        grouped[key]["qty"] += ex["qty"]
        grouped[key]["price_accum"] += ex["price"] * ex["qty"]
        grouped[key]["fee"] += ex["fee"]
        
    result = []
    for key, val in grouped.items():
        if val["qty"] > 0:
            val["price"] = val["price_accum"] / val["qty"]
        else:
            val["price"] = 0.0
        del val["price_accum"]
        result.append(val)
        
    return result

def merge_partial_exits(trades):
    """Group matched trades by entry_time and combine partial exits into a single row."""
    merged = []
    # Group trades by entry_time, side, and ticker
    grouped = {}
    for t in trades:
        key = (t["entry_time"], t["side"], t["ticker"])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(t)
        
    for key, group in grouped.items():
        if len(group) == 1:
            # Only one entry-exit, keep as is
            merged.append(group[0])
        else:
            # Sort the group by exit_time_1 to identify chronological order of exits
            # Open positions (empty exit time) will be sorted to the end
            group_sorted = sorted(
                group, 
                key=lambda x: x["exit_time_1"] if isinstance(x["exit_time_1"], datetime) else datetime.max
            )
            
            base_trade = group_sorted[0]
            
            # First exit details
            exit_time_1 = base_trade["exit_time_1"]
            pl_1 = base_trade["pl_1"]
            total_fee = base_trade["fee"]
            total_pl = base_trade["pl"] if isinstance(base_trade["pl"], (int, float)) else 0.0
            
            # We will combine all subsequent exits into exit_time_2 and pl_2
            exit_time_2 = ""
            pl_2 = 0.0
            has_second_exit = False
            
            for extra in group_sorted[1:]:
                total_fee += extra["fee"]
                if isinstance(extra["pl"], (int, float)):
                    total_pl += extra["pl"]
                
                # Record the second exit time
                if extra["exit_time_1"]:
                    exit_time_2 = extra["exit_time_1"]
                    has_second_exit = True
                if isinstance(extra["pl_1"], (int, float)):
                    pl_2 += extra["pl_1"]
                    
            merged.append({
                "ticker": base_trade["ticker"],
                "entry_time": base_trade["entry_time"],
                "exit_time_1": exit_time_1,
                "exit_time_2": exit_time_2 if has_second_exit else "",
                "side": base_trade["side"],
                "pl": total_pl,
                "pl_1": pl_1,
                "pl_2": pl_2 if has_second_exit else "",
                "fee": total_fee,
                "source": base_trade.get("source", "CoinDCX")
            })
    return merged

def match_executions(executions):
    """
    Match chronological raw buy/sell executions for a symbol into structured trades.
    If there are multiple partial exits at different times, they are split into separate rows.
    """
    # Preprocess to merge simultaneous identical executions
    merged_ex = preprocess_executions(executions)
    
    # Sort executions chronologically
    sorted_ex = sorted(merged_ex, key=lambda x: x["time"])
    
    trades = []
    active_entries = [] # List of {"qty": qty, "price": price, "time": time, "fee": fee, "source": source}
    active_side = None
    
    for ex in sorted_ex:
        qty = ex["qty"]
        price = ex["price"]
        ex_time = ex["time"]
        fee = ex["fee"]
        side = ex["side"]
        symbol = ex["symbol"]
        source = ex.get("source", "CoinDCX")
        
        if active_side is None:
            active_side = side
            active_entries.append({
                "qty": qty,
                "price": price,
                "time": ex_time,
                "fee": fee,
                "source": source
            })
        elif active_side == side:
            # Scaling in
            active_entries.append({
                "qty": qty,
                "price": price,
                "time": ex_time,
                "fee": fee,
                "source": source
            })
        else:
            # Scaling out (exit) using FIFO
            remaining_exit_qty = qty
            
            while remaining_exit_qty > 1e-6 and active_entries:
                entry = active_entries[0]
                matched_qty = min(remaining_exit_qty, entry["qty"])
                
                # Pro-rata entry fee for this matched part
                entry_fee_share = (matched_qty / entry["qty"]) * entry["fee"]
                # Pro-rata exit fee share for this matched part
                exit_fee_share = (matched_qty / qty) * fee
                total_trade_fee = entry_fee_share + exit_fee_share
                
                # Calculate P/L for this matched part
                multiplier = get_fyers_symbol_multiplier(symbol) if entry.get("source") == "Fyers" else 1.0
                if active_side == "BUY":
                    pl = matched_qty * (price - entry["price"]) * multiplier
                else:
                    pl = matched_qty * (entry["price"] - price) * multiplier
                    
                # Create a matched trade record
                trades.append({
                    "ticker": symbol,
                    "entry_time": entry["time"],
                    "exit_time_1": ex_time,
                    "exit_time_2": "",
                    "side": active_side,
                    "pl": pl,
                    "pl_1": pl,
                    "pl_2": "",
                    "fee": total_trade_fee,
                    "source": entry.get("source", "CoinDCX")
                })
                
                # Deduct matched quantity from entry and exit
                entry["qty"] -= matched_qty
                entry["fee"] -= entry_fee_share
                remaining_exit_qty -= matched_qty
                
                if entry["qty"] <= 1e-6:
                    active_entries.pop(0)
                    
            if not active_entries:
                active_side = None
                
            # If there is remaining exit quantity but entries are empty, position reversed
            if remaining_exit_qty > 1e-6:
                active_side = side
                active_entries.append({
                    "qty": remaining_exit_qty,
                    "price": price,
                    "time": ex_time,
                    "fee": (remaining_exit_qty / qty) * fee,
                    "source": source
                })
                
    # Handle remaining open positions
    for entry in active_entries:
        if entry["qty"] > 1e-6:
            trades.append({
                "ticker": symbol,
                "entry_time": entry["time"],
                "exit_time_1": "",
                "exit_time_2": "",
                "side": active_side,
                "pl": "",
                "pl_1": "",
                "pl_2": "",
                "fee": entry["fee"],
                "source": entry.get("source", "CoinDCX")
            })
        
    # Merge partial exits sharing the same entry timestamp
    trades = merge_partial_exits(trades)
    return trades

# --- Main Flow ---

def main():
    config = load_env()
    
    # 1. Select Date
    target_date = get_target_date()
    
    # 2. Fetch Executions
    all_executions = []
    
    # CoinDCX Executions
    coindcx_api = config.get("COINDCX_API")
    coindcx_secret = config.get("COINDCX_SECRATE")
    all_executions.extend(fetch_coindcx_trades(coindcx_api, coindcx_secret, target_date))
    
    # Fyers Executions
    fyers_app_id = config.get("FYERS_APP_ID")
    fyers_secret_id = config.get("FYERS_SECRATE_ID")
    all_executions.extend(fetch_fyers_trades(fyers_app_id, fyers_secret_id, target_date))
    
    if not all_executions:
        print(f"\nNo trades found for {target_date} on either Fyers or CoinDCX.")
        return

    # 3. Group and Match Executions by Ticker
    executions_by_ticker = {}
    for ex in all_executions:
        ticker = ex["symbol"]
        if ticker not in executions_by_ticker:
            executions_by_ticker[ticker] = []
        executions_by_ticker[ticker].append(ex)
        
    compiled_trades = []
    for ticker, ex_list in executions_by_ticker.items():
        matched = match_executions(ex_list)
        compiled_trades.extend(matched)
        
    # Sort matched trades by entry time
    compiled_trades = sorted(compiled_trades, key=lambda x: x["entry_time"])

    # 4. Output to CSV
    csv_file = "trade_journal.csv"
    headers = [
        "Date", "Trade Index", "Ticker", "Time", "Exit Time 1", "Exit Time 2",
        "Side", "PL Results", "P/L after Charges", "P/L", "P/L 1", "P/L 2", "Brokrage", "Trend", "Liqudity type",
        "First candle type", "Setup explanation", "Is trade works", "Can this be improved",
        "Learning", "Number of fail on same setup before work"
    ]
    target_date_str = target_date.strftime("%Y-%m-%d")
    last_index = 0

    print(f"\nWriting {len(compiled_trades)} trades to '{csv_file}'...")
    
    try:
        with open(csv_file, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            
            for i, t in enumerate(compiled_trades, start=1):
                trade_idx = last_index + i
                
                # Formatting times
                entry_time_str = t["entry_time"].strftime("%H:%M:%S")
                exit_1_str = t["exit_time_1"].strftime("%H:%M:%S") if isinstance(t["exit_time_1"], datetime) else str(t["exit_time_1"])
                exit_2_str = t["exit_time_2"].strftime("%H:%M:%S") if isinstance(t["exit_time_2"], datetime) else str(t["exit_time_2"])
                
                # Format P/Ls (2 decimal places if float)
                pl = f"{t['pl']:.2f}" if isinstance(t["pl"], float) else str(t["pl"])
                
                # P/L after Charges (P/L - Fee)
                if isinstance(t["pl"], (int, float)) and isinstance(t["fee"], (int, float)):
                    pl_after = f"{(t['pl'] - t['fee']):.2f}"
                else:
                    pl_after = ""
                    
                pl_1 = f"{t['pl_1']:.2f}" if isinstance(t["pl_1"], float) else str(t["pl_1"])
                pl_2 = f"{t['pl_2']:.2f}" if isinstance(t["pl_2"], float) else str(t["pl_2"])
                fee = f"{t['fee']:.4f}" if isinstance(t["fee"], float) else str(t["fee"])
                
                row = [
                    target_date_str,                  # Date
                    trade_idx,                        # Trade Index
                    t["ticker"],                      # Ticker
                    entry_time_str,                   # Time
                    exit_1_str,                       # Exit Time 1
                    exit_2_str,                       # Exit Time 2
                    t["side"],                        # Side
                    "",                               # PL Results (Empty)
                    pl_after,                         # P/L after Charges
                    pl,                               # P/L
                    pl_1,                             # P/L 1
                    pl_2,                             # P/L 2
                    fee,                              # Brokrage
                    "",                               # Trend (Empty)
                    "",                               # Liqudity type (Empty)
                    "",                               # First candle type (Empty)
                    "",                               # Setup explanation (Empty)
                    "",                               # Is trade works (Empty)
                    "",                               # Can this be improved (Empty)
                    "",                               # Learning (Empty)
                    ""                                # Number of fail... (Empty)
                ]
                writer.writerow(row)
        print("Done! CSV file updated successfully.")
    except PermissionError:
        print(f"\n[ERROR] Permission Denied: Could not write to '{csv_file}'. Please make sure it is closed and not open in Excel, then run again.")
        return

    # Calculate and Print terminal summaries
    fyers_gross = sum(t["pl"] for t in compiled_trades if "Fyers" in t.get("source", "") and isinstance(t["pl"], (int, float)))
    fyers_fee = sum(t["fee"] for t in compiled_trades if "Fyers" in t.get("source", "") and isinstance(t["fee"], (int, float)))
    fyers_net = fyers_gross - fyers_fee

    coindcx_gross = sum(t["pl"] for t in compiled_trades if "CoinDCX" in t.get("source", "") and isinstance(t["pl"], (int, float)))
    coindcx_fee = sum(t["fee"] for t in compiled_trades if "CoinDCX" in t.get("source", "") and isinstance(t["fee"], (int, float)))
    coindcx_net = coindcx_gross - coindcx_fee

    combined_gross = fyers_gross + coindcx_gross
    combined_fee = fyers_fee + coindcx_fee
    combined_net = combined_gross - combined_fee
    
    print("\n==================================================")
    print(f"            TRADE SUMMARY FOR {target_date_str}")
    print("==================================================")
    print(f"Fyers Gross P/L   : Rs. {fyers_gross:,.2f}")
    print(f"Fyers Charges     : Rs. {fyers_fee:,.2f}")
    print(f"Fyers Net P/L     : Rs. {fyers_net:,.2f}")
    print("--------------------------------------------------")
    print(f"CoinDCX Gross P/L : Rs. {coindcx_gross:,.2f}")
    print(f"CoinDCX Charges   : Rs. {coindcx_fee:,.2f}")
    print(f"CoinDCX Net P/L   : Rs. {coindcx_net:,.2f}")
    print("--------------------------------------------------")
    print(f"Combined Gross P/L: Rs. {combined_gross:,.2f}")
    print(f"Combined Charges  : Rs. {combined_fee:,.2f}")
    print(f"Combined Net P/L  : Rs. {combined_net:,.2f}")
    print("==================================================\n")

if __name__ == "__main__":
    main()
