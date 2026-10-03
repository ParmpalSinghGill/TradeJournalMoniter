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

STRATEGY_KEYS = ('exit1', 'exit2', 'exit3', 'blend')
STRATEGY_LABELS = {
    'exit1': 'Exit 1 (full position)',
    'exit2': 'Exit 2 (full position)',
    'exit3': 'Exit 3 (full position)',
    'blend': '3-Exit scale-out (equal split)',
}


def parse_psl_percent(val_str):
    """
    Parses P/SL % string into a float percentage value.
    Handles standard percentages ("8.10%", "-3.99"), floats,
    and Excel time format anomalies ("05:18:00 AM" -> 5.18%).
    Returns None when the cell is blank so missing exits stay missing.
    """
    if val_str is None:
        return None

    val_str = str(val_str).strip()
    if not val_str:
        return None

    if val_str.endswith('%'):
        val_str = val_str[:-1].strip()
        if not val_str:
            return None

    time_match = re.match(r'^(\d{1,2}):(\d{2}):(\d{2})\s*(AM|PM)$', val_str, re.IGNORECASE)
    if time_match:
        hours = int(time_match.group(1))
        minutes = int(time_match.group(2))
        return float(f"{hours}.{minutes:02d}")

    try:
        return float(val_str)
    except ValueError:
        return None


def normalize_header(name):
    return re.sub(r'[^a-z0-9]+', '', str(name).strip().lower())


def build_header_map(header_row):
    mapping = {}
    for idx, name in enumerate(header_row):
        mapping[normalize_header(name)] = idx
    return mapping


def cell(row, header_map, *aliases, default=""):
    for alias in aliases:
        idx = header_map.get(normalize_header(alias))
        if idx is not None and idx < len(row):
            return row[idx]
    return default


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


def format_pct(value):
    if value is None:
        return ""
    return f"{value:.2f}%"


def calc_pl(exposure, pct, brokerage):
    """Return gross/net rupee and percent P/L for a full-position exit at `pct`."""
    if pct is None or exposure <= 0:
        return None
    gross = exposure * (pct / 100.0)
    net = gross - brokerage
    return {
        'gross_pct': pct,
        'gross_rs': round(gross, 2),
        'net_rs': round(net, 2),
        'net_pct': (net / exposure) * 100.0,
    }


