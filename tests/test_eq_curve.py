from StemSamplePrep import EqCurveEditor


def test_eq_bell_width_responds_across_high_q_range():
    assert EqCurveEditor._bell_width(5.0) > EqCurveEditor._bell_width(10.0)


def test_cut_filter_response_uses_q():
    low_q_db = EqCurveEditor._cut_filter_db("hp", 100.0, 100.0, 0.7)
    high_q_db = EqCurveEditor._cut_filter_db("hp", 100.0, 100.0, 5.0)
    assert high_q_db > low_q_db
