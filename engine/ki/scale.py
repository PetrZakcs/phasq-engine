"""
Převod na stupnici pravděpodobnosti dle tabulky č. 1, příloha 1 vyhlášky
č. 122/2026 Sb. Viz zadání kap. 4 - pravidla jsou odtud doslovně převzatá,
nic není dovozené ani odhadnuté.
"""

from dataclasses import dataclass

SEVERITY_LABELS: dict[int, str] = {
    1: "Zanedbatelná",
    2: "Malá",
    3: "Střední",
    4: "Vysoká",
    5: "Velmi vysoká",
}

SEVERITY_TEXT: dict[int, str] = {
    1: "ne častěji než jednou za 20 let",
    2: "jednou za 10-20 let",
    3: "jednou za 5-10 let",
    4: "jednou za 1-5 let",
    5: "častěji než jednou za rok",
}


@dataclass
class ProbabilityProposal:
    level: int
    label: str
    rationale: str
    is_borderline: bool = False
    borderline_alternative_level: int | None = None
    borderline_alternative_label: str | None = None


def propose_flood_probability(in_q5: bool, in_q20: bool, in_q100: bool) -> ProbabilityProposal:
    """
    Návrh úrovně pravděpodobnosti pro NÁVRHOVÉ povodně (Q5/Q20/Q100).
    Pravidla ze zadání, nevyjednatelná:
    - Q5 -> návrh 4 (Vysoká, "jednou za 1-5 let" zahrnuje hraniční hodnotu 5)
    - Q20 -> návrh 2 (Malá), VŽDY označit jako hraniční vůči úrovni 1 -
      hodnota "jednou za 20 let" leží přesně na hranici mezi "ne častěji
      než jednou za 20 let" (1) a "jednou za 10-20 let" (2).
    - Q100 -> návrh 1 (Zanedbatelná)
    - mimo Q100 -> 1, s poznámkou "mimo vymezená záplavová území"

    Kontrola podle priority Q5 > Q20 > Q100 > mimo - objekt v Q5 je typicky
    i v Q20/Q100 (menší periodа je podmnožina větší), takže se testuje
    od nejpřísnější.
    """
    if in_q5:
        return ProbabilityProposal(
            level=4,
            label=SEVERITY_LABELS[4],
            rationale=(
                "Objekt leží v záplavovém území Q5 (pětiletá voda - průtok "
                "s dobou opakování 5 let). Dle tabulky č. 1 odpovídá úrovni "
                f"'{SEVERITY_LABELS[4]}' ({SEVERITY_TEXT[4]})."
            ),
        )
    if in_q20:
        return ProbabilityProposal(
            level=2,
            label=SEVERITY_LABELS[2],
            rationale=(
                "Objekt leží v záplavovém území Q20 (dvacetiletá voda), mimo "
                "Q5. Dle tabulky č. 1 odpovídá úrovni "
                f"'{SEVERITY_LABELS[2]}' ({SEVERITY_TEXT[2]})."
            ),
            is_borderline=True,
            borderline_alternative_level=1,
            borderline_alternative_label=SEVERITY_LABELS[1],
        )
    if in_q100:
        return ProbabilityProposal(
            level=1,
            label=SEVERITY_LABELS[1],
            rationale=(
                "Objekt leží v záplavovém území Q100 (stoletá voda), mimo "
                "Q20. Dle tabulky č. 1 odpovídá úrovni "
                f"'{SEVERITY_LABELS[1]}' ({SEVERITY_TEXT[1]})."
            ),
        )
    return ProbabilityProposal(
        level=1,
        label=SEVERITY_LABELS[1],
        rationale=(
            "Objekt leží mimo vymezená záplavová území (Q5/Q20/Q100). Dle "
            f"tabulky č. 1 odpovídá úrovni '{SEVERITY_LABELS[1]}' "
            f"({SEVERITY_TEXT[1]})."
        ),
    )