def size_position(category, price, target_exits):
    """
    Apply capital rules and return lots, capital, exposure, quantity label.
    lots_bought == 0 means the trade exceeds the capital limit.
    """
    if category == 'Gold':
        gold_oz_qty = GOLD_TOTAL_EXPOSURE / (price * GOLD_USD_INR_RATE) if price > 0 else 0.0
        return {
            'lots_bought': 1,
            'capital_used': GOLD_CAPITAL_LIMIT,
            'exposure': GOLD_TOTAL_EXPOSURE,
            'traded_qty': f"{gold_oz_qty:.4f} oz",
            'one_lot_cost': GOLD_CAPITAL_LIMIT,
        }

    multiplier = NIFTY_LOT_SIZE if category == 'Nifty' else CRUD_LOT_SIZE
    one_lot_cost = price if price > 1000 else (price * multiplier)

    if category == 'Nifty':
        two_lot_cost = one_lot_cost * 2
        if two_lot_cost <= OPTION_CAPITAL_LIMIT:
            lots_bought = 2
            capital_used = two_lot_cost
        elif one_lot_cost <= OPTION_CAPITAL_LIMIT:
            lots_bought = 1
            capital_used = one_lot_cost
        else:
            lots_bought = 0
            capital_used = 0.0
    else:
        if one_lot_cost <= 0:
            lots_bought = 0
            capital_used = 0.0
        else:
            max_affordable = int(OPTION_CAPITAL_LIMIT // one_lot_cost)
            lots_bought = min(target_exits, max_affordable)
            capital_used = lots_bought * one_lot_cost

    return {
        'lots_bought': lots_bought,
        'capital_used': capital_used,
        'exposure': capital_used,
        'traded_qty': f"{lots_bought} Lot(s)" if lots_bought else "",
        'one_lot_cost': one_lot_cost,
    }


def flatten_pl(prefix, pl):
    if not pl:
        return {
            f'{prefix} P/L % (Before Brok)': "",
            f'{prefix} P/L Rs (Before Brok)': "",
            f'{prefix} P/L Rs (After Brok)': "",
            f'{prefix} P/L % (After Brok)': "",
        }
    return {
        f'{prefix} P/L % (Before Brok)': format_pct(pl['gross_pct']),
        f'{prefix} P/L Rs (Before Brok)': pl['gross_rs'],
        f'{prefix} P/L Rs (After Brok)': pl['net_rs'],
        f'{prefix} P/L % (After Brok)': format_pct(pl['net_pct']),
    }


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
        if not header:
            print("Error: Input CSV has no header row.")
            return
        header_map = build_header_map(header)

        for row in reader:
            if not row or len(row) < 7:
                continue

            row = [item.strip() for item in row]

            date_str = cell(row, header_map, "Date") or prev_date
            trade_idx = cell(row, header_map, "Trade Index") or "1"
            ticker = cell(row, header_map, "Ticker") or prev_ticker
            entry_time = cell(row, header_map, "Entry Time")
            exit_time = cell(row, header_map, "Exit Time")
            side = cell(row, header_map, "Side") or "BUY"

            if date_str:
                prev_date = date_str
            if ticker:
                prev_ticker = ticker

            if not ticker:
                continue

            try:
                price = float(cell(row, header_map, "Price", "Price ($)"))
            except (ValueError, TypeError):
                price = 0.0

            exit1_pct = parse_psl_percent(cell(row, header_map, "Exit 1 %", "Exit1", "Exit 1", "P/SL %"))
            exit2_pct = parse_psl_percent(cell(row, header_map, "Exit2", "Exit 2 %", "Exit 2"))
            exit3_pct = parse_psl_percent(cell(row, header_map, "Exit3", "Exit 3 %", "Exit 3"))
            rr_raw = cell(row, header_map, "RR")
            rr_val = parse_psl_percent(rr_raw)

            filled_exits = [pct for pct in (exit1_pct, exit2_pct, exit3_pct) if pct is not None]
            # Fall back to old "number of exits" column when present; otherwise
            # size Crude lots to the number of recorded exit levels.
            target_exits = max(1, len(filled_exits))
            exits_col = cell(row, header_map, "numer of exits", "number of exits", "Target Exits")
            if exits_col:
                try:
                    target_exits = max(1, int(float(exits_col)))
                except ValueError:
                    pass

            category = determine_category(ticker)
            brokerage = calculate_trade_brokerage(category)
            sized = size_position(category, price, target_exits)

            if sized['lots_bought'] == 0:
                skipped_trades.append({
                    'Date': date_str,
                    'Ticker': ticker,
                    'Price': price,
                    'Requested Exits': target_exits,
                    'Required Capital': round(sized['one_lot_cost'], 2),
                    'Reason': f"1 Lot cost Rs.{sized['one_lot_cost']:,.2f} > Rs.10,000 capital limit",
                })
                continue

            exposure = sized['exposure']
            capital_used = sized['capital_used']
            blend_pct = (sum(filled_exits) / len(filled_exits)) if filled_exits else 0.0

            pl_exit1 = calc_pl(exposure, exit1_pct, brokerage)
            pl_exit2 = calc_pl(exposure, exit2_pct, brokerage)
            pl_exit3 = calc_pl(exposure, exit3_pct, brokerage)
            pl_blend = calc_pl(exposure, blend_pct, brokerage) if filled_exits else None

            trade_info = {
                'Date': date_str,
                'Trade Index': trade_idx,
                'Ticker': ticker,
                'Category': category,
                'Entry Time': entry_time,
                'Exit Time': exit_time,
                'Side': side,
                'Price ($)': price,
                'Exit 1 %': format_pct(exit1_pct),
                'Exit 2 %': format_pct(exit2_pct),
                'Exit 3 %': format_pct(exit3_pct),
                'RR': (f"{rr_val:.2f}" if rr_val is not None else rr_raw),
                'Filled Exits': len(filled_exits),
                'Target Exits': target_exits,
                'Traded Quantity': sized['traded_qty'],
                'Capital Invested (Rs)': round(capital_used, 2),
                'Leveraged Exposure (Rs)': round(exposure, 2),
                'Brokerage (Rs)': round(brokerage, 2),
                '_pl': {
                    'exit1': pl_exit1,
                    'exit2': pl_exit2,
                    'exit3': pl_exit3,
                    'blend': pl_blend,
                },
            }
            trade_info.update(flatten_pl('Exit 1', pl_exit1))
            trade_info.update(flatten_pl('Exit 2', pl_exit2))
            trade_info.update(flatten_pl('Exit 3', pl_exit3))
            trade_info.update(flatten_pl('Scale-out', pl_blend))
            # Keep legacy single-P/L columns pointing at the 3-exit scale-out result.
            if pl_blend:
                trade_info['P/L % (Before Brok)'] = format_pct(pl_blend['gross_pct'])
                trade_info['P/L Rs (Before Brok)'] = pl_blend['gross_rs']
                trade_info['P/L Rs (After Brok)'] = pl_blend['net_rs']
                trade_info['P/L % (After Brok)'] = format_pct(pl_blend['net_pct'])
            else:
                trade_info['P/L % (Before Brok)'] = ""
                trade_info['P/L Rs (Before Brok)'] = ""
                trade_info['P/L Rs (After Brok)'] = ""
                trade_info['P/L % (After Brok)'] = ""

            included_trades.append(trade_info)

    fieldnames = [
        'Date', 'Trade Index', 'Ticker', 'Category', 'Entry Time', 'Exit Time',
        'Side', 'Price ($)', 'Exit 1 %', 'Exit 2 %', 'Exit 3 %', 'RR',
        'Filled Exits', 'Target Exits', 'Traded Quantity',
        'Capital Invested (Rs)', 'Leveraged Exposure (Rs)', 'Brokerage (Rs)',
        'Exit 1 P/L % (Before Brok)', 'Exit 1 P/L Rs (Before Brok)',
        'Exit 1 P/L Rs (After Brok)', 'Exit 1 P/L % (After Brok)',
        'Exit 2 P/L % (Before Brok)', 'Exit 2 P/L Rs (Before Brok)',
        'Exit 2 P/L Rs (After Brok)', 'Exit 2 P/L % (After Brok)',
        'Exit 3 P/L % (Before Brok)', 'Exit 3 P/L Rs (Before Brok)',
        'Exit 3 P/L Rs (After Brok)', 'Exit 3 P/L % (After Brok)',
        'Scale-out P/L % (Before Brok)', 'Scale-out P/L Rs (Before Brok)',
        'Scale-out P/L Rs (After Brok)', 'Scale-out P/L % (After Brok)',
        'P/L % (Before Brok)', 'P/L Rs (Before Brok)',
        'P/L Rs (After Brok)', 'P/L % (After Brok)',
    ]

    csv_rows = []
    for trade in included_trades:
        csv_rows.append({k: trade.get(k, "") for k in fieldnames})

    with open(output_csv, mode='w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(csv_rows)

    print(f"Processed {len(included_trades) + len(skipped_trades)} total trades:")
    print(f" - Included Trades: {len(included_trades)}")
    print(f" - Skipped Trades: {len(skipped_trades)}")
    print(f"Saved included trades to '{output_csv}'.\n")

    display_report(included_trades, skipped_trades)


def strategy_stats(trades, key, require_all_three=False):
    stats = {
        'count': 0,
        'wins': 0,
        'invest': 0.0,
        'exposure': 0.0,
        'gross': 0.0,
        'brok': 0.0,
        'net': 0.0,
        'win_rs': 0.0,
        'loss_rs': 0.0,
    }
    for trade in trades:
        if require_all_three:
            pls = trade['_pl']
            if not (pls.get('exit1') and pls.get('exit2') and pls.get('exit3')):
                continue
        pl = trade['_pl'].get(key)
        if not pl:
            continue
        stats['count'] += 1
        stats['invest'] += trade['Capital Invested (Rs)']
        stats['exposure'] += trade['Leveraged Exposure (Rs)']
        stats['gross'] += pl['gross_rs']
        stats['brok'] += trade['Brokerage (Rs)']
        stats['net'] += pl['net_rs']
        if pl['net_rs'] > 0:
            stats['wins'] += 1
            stats['win_rs'] += pl['net_rs']
        elif pl['net_rs'] < 0:
            stats['loss_rs'] += abs(pl['net_rs'])
    return stats


def print_strategy_table(title, trades, require_all_three=False):
    print("\n" + "=" * 118)
    print(f"{title:^118}")
    print("=" * 118)
    header = (
        f"{'Strategy':<32} | {'Trades':<6} | {'Win Rate':<9} | "
        f"{'Gross P/L':<14} | {'Brokerage':<10} | {'Net P/L':<14} | {'Net ROI':<9} | {'PF':<6}"
    )
    print(header)
    print("-" * 118)

    ranked = []
    for key in STRATEGY_KEYS:
        stats = strategy_stats(trades, key, require_all_three=require_all_three)
        ranked.append((key, stats))

    best_key = None
    best_net = None
    for key, stats in ranked:
        if stats['count'] == 0:
            print(
                f"{STRATEGY_LABELS[key]:<32} | {'-':<6} | {'-':<9} | "
                f"{'-':<14} | {'-':<10} | {'-':<14} | {'-':<9} | {'-':<6}"
            )
            continue
        win_rate = (stats['wins'] / stats['count'] * 100.0) if stats['count'] else 0.0
        roi = (stats['net'] / stats['invest'] * 100.0) if stats['invest'] else 0.0
        profit_factor = (stats['win_rs'] / stats['loss_rs']) if stats['loss_rs'] > 0 else (float('inf') if stats['win_rs'] > 0 else 0.0)
        pf_str = "∞" if profit_factor == float('inf') else f"{profit_factor:.2f}"
        print(
            f"{STRATEGY_LABELS[key]:<32} | {stats['count']:<6} | {win_rate:>6.1f}%   | "
            f"Rs.{stats['gross']:>9.2f} | Rs.{stats['brok']:<7.2f} | "
            f"Rs.{stats['net']:>9.2f} | {roi:>+7.2f}% | {pf_str:<6}"
        )
        if best_net is None or stats['net'] > best_net:
            best_net = stats['net']
            best_key = key

    print("=" * 118)
    if best_key:
        print(f" Best by net P/L: {STRATEGY_LABELS[best_key]}  (Rs. {best_net:+,.2f})")


def display_report(trades, skipped_trades):
    print("=" * 150)
    print(f"{'PAPER TRADING 3-EXIT STRATEGY P&L REPORT':^150}")
    print("=" * 150)
    header_fmt = (
        f"{'#':<3} | {'Date':<10} | {'Ticker':<16} | {'Qty':<10} | {'Capital':<9} | "
        f"{'Ex1%':<8} | {'Ex2%':<8} | {'Ex3%':<8} | "
        f"{'Scale-out':<18} | {'Exit 1':<18} | {'Exit 2':<18} | {'Exit 3':<18}"
    )
    print(header_fmt)
    print("-" * 150)

    for idx, trade in enumerate(trades, 1):
        qty_str = trade['Traded Quantity'].split('(')[0].strip()
        invest = trade['Capital Invested (Rs)']

        def cell_pl(pl):
            if not pl:
                return f"{'-':<18}"
            return f"Rs.{pl['net_rs']:>8.2f} ({pl['net_pct']:>6.2f}%)"

        print(
            f"{idx:<3} | {trade['Date']:<10} | {trade['Ticker']:<16} | {qty_str:<10} | "
            f"{invest:<9.2f} | {trade['Exit 1 %'] or '-':<8} | {trade['Exit 2 %'] or '-':<8} | "
            f"{trade['Exit 3 %'] or '-':<8} | "
            f"{cell_pl(trade['_pl']['blend'])} | {cell_pl(trade['_pl']['exit1'])} | "
            f"{cell_pl(trade['_pl']['exit2'])} | {cell_pl(trade['_pl']['exit3'])}"
        )

    print("-" * 150)

    blend_stats = strategy_stats(trades, 'blend')
    tot_invest = blend_stats['invest']
    tot_exposure = blend_stats['exposure']
    tot_gross = blend_stats['gross']
    tot_brok = blend_stats['brok']
    tot_net = blend_stats['net']
    tot_gross_pct = (tot_gross / tot_exposure * 100.0) if tot_exposure else 0.0
    tot_net_pct = (tot_net / tot_exposure * 100.0) if tot_exposure else 0.0
    tot_roi = (tot_net / tot_invest * 100.0) if tot_invest else 0.0

    print(
        f"{'SCALE-OUT TOTALS':<57} | {tot_invest:<9.2f} | "
        f"Gross Rs.{tot_gross:>8.2f} ({tot_gross_pct:.2f}%) | "
        f"Brok Rs.{tot_brok:<7.2f} | "
        f"Net Rs.{tot_net:>8.2f} ({tot_net_pct:.2f}%)"
    )
    print("=" * 150)

    if skipped_trades:
        print("\n" + "!" * 105)
        print(f"{'SKIPPED TRADES (EXCEEDED RS. 10,000 CAPITAL LIMIT)':^105}")
        print("!" * 105)
        for skipped in skipped_trades:
            print(
                f" -> Date: {skipped['Date']} | Ticker: {skipped['Ticker']} | "
                f"Price: {skipped['Price']} | Exits: {skipped['Requested Exits']} | {skipped['Reason']}"
            )
        print("!" * 105)

    print("\n" + "=" * 70)
    print(f"{'3-EXIT SCALE-OUT SUMMARY (ACTUAL STRATEGY)':^70}")
    print("=" * 70)
    print(f" Total Included Trades      : {len(trades)}")
    print(f" Total Skipped Trades       : {len(skipped_trades)}")
    print(f" Total Capital Invested     : Rs. {tot_invest:,.2f}")
    print(f" Total Position Exposure    : Rs. {tot_exposure:,.2f}")
    print(f" Position Return BEFORE Brok : Rs. {tot_gross:+,.2f} ({tot_gross_pct:+.2f}%)")
    print(f" Total Brokerage & Charges   : Rs. {tot_brok:,.2f}")
    print(f" Position Return AFTER Brok  : Rs. {tot_net:+,.2f} ({tot_net_pct:+.2f}%)")
    print(f" Margin Return (Net ROI)    : {tot_roi:+.2f}%")
    if trades:
        print(
            f" Winning Trades (Scale-out) : {blend_stats['wins']} / {len(trades)} "
            f"({(blend_stats['wins'] / len(trades) * 100):.1f}%)"
        )
    print("=" * 70)

    print_strategy_table(
        "STRATEGY COMPARISON - EACH EXIT AS 100% OF THE POSITION",
        trades,
        require_all_three=False,
    )
    print_strategy_table(
        "SAME-SAMPLE COMPARISON - ONLY TRADES WITH ALL 3 EXITS FILLED",
        trades,
        require_all_three=True,
    )

    print("\n" + "=" * 100)
    print(f"{'CATEGORY BREAKDOWN (SCALE-OUT)':^100}")
    print("=" * 100)
    print(
        f"{'Category':<10} | {'Trades':<6} | {'Exposure (Rs)':<14} | "
        f"{'Before Brok P/L':<20} | {'Brokerage':<9} | {'After Brok P/L':<20}"
    )
    print("-" * 100)
    for cat_name in ('Nifty', 'Crud', 'Gold'):
        cat_trades = [t for t in trades if t['Category'] == cat_name]
        stats = strategy_stats(cat_trades, 'blend')
        g_pct = (stats['gross'] / stats['exposure'] * 100) if stats['exposure'] else 0.0
        n_pct = (stats['net'] / stats['exposure'] * 100) if stats['exposure'] else 0.0
        g_str = f"Rs.{stats['gross']:>8.2f} ({g_pct:>6.2f}%)"
        n_str = f"Rs.{stats['net']:>8.2f} ({n_pct:>6.2f}%)"
        print(
            f"{cat_name:<10} | {stats['count']:<6} | {stats['exposure']:<14.2f} | "
            f"{g_str:<20} | Rs.{stats['brok']:<6.2f} | {n_str:<20}"
        )
    print("=" * 100)


if __name__ == "__main__":
    process_paper_trading()
