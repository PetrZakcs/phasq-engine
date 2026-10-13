from engine.trafficability.classify import (
    CLAY_HIGH_PCT,
    PRECIP_72H_RISK_MM,
    RELATIVE_MOISTURE_HIGH_PCT,
    WORLDCOVER_CROPLAND,
    WORLDCOVER_GRASSLAND,
    ClassificationInput,
    classify,
)


def _base_input(**overrides) -> ClassificationInput:
    defaults = dict(
        land_cover_class=WORLDCOVER_CROPLAND,
        reference_source="local_baseline",
        relative_moisture_pct=50.0,
        precip_72h_mm=0.0,
        precip_data_age_days=4,
        clay_pct=20.0,
        sentinel1_scene_date="2026-10-10",
        sentinel1_age_days=3,
        backscatter_jump_detected=False,
    )
    defaults.update(overrides)
    return ClassificationInput(**defaults)


def test_land_cover_none_is_nelze_urcit():
    result = classify(_base_input(land_cover_class=None))
    assert result.classification == "Nelze určit"
    assert "Pravidlo 1" in result.decisive_rule


def test_land_cover_forest_is_nelze_urcit():
    result = classify(_base_input(land_cover_class=10))  # Tree cover
    assert result.classification == "Nelze určit"
    assert "Pravidlo 1" in result.decisive_rule


def test_grassland_is_in_scope():
    result = classify(_base_input(land_cover_class=WORLDCOVER_GRASSLAND))
    assert result.classification != "Nelze určit"


def test_global_fallback_is_nelze_urcit_per_adr008():
    result = classify(_base_input(reference_source="global_fallback"))
    assert result.classification == "Nelze určit"
    assert "ADR-008" in result.decisive_rule


def test_reference_source_none_is_nelze_urcit():
    result = classify(_base_input(reference_source=None))
    assert result.classification == "Nelze určit"


def test_high_moisture_and_high_precip_is_nevhodne():
    result = classify(_base_input(
        relative_moisture_pct=RELATIVE_MOISTURE_HIGH_PCT,
        precip_72h_mm=PRECIP_72H_RISK_MM,
    ))
    assert result.classification == "Nevhodné"
    assert "Pravidlo 3" in result.decisive_rule


def test_high_moisture_only_is_riziko():
    result = classify(_base_input(
        relative_moisture_pct=RELATIVE_MOISTURE_HIGH_PCT,
        precip_72h_mm=0.0,
    ))
    assert result.classification == "Riziko"
    assert "Pravidlo 4" in result.decisive_rule


def test_high_precip_only_is_riziko():
    result = classify(_base_input(
        relative_moisture_pct=10.0,
        precip_72h_mm=PRECIP_72H_RISK_MM,
    ))
    assert result.classification == "Riziko"


def test_low_moisture_low_precip_is_vhodne():
    result = classify(_base_input(relative_moisture_pct=10.0, precip_72h_mm=0.0))
    assert result.classification == "Vhodné"
    assert "Pravidlo 5" in result.decisive_rule


def test_just_below_moisture_threshold_is_not_high():
    """Hraniční případ: práh je >=, ne >. Hodnota těsně pod prahem nesmí spustit pravidlo 3/4."""
    result = classify(_base_input(
        relative_moisture_pct=RELATIVE_MOISTURE_HIGH_PCT - 0.1,
        precip_72h_mm=0.0,
    ))
    assert result.classification == "Vhodné"


def test_exactly_at_moisture_threshold_counts_as_high():
    """Hraniční případ: hodnota přesně na prahu MUSÍ počítat jako 'vysoká' (>=)."""
    result = classify(_base_input(
        relative_moisture_pct=RELATIVE_MOISTURE_HIGH_PCT,
        precip_72h_mm=0.0,
    ))
    assert result.classification == "Riziko"


def test_clay_bumps_vhodne_to_riziko():
    result = classify(_base_input(
        relative_moisture_pct=10.0, precip_72h_mm=0.0,
        clay_pct=CLAY_HIGH_PCT,
    ))
    assert result.classification == "Riziko"
    assert "Pravidlo 6" in result.decisive_rule


