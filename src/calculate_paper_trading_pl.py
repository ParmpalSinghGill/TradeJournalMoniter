import csv
import os
import re

# Base directory setup (Project Root)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT_DIR = os.path.dirname(SCRIPT_DIR)

# Trading Constants & Rules
OPTION_CAPITAL_LIMIT = 10000.0  # Rs. 10,000 capital limit for Nifty & Crud options
GOLD_CAPITAL_LIMIT = 5000.0     # Rs. 5,000 capital limit for Gold trades

NIFTY_LOT_SIZE = 65            # 65 units per lot for Nifty options
CRUD_LOT_SIZE = 10             # 10 units per lot for Crude Oil options

GOLD_LEVERAGE = 30.0           # 30x leverage on Gold
GOLD_USD_INR_RATE = 102.0      # 102 INR per USD/USDT for Gold contracts
GOLD_TOTAL_EXPOSURE = GOLD_CAPITAL_LIMIT * GOLD_LEVERAGE  # Rs. 150,000 exposure for Gold (5k x 30)

def parse_psl_percent(val_str):
    """
    Parses P/SL % string into a float percentage value.
    Handles standard percentages ("8.10%", "-3.99"), floats, 
    and Excel time format anomalies ("05:18:00 AM" -> 5.18%).
    """
    if not val_str:
        return 0.0
    
    val_str = str(val_str).strip()
    
    if val_str.endswith('%'):
        val_str = val_str[:-1].strip()
        
    time_match = re.match(r'^(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)$', val_str, re.IGNORECASE)
    if time_match:
        hours = int(time_match.group(1))
        minutes = int(time_match.group(2))
        return float(f"{hours}.{minutes:02d}")
        
    try:
        return float(val_str)
    except ValueError:
        return 0.0

def determine_category(ticker):
    """Categorize trade based on ticker symbol into Nifty, Crud, or Gold."""
    ticker_upper = str(ticker).upper()
    if 'NIFTY' in ticker_upper:
        return 'Nifty'
    elif 'CRUD' in ticker_upper:
        return 'Crud'
    elif 'GOLD' in ticker_upper:
        return 'Gold'
    return 'Other'

def calculate_trade_brokerage(category):
    """
    Brokerage charges per trade order:
    - Nifty & Crud Options: Rs 64 roundtrip (Rs 20 buy + Rs 20 sell + STT/GST/etc).
    - Gold: Rs 22 roundtrip.
    """
    if category == 'Gold':
        return 22.0
    else:
        return 64.0

