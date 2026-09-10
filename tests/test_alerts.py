"""ALERT-2 (in-place poll revisions), ALERT-4 (cumulative drift), ALERT-5/DQ-3
(history that shrank) and FS-7 (a missed slot)."""
import datetime

import support

refresh = support.load("refresh")


def base(**kw):
    s = {"run_utc": "2026-08-29T19:00:00Z", "days_to_election": 66,
         "consensus_dem": 0.80, "pm_dem": 0.82, "kalshi_dem": 0.78,
         "pm_history_days": 235, "kalshi_history_days": 412,
         "mov_history_days": 18, "seat_history_days": 10,
         "pm_series_days": {"D": 235, "R": 235}, "k_series_days": {"D": 412, "R": 412},
         "mov_series_days": {"Democrat 0-3%": 18, "Democrat 18%+": 18},
         "seat_series_days": {"KXHOUSEWINSTATE-PAD-E9": 10},
         "poll_ids": ["p1"], "poll_values": {"p1": {"general/Bob Brooks": "47"}},
         "polls_total": 5, "polls_general": 1,
         "kalshi_status": {"D": "active", "R": "active"}}
    s.update(kw)
    return s


def now_iso(hours_ago=0.0):
    t = datetime.datetime.utcnow() - datetime.timedelta(hours=hours_ago)
    return t.isoformat(timespec="seconds") + "Z"


# ------------------------------------------------------------------- ALERT-2

def test_alert2_poll_revised_under_the_same_id_is_alerted():
    """One general poll in this race: a silent revision moves the whole average."""
    prev = base(run_utc=now_iso(6))
    cur = base(poll_values={"p1": {"general/Bob Brooks": "51"}})
    notes, alerts = refresh.diff(prev, cur)
    hit = [a for a in alerts if "REVISED IN PLACE" in a]
    assert hit, alerts
    assert "p1" in hit[0] and "47" in hit[0] and "51" in hit[0], hit


def test_alert2_unchanged_polls_do_not_alert():
    prev = base(run_utc=now_iso(6))
    notes, alerts = refresh.diff(prev, base())
    assert not any("REVISED" in a for a in alerts), alerts


def test_alert2_a_brand_new_poll_id_is_still_the_new_poll_alert():
    prev = base(run_utc=now_iso(6))
    cur = base(poll_ids=["p1", "p2"],
               poll_values={"p1": {"general/Bob Brooks": "47"}, "p2": {"general/x": "40"}})
    notes, alerts = refresh.diff(prev, cur)
    assert any("NEW POLL(S)" in a for a in alerts), alerts
    assert not any("REVISED IN PLACE" in a for a in alerts), alerts


# ------------------------------------------------------------------- ALERT-4

def test_alert4_drift_split_across_runs_trips_the_threshold():
    """+3pp then +3pp never crosses 5pp in one step, but it is still a 6pp move."""
    trail = [{"run_utc": "2026-08-28T07:12:00Z", "consensus_dem": 0.74,
              "pm_dem": 0.74, "kalshi_dem": 0.74},
             {"run_utc": "2026-08-28T19:12:00Z", "consensus_dem": 0.77,
              "pm_dem": 0.77, "kalshi_dem": 0.77}]
    prev = base(run_utc=now_iso(6), consensus_dem=0.77, pm_dem=0.77, kalshi_dem=0.77, recent=trail)
    cur = base(consensus_dem=0.80, pm_dem=0.80, kalshi_dem=0.80)
    notes, alerts = refresh.diff(prev, cur)
    hit = [a for a in alerts if "CUMULATIVE MOVE" in a and "Consensus" in a]
    assert hit, alerts
    assert "+6.0 pp" in hit[0], hit
    assert not any("LARGE MOVE" in a for a in alerts), "no single step crossed the threshold"


def test_alert4_a_flat_trail_stays_quiet():
    trail = [{"run_utc": "2026-08-28T07:12:00Z", "consensus_dem": 0.795,
              "pm_dem": 0.815, "kalshi_dem": 0.775}]
    prev = base(run_utc=now_iso(6), recent=trail)
    notes, alerts = refresh.diff(prev, base())
    assert not any("CUMULATIVE" in a for a in alerts), alerts


def test_alert4_single_large_step_is_not_double_reported():
    trail = [{"run_utc": "2026-08-28T07:12:00Z", "consensus_dem": 0.70,
              "pm_dem": 0.70, "kalshi_dem": 0.70}]
    prev = base(run_utc=now_iso(6), consensus_dem=0.70, pm_dem=0.70, kalshi_dem=0.70, recent=trail)
    notes, alerts = refresh.diff(prev, base())
    assert len([a for a in alerts if "Consensus" in a]) == 1, alerts