def test_clay_bumps_riziko_to_nevhodne():
    result = classify(_base_input(
        relative_moisture_pct=RELATIVE_MOISTURE_HIGH_PCT, precip_72h_mm=0.0,
        clay_pct=CLAY_HIGH_PCT,
    ))
    assert result.classification == "Nevhodné"


def test_clay_never_pushes_past_nevhodne():
    """Pravidlo 6 nesmí přetéct přes nejhorší třídu."""
    result = classify(_base_input(
        relative_moisture_pct=RELATIVE_MOISTURE_HIGH_PCT, precip_72h_mm=PRECIP_72H_RISK_MM,
        clay_pct=CLAY_HIGH_PCT,
    ))
    assert result.classification == "Nevhodné"


def test_clay_just_below_threshold_does_not_bump():
    result = classify(_base_input(
        relative_moisture_pct=10.0, precip_72h_mm=0.0,
        clay_pct=CLAY_HIGH_PCT - 0.1,
    ))
    assert result.classification == "Vhodné"


def test_clay_missing_does_not_bump_but_adds_caveat():
    result = classify(_base_input(relative_moisture_pct=10.0, precip_72h_mm=0.0, clay_pct=None))
    assert result.classification == "Vhodné"
    assert any("textura" in c.lower() for c in result.caveats)


def test_slope_is_not_a_classify_input_at_all():
    """Sklon záměrně NENÍ rozhodovací vstup (viz ADR-013) - ClassificationInput
    ho ani nemá jako pole. Tenhle test hlídá, že se náhodou nepřidá bez ADR."""
    import dataclasses
    field_names = {f.name for f in dataclasses.fields(ClassificationInput)}
    assert "slope" not in field_names
    assert "slope_pct" not in field_names
    assert "slope_degrees" not in field_names


def test_backscatter_jump_gives_low_confidence():
    result = classify(_base_input(backscatter_jump_detected=True))
    assert result.confidence == "nízká"
    assert "orba" in result.confidence_reason.lower() or "sklizeň" in result.confidence_reason.lower()


def test_stale_sentinel1_scene_gives_medium_confidence():
    result = classify(_base_input(sentinel1_age_days=10))
    assert result.confidence == "střední"


def test_fresh_everything_gives_high_confidence():
    # precip_data_age_days=4 ve výchozím _base_input() je REALISTICKÁ hodnota
    # (živě ověřená latence NASA POWER, ADR-012) - proto by i "jinak ideální"
    # vstup obvykle skončil na "střední", ne "vysoká". Tenhle test cíleně
    # simuluje hypoteticky čerstvější srážková data, aby ověřil, že cesta
    # k "vysoká" vůbec existuje a funguje, ne že je nedosažitelná.
    result = classify(_base_input(precip_data_age_days=1))
    assert result.confidence == "vysoká"


def test_realistic_precip_latency_caps_confidence_at_medium():
    """
    Regresní pojistka na ADR-012 nález: NASA POWER srážky mají živě
    ověřenou ~4denní latenci. Běžný reálný běh (precip_data_age_days=4)
    proto NESMÍ dostat "vysoká" spolehlivost, i když je jinak všechno
    v pořádku - to by bylo přehnané sebevědomí vzhledem ke skutečně
    starým srážkovým datům.
    """
    result = classify(_base_input())
    assert result.confidence == "střední"


def test_stale_precip_data_adds_caveat():
    result = classify(_base_input(precip_72h_mm=1.0, precip_data_age_days=5))
    assert any("latence" in c.lower() or "stará" in c.lower() for c in result.caveats)


def test_missing_precip_adds_caveat_not_nelze_urcit():
    """Chybějící srážky samy o sobě nemusí shodit celou klasifikaci na
    'Nelze určit' - jen se sníží spolehlivost přes caveat, posuzuje se
    jen podle vlhkosti (zadání neuvádí srážky jako tvrdou podmínku)."""
    result = classify(_base_input(relative_moisture_pct=10.0, precip_72h_mm=None))
    assert result.classification == "Vhodné"
    assert any("srážk" in c.lower() for c in result.caveats)