def process_paper_trading(input_csv=None, output_csv=None):
    if input_csv is None:
        input_csv = os.path.join(ROOT_DIR, "paper_trading.csv")
    if output_csv is None:
        output_csv = os.path.join(ROOT_DIR, "paper_trading_with_pl.csv")
        
    if not os.path.exists(input_csv):
        print(f"Error: Input file '{input_csv}' not found.")
        return
    
    included_trades = []
    skipped_trades = []
    
    prev_date = ""
    prev_ticker = ""
    
    with open(input_csv, mode='r', newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        
        for row in reader:
            if not row or len(row) < 7:
                continue
            
            row = [item.strip() for item in row]
            
            date_str = row[0] if row[0] else prev_date
            trade_idx = row[1] if len(row) > 1 and row[1] else "1"
            ticker = row[2] if len(row) > 2 and row[2] else prev_ticker
            entry_time = row[3] if len(row) > 3 else ""
            exit_time = row[4] if len(row) > 4 else ""
            side = row[5] if len(row) > 5 else "BUY"
            
            if date_str:
                prev_date = date_str
            if ticker:
                prev_ticker = ticker
                
            if not ticker:
                continue
                
            try:
                price = float(row[6])
            except (ValueError, IndexError):
                price = 0.0
                
            psl_pct = parse_psl_percent(row[7]) if len(row) > 7 else 0.0
            
            # Read exits count / requested lots (9th column)
            target_exits = 1
            if len(row) >= 9 and row[8]:
                try:
                    target_exits = int(float(row[8]))
                except ValueError:
                    target_exits = 1
                    
            category = determine_category(ticker)
            brokerage = calculate_trade_brokerage(category)
            
            if category == 'Gold':
                # Gold calculation: Capital = Rs. 5,000, 30x Exposure = Rs. 150,000
                gold_oz_qty = GOLD_TOTAL_EXPOSURE / (price * GOLD_USD_INR_RATE) if price > 0 else 0.0
                capital_used = GOLD_CAPITAL_LIMIT
                exposure = GOLD_TOTAL_EXPOSURE
                traded_lots = f"{gold_oz_qty:.4f} oz"
                
                gross_pl = exposure * (psl_pct / 100.0)
                net_pl = gross_pl - brokerage
                net_pl_pct = (net_pl / exposure * 100.0)
                
                trade_info = {
                    'Date': date_str,
                    'Trade Index': trade_idx,
                    'Ticker': ticker,
                    'Category': category,
                    'Entry Time': entry_time,
                    'Exit Time': exit_time,
                    'Side': side,
                    'Price ($)': price,
                    'Target Exits': target_exits,
                    'Traded Quantity': traded_lots,
                    'Capital Invested (Rs)': round(capital_used, 2),
                    'Leveraged Exposure (Rs)': round(exposure, 2),
                    'P/L % (Before Brok)': f"{psl_pct:.4f}%",
                    'P/L Rs (Before Brok)': round(gross_pl, 2),
                    'Brokerage (Rs)': round(brokerage, 2),
                    'P/L Rs (After Brok)': round(net_pl, 2),
                    'P/L % (After Brok)': f"{net_pl_pct:.4f}%"
                }
                included_trades.append(trade_info)
                
            else: # Nifty and Crud Options
                multiplier = NIFTY_LOT_SIZE if category == 'Nifty' else CRUD_LOT_SIZE
                # Handle total lot price vs option premium per unit
                one_lot_cost = price if price > 1000 else (price * multiplier)
                
                if category == 'Nifty':
                    # Nifty: Try 2 lots if 2 lots <= 10k, else fallback to 1 lot if 1 lot <= 10k
                    two_lot_cost = one_lot_cost * 2
                    if two_lot_cost <= OPTION_CAPITAL_LIMIT:
                        lots_bought = 2
                        capital_used = two_lot_cost
                    elif one_lot_cost <= OPTION_CAPITAL_LIMIT:
                        lots_bought = 1
                        capital_used = one_lot_cost
                    else:
                        lots_bought = 0
                else: # Crud
                    required_capital = one_lot_cost * target_exits
                    if required_capital <= OPTION_CAPITAL_LIMIT:
                        lots_bought = target_exits
                        capital_used = required_capital
                    elif one_lot_cost <= OPTION_CAPITAL_LIMIT:
                        lots_bought = 1
                        capital_used = one_lot_cost
                    else:
                        lots_bought = 0
                        
                if lots_bought == 0:
                    skipped_info = {
                        'Date': date_str,
                        'Ticker': ticker,
                        'Price': price,
                        'Requested Exits': target_exits,
                        'Required Capital': round(one_lot_cost, 2),
                        'Reason': f"1 Lot cost Rs.{one_lot_cost:,.2f} > Rs.10,000 capital limit"
                    }
                    skipped_trades.append(skipped_info)
                else:
                    exposure = capital_used
                    gross_pl = exposure * (psl_pct / 100.0)
                    net_pl = gross_pl - brokerage
                    net_pl_pct = (net_pl / exposure * 100.0)
                    
                    trade_info = {
                        'Date': date_str,
                        'Trade Index': trade_idx,
                        'Ticker': ticker,
                        'Category': category,
                        'Entry Time': entry_time,
                        'Exit Time': exit_time,
                        'Side': side,
                        'Price ($)': price,
                        'Target Exits': target_exits,
                        'Traded Quantity': f"{lots_bought} Lot(s)",
                        'Capital Invested (Rs)': round(capital_used, 2),
                        'Leveraged Exposure (Rs)': round(exposure, 2),
                        'P/L % (Before Brok)': f"{psl_pct:.2f}%",
                        'P/L Rs (Before Brok)': round(gross_pl, 2),
                        'Brokerage (Rs)': round(brokerage, 2),
                        'P/L Rs (After Brok)': round(net_pl, 2),
                        'P/L % (After Brok)': f"{net_pl_pct:.2f}%"
                    }
                    included_trades.append(trade_info)

    # Write ONLY included trades to output CSV file
    fieldnames = [
        'Date', 'Trade Index', 'Ticker', 'Category', 'Entry Time', 'Exit Time', 
        'Side', 'Price ($)', 'Target Exits', 'Traded Quantity', 'Capital Invested (Rs)', 'Leveraged Exposure (Rs)',
        'P/L % (Before Brok)', 'P/L Rs (Before Brok)', 
        'Brokerage (Rs)', 
        'P/L Rs (After Brok)', 'P/L % (After Brok)'
    ]
    
    with open(output_csv, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(included_trades)
        
    print(f"Processed {len(included_trades) + len(skipped_trades)} total trades:")
    print(f" - Included Trades: {len(included_trades)}")
    print(f" - Skipped Trades: {len(skipped_trades)}")
    print(f"Saved included trades to '{output_csv}'.\n")
    
    display_report(included_trades, skipped_trades)

def display_report(trades, skipped_trades):
    header_fmt = f"{'#':<3} | {'Date':<10} | {'Ticker':<16} | {'Cat':<6} | {'Qty / Lots':<12} | {'Capital(Rs)':<11} | {'P/L Before Brok':<17} | {'Brokerage':<9} | {'P/L After Brok':<19} | {'Impact':<8}"
    
    print("=" * 128)
    print(f"{'PAPER TRADING FULL 50-TRADE P&L REPORT':^128}")
    print("=" * 128)
    print(header_fmt)
    print("-" * 128)
    
    tot_invest = 0.0
    tot_exposure = 0.0
    tot_gross = 0.0
    tot_brok = 0.0
    tot_net = 0.0
    
    gross_wins = 0
    net_wins = 0
    
    category_summary = {
        'Nifty': {'count': 0, 'invest': 0.0, 'exposure': 0.0, 'gross': 0.0, 'brok': 0.0, 'net': 0.0},
        'Crud': {'count': 0, 'invest': 0.0, 'exposure': 0.0, 'gross': 0.0, 'brok': 0.0, 'net': 0.0},
        'Gold': {'count': 0, 'invest': 0.0, 'exposure': 0.0, 'gross': 0.0, 'brok': 0.0, 'net': 0.0}
    }
    
    for idx, t in enumerate(trades, 1):
        invest = t['Capital Invested (Rs)']
        exposure = t['Leveraged Exposure (Rs)']
        gross_rs = t['P/L Rs (Before Brok)']
        gross_pct = t['P/L % (Before Brok)']
        brok = t['Brokerage (Rs)']
        net_rs = t['P/L Rs (After Brok)']
        net_pct = t['P/L % (After Brok)']
        impact = net_rs - gross_rs
        
        tot_invest += invest
        tot_exposure += exposure
        tot_gross += gross_rs
        tot_brok += brok
        tot_net += net_rs
        
        if gross_rs > 0:
            gross_wins += 1
        if net_rs > 0:
            net_wins += 1
            
        cat = t['Category']
        if cat in category_summary:
            category_summary[cat]['count'] += 1
            category_summary[cat]['invest'] += invest
            category_summary[cat]['exposure'] += exposure
            category_summary[cat]['gross'] += gross_rs
            category_summary[cat]['brok'] += brok
            category_summary[cat]['net'] += net_rs
            
        gross_str = f"Rs.{gross_rs:>7.2f} ({gross_pct:>7})"
        net_str = f"Rs.{net_rs:>7.2f} ({net_pct:>7})"
        qty_str = t['Traded Quantity'].split('(')[0].strip()
        
        print(f"{idx:<3} | {t['Date']:<10} | {t['Ticker']:<16} | {t['Category']:<6} | {qty_str:<12} | {invest:<11.2f} | {gross_str:<17} | Rs.{brok:<6.2f} | {net_str:<19} | Rs.{impact:<7.2f}")

    print("-" * 128)
    tot_gross_pct = (tot_gross / tot_exposure * 100.0) if tot_exposure > 0 else 0.0
    tot_net_pct = (tot_net / tot_exposure * 100.0) if tot_exposure > 0 else 0.0
    
    tot_gross_str = f"Rs.{tot_gross:>7.2f} ({tot_gross_pct:.2f}%)"
    tot_net_str = f"Rs.{tot_net:>7.2f} ({tot_net_pct:.2f}%)"
    
    print(f"{'TOTALS':<57} | {tot_invest:<11.2f} | {tot_gross_str:<17} | Rs.{tot_brok:<6.2f} | {tot_net_str:<19} | Rs.{-tot_brok:<7.2f}")
    print("=" * 128)
    
    if skipped_trades:
        print("\n" + "!" * 105)
        print(f"{'SKIPPED TRADES (EXCEEDED RS. 10,000 CAPITAL LIMIT)':^105}")
        print("!" * 105)
        for st in skipped_trades:
            print(f" -> Date: {st['Date']} | Ticker: {st['Ticker']} | Price: {st['Price']} | Exits: {st['Requested Exits']} | {st['Reason']}")
        print("!" * 105)

    print("\n" + "=" * 65)
    print(f"{'OVERALL SUMMARY METRICS (FULL 50 TRADES DATASET)':^65}")
    print("=" * 65)
    print(f" Total Included Trades      : {len(trades)}")
    print(f" Total Skipped Trades       : {len(skipped_trades)}")
    print(f" Total Capital Invested     : Rs. {tot_invest:,.2f}")
    print(f" Total Position Exposure    : Rs. {tot_exposure:,.2f}")
    print(f" Position Return BEFORE Brok : Rs. {tot_gross:+,.2f} ({tot_gross_pct:+.2f}%)")
    print(f" Total Brokerage & Charges   : Rs. {tot_brok:,.2f}")
    print(f" Position Return AFTER Brok  : Rs. {tot_net:+,.2f} ({tot_net_pct:+.2f}%)")
    print(f" Margin Return (Net ROI)    : {((tot_net / tot_invest)*100):+.2f}%")
    print("-" * 65)
    print(f" Winning Trades (Before)    : {gross_wins} / {len(trades)} ({(gross_wins/len(trades)*100):.1f}%)")
    print(f" Winning Trades (After)     : {net_wins} / {len(trades)} ({(net_wins/len(trades)*100):.1f}%)")
    print("=" * 65)

    print("\n" + "=" * 85)
    print(f"{'CATEGORY BREAKDOWN (FULL 50 TRADES DATASET)':^85}")
    print("=" * 85)
    print(f"{'Category':<10} | {'Trades':<6} | {'Exposure (Rs)':<14} | {'Before Brok P/L':<18} | {'Brokerage':<9} | {'After Brok P/L':<18}")
    print("-" * 85)
    for c_name, c_data in category_summary.items():
        g_pct = (c_data['gross'] / c_data['exposure'] * 100) if c_data['exposure'] > 0 else 0.0
        n_pct = (c_data['net'] / c_data['exposure'] * 100) if c_data['exposure'] > 0 else 0.0
        g_str = f"Rs.{c_data['gross']:>7.2f} ({g_pct:>6.4f}%)"
        n_str = f"Rs.{c_data['net']:>7.2f} ({n_pct:>6.4f}%)"
        print(f"{c_name:<10} | {c_data['count']:<6} | {c_data['exposure']:<14.2f} | {g_str:<18} | Rs.{c_data['brok']:<6.2f} | {n_str:<18}")
    print("=" * 85)

if __name__ == "__main__":
    process_paper_trading()