# ------------------------------------------------------------- ALERT-5 / DQ-3

def test_alert5_shrinking_history_alerts_instead_of_reassuring():
    prev = base(run_utc=now_iso(6))
    cur = base(pm_history_days=230)
    notes, alerts = refresh.diff(prev, cur)
    assert any("HISTORY SHRANK" in a for a in alerts), alerts
    assert not any("expected if this ran twice" in n for n in notes), notes


def test_alert5_flat_history_still_gets_the_reassuring_note():
    prev = base(run_utc=now_iso(6))
    notes, alerts = refresh.diff(prev, base())
    assert any("expected if this ran twice" in n for n in notes), notes
    assert not any("HISTORY SHRANK" in a for a in alerts), alerts


def test_dq3_one_bracket_losing_its_history_column_is_alerted():
    """A single failed bracket fetch yields an empty column that reads as blanks."""
    prev = base(run_utc=now_iso(6))
    cur = base(mov_series_days={"Democrat 0-3%": 18, "Democrat 18%+": 0})
    notes, alerts = refresh.diff(prev, cur)
    hit = [a for a in alerts if "HISTORY SHRANK" in a and "Democrat 18%+" in a]
    assert hit, alerts


def test_dq3_a_bracket_vanishing_entirely_is_alerted():
    prev = base(run_utc=now_iso(6))
    cur = base(mov_series_days={"Democrat 0-3%": 18})
    notes, alerts = refresh.diff(prev, cur)
    assert any("Democrat 18%+" in a and "absent entirely" in a for a in alerts), alerts


def test_dq3_ladder_history_totals_are_tracked_too():
    prev = base(run_utc=now_iso(6))
    cur = base(seat_history_days=4)
    notes, alerts = refresh.diff(prev, cur)
    assert any("seat-ladder history" in a for a in alerts), alerts


# --------------------------------------------------------------------- FS-7

def test_fs7_a_long_gap_since_the_previous_run_is_noted():
    notes, alerts = refresh.diff(base(run_utc=now_iso(30)), base())
    assert any("missed" in n for n in notes), notes


def test_fs7_a_normal_gap_is_not_noted():
    notes, alerts = refresh.diff(base(run_utc=now_iso(6)), base())
    assert not any("missed" in n for n in notes), notes


# ------------------------------- existing behaviour that must not regress ----

def test_large_single_step_move_still_alerts():
    prev = base(run_utc=now_iso(6), consensus_dem=0.70)
    notes, alerts = refresh.diff(prev, base())
    assert any("LARGE MOVE" in a and "Consensus" in a for a in alerts), alerts


def test_kalshi_status_change_still_alerts():
    prev = base(run_utc=now_iso(6))
    cur = base(kalshi_status={"D": "settled", "R": "active"})
    notes, alerts = refresh.diff(prev, cur)
    assert any("status changed: active -> settled" in a for a in alerts), alerts


def test_election_day_passing_still_alerts():
    notes, alerts = refresh.diff(base(run_utc=now_iso(6)), base(days_to_election=0))
    assert any("Election day has passed" in a for a in alerts), alerts


def test_arbitrage_alert_fires_when_the_edge_survives_fees():
    cur = base(pair_ask_total=0.90, pair_net_edge=0.075)
    notes, alerts = refresh.diff(base(run_utc=now_iso(6)), cur)
    assert any("ARBITRAGE" in a for a in alerts), alerts
    assert any("NET" in a for a in alerts), alerts


def test_arbitrage_below_fees_is_a_note_not_an_alert():
    """A live run showed 1.00pp gross against 2.44pp of Kalshi fees — a 1.44pp
    LOSS, announced as an arbitrage. Gross edge alone is not a signal."""
    cur = base(pair_ask_total=0.99, pair_net_edge=-0.0144)
    notes, alerts = refresh.diff(base(run_utc=now_iso(6)), cur)
    assert not any("ARBITRAGE" in a for a in alerts), alerts
    assert any("not tradeable" in n for n in notes), notes


def test_large_move_alert_reports_book_depth():
    """6pp on $3 of resting size is noise; the same 6pp on a deep book is news."""
    cur = base(pm_dem=0.90, top_ask_size={"pm_dem": 42.0, "pm_rep": 91.0})
    notes, alerts = refresh.diff(base(run_utc=now_iso(6)), cur)
    move = [a for a in alerts if "LARGE MOVE" in a]
    assert move and "depth" in move[0], alerts


def test_first_run_says_so():
    notes, alerts = refresh.diff(None, base())
    assert any("First recorded run" in n for n in notes), notes
