from engine.ki.scale import propose_flood_probability


def test_q5_gives_level_4():
    p = propose_flood_probability(in_q5=True, in_q20=True, in_q100=True)
    assert p.level == 4
    assert p.label == "Vysoká"
    assert p.is_borderline is False


def test_q20_gives_level_2_and_is_always_borderline():
    """
    Hraniční případ ze zadání: Q20 leží přesně na hranici úrovní 1 a 2,
    proto MUSÍ být vždy označen jako hraniční, s oběma možnostmi.
    """
    p = propose_flood_probability(in_q5=False, in_q20=True, in_q100=True)
    assert p.level == 2
    assert p.label == "Malá"
    assert p.is_borderline is True
    assert p.borderline_alternative_level == 1
    assert p.borderline_alternative_label == "Zanedbatelná"


def test_q100_gives_level_1_not_borderline():
    p = propose_flood_probability(in_q5=False, in_q20=False, in_q100=True)
    assert p.level == 1
    assert p.label == "Zanedbatelná"
    assert p.is_borderline is False


def test_outside_all_zones_gives_level_1_with_note():
    p = propose_flood_probability(in_q5=False, in_q20=False, in_q100=False)
    assert p.level == 1
    assert "mimo" in p.rationale.lower()
    assert p.is_borderline is False


def test_priority_q5_overrides_q20_and_q100():
    """Objekt v Q5 je typicky podmnožina Q20/Q100 - test exploruje, že
    priorita jde od nejpřísnější (Q5) bez ohledu na ostatní flagy."""
    p = propose_flood_probability(in_q5=True, in_q20=False, in_q100=False)
    assert p.level == 4


def test_q20_without_q100_flag_still_works():
    """Edge case: in_q100 by měl být vždy True, když in_q20 je True (Q20
    je podmnožina Q100), ale funkce nesmí na tomhle předpokladu selhat,
    kdyby data byla nekonzistentní."""
    p = propose_flood_probability(in_q5=False, in_q20=True, in_q100=False)
    assert p.level == 2
    assert p.is_borderline is True


def test_all_five_severity_labels_defined():
    from engine.ki.scale import SEVERITY_LABELS, SEVERITY_TEXT
    assert set(SEVERITY_LABELS.keys()) == {1, 2, 3, 4, 5}
    assert set(SEVERITY_TEXT.keys()) == {1, 2, 3, 4, 5}
    assert SEVERITY_LABELS[5] == "Velmi vysoká"
