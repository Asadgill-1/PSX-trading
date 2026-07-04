"""Named strategy modules — researched, source-cited (spec §1).

Each module is a documented, publicly-verifiable idea from Pakistani market
practice. The Scout must tag every idea with one of these names; nightly
reflection re-weights them by realized results (strategy_weights table).

Citations reviewed 2026-07-05. These describe WHERE the idea comes from —
performance claims are the sources', not ours.
"""

STRATEGIES = [
    {
        "name": "sector-rotation",
        "summary": "Follow money rotating into sectors brokerages rate overweight when "
                   "interest rates fall (banks, E&P, fertilizer, cement, OMCs).",
        # source: AKD Securities "Pakistan Strategy CY2025" (research.akdsl.com,
        # AKD_Detail_Report_Dec_21_2024.pdf): overweight banks/E&P/fertilizers/cement/
        # OMC/autos/textiles/tech on lower rates + macro stability; power/chemicals underweight.
        "signal_hint": "sector peers moving together on above-average volume",
    },
    {
        "name": "heavyweight-follow",
        "summary": "KSE-100 is driven by a handful of heavyweights; when index leaders "
                   "move with volume, followers in the same sector often lag by days.",
        # source: Profit / Pakistan Today FY26 review (profit.pakistantoday.com.pk,
        # 2026-07-01): top index contribution from UBL, HBL, Engro Holdings, MCB,
        # Engro Fertiliser, Fauji Fertiliser — index concentration is documented.
        "signal_hint": "index heavyweight breaking out while sector peers have not moved yet",
    },
    {
        "name": "dividend-capture",
        "summary": "Buy high-dividend payers ahead of book-closure/entitlement dates; "
                   "PSX has a deep high-yield cohort and payouts anchor prices.",
        # source: PSX investor education on dividends (psx.com.pk resources-and-tools);
        # high-yield screens are a standard product on sarmaaya.pk and TradingView's
        # Pakistan high-dividend movers page — the cohort is public and screenable.
        "signal_hint": "yield well above market average with announced payout dates",
    },
    {
        "name": "result-season-momentum",
        "summary": "Around quarterly result announcements, strong earnings surprises "
                   "keep moving for days; brokerages publish result previews that "
                   "concentrate attention on expected beats.",
        # source: standard practice of PK brokerage research (Topline Securities,
        # AKD result previews — topline.com.pk research portal); announcement dates
        # are public on the PSX announcements feed.
        "signal_hint": "price+volume reaction on/after a results announcement",
    },
    {
        "name": "volume-momentum",
        "summary": "Unusual volume with a firm price close often precedes short-term "
                   "continuation; classic momentum screen applied to PSX liquidity.",
        # source: generic, publicly documented momentum screening (documented across
        # brokerage technical notes); encoded here as the baseline quantitative screen.
        "signal_hint": "volume multiple of recent average, close near day high",
    },
    {
        "name": "value-pe",
        "summary": "Low price-to-earnings versus sector with a catalyst; buys years of "
                   "profit cheaply but needs a reason the discount closes.",
        # source: generic value screening as practiced in PK brokerage fundamental
        # coverage (Topline/AKD company notes routinely lead with P/E vs sector).
        "signal_hint": "P/E below sector norm plus a concrete catalyst in the data",
    },
]


def seed_weights(conn) -> None:
    """Insert any missing strategy rows at neutral weight 1.0 (idempotent)."""
    from .. import db
    for s in STRATEGIES:
        conn.execute(
            "INSERT OR IGNORE INTO strategy_weights(strategy, weight, notes, updated_at)"
            " VALUES (?, 1.0, ?, ?)",
            (s["name"], s["summary"], db.utcnow()),
        )
    conn.commit()


def prompt_block() -> str:
    """Strategy menu injected into the Scout prompt."""
    lines = ["Allowed strategy tags (pick the single best fit for each idea):"]
    for s in STRATEGIES:
        lines.append(f'- "{s["name"]}": {s["summary"]} Signal: {s["signal_hint"]}')
    return "\n".join(lines)
