"""
MENDORA safety rules — deterministic, no AI involved.

Everything the safety engine knows lives in this file as plain data, so it can be reviewed and
extended without touching the engine:

  QUESTIONS   clarifying yes / no / not-sure questions for MEDIUM (uncertain) hazards
  GUIDANCE    plain-language advice for each kind of HIGH-risk situation
  RULES       hazard patterns (regular expressions) with their risk level
  ELECTRICAL_SIMPLE / UNSAFE_INSTRUCTION_PATTERNS   see their comments

How risk is decided (see engine.py):
  * any HIGH rule matches                → high: DIY and AI diagnosis are blocked
  * otherwise any MEDIUM rule matches    → medium: no DIY; clarifying questions; professional advised
  * nothing matches                      → low (but electrical jobs default to medium unless they are
                                           clearly simple, and alarming/uncertain wording is medium)
Answers to clarifying questions can raise a hazard to high, or clear a medium hazard.
A high hazard is never cleared by answers.

Patterns are matched case-insensitively. `[^.]{0,40}` means "within about 40 characters, in the same sentence".
"""

from dataclasses import dataclass
from typing import Literal

RULES_VERSION = "2026-10-27.1"

Risk = Literal["low", "medium", "high"]
Effect = Literal["escalate", "keep", "resolve"]
Category = Literal["electrical", "gas", "structural", "plumbing", "carpentry", "general"]


# ---------------------------------------------------------------------------
# Clarifying questions (answers: yes / no / not_sure — "not sure" always keeps the hazard)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Question:
    id: str
    text: str
    on_yes: Effect
    on_no: Effect


_QUESTION_LIST = [
    Question("electrical_danger_signs", "Do you see sparks or scorch marks, feel heat, or smell burning (or a fishy smell) near it?", "escalate", "resolve"),
    Question("electrical_opening", "Would fixing it mean opening or removing a socket, switch, light fitting or fuse box, or touching any wiring?", "keep", "resolve"),
    Question("breaker_repeats", "Does it trip or blow again straight after you reset it, even with appliances unplugged?", "keep", "resolve"),
    Question("gas_signs", "Can you smell gas (like rotten eggs) or hear hissing near the appliance or pipe?", "escalate", "keep"),
    Question("crack_signs", "Is the crack getting wider, wider than about 5 mm (a pencil's width), or are nearby doors or windows suddenly sticking?", "escalate", "resolve"),
    Question("ceiling_leak_signs", "Is the ceiling sagging or bulging, or is water dripping near a light, fan or other electrics?", "escalate", "resolve"),
    Question("water_heater_signs", "Is the water heater bulging, releasing steam, making loud bangs, or is the water scalding hot?", "escalate", "keep"),
    Question("contamination_signs", "Has anyone felt unwell after using the water, or is sewage or dirty water coming up anywhere?", "escalate", "keep"),
    Question("sewage_backup", "Is sewage or dirty water backing up into sinks, toilets or onto the floor?", "escalate", "resolve"),
    Question("furniture_tip", "Could it tip over or fall on someone — for example, is it tall or heavy, not fixed to the wall, or used by children?", "escalate", "resolve"),
    Question("overhead_signs", "Is it loose where it is fixed, hanging lower than before, or could it fall on someone?", "escalate", "resolve"),
    Question("glass_injury", "Is anyone hurt, or is the broken glass somewhere a person could fall into or step on?", "escalate", "resolve"),
    Question("general_danger", "Is anyone in danger right now — for example fire, smoke, sparks, a gas smell, water near electrics, or something about to fall?", "escalate", "resolve"),
]
QUESTIONS: dict[str, Question] = {q.id: q for q in _QUESTION_LIST}


# ---------------------------------------------------------------------------
# Guidance for HIGH-risk situations (plain language, no repair instructions)
# ---------------------------------------------------------------------------

EMERGENCY_NUMBER_HINT = "your local emergency number (for example 112 in India and the EU, or 911 in the US)"


@dataclass(frozen=True)
class Guidance:
    priority: int  # lower = more urgent; decides which advice is shown first
    explanation: str
    action: str
    steps: tuple[str, ...]
    professional: str
    leave_area: bool = False


GUIDANCE: dict[str, Guidance] = {
    "gas_leak": Guidance(
        1,
        "A gas smell or hissing sound can mean a gas leak. Leaking gas can catch fire or explode.",
        f"Leave the area now. Once you are outside and safe, call your gas provider's emergency line or {EMERGENCY_NUMBER_HINT}.",
        (
            "Get everyone, including pets, out of the area now.",
            "Don't use flames, lighters or matches, and don't switch lights, appliances or anything electrical on or off.",
            "Don't use your phone near the smell — call once you are outside and away from it.",
            "If doors or windows are on your way out, open them, but don't delay leaving.",
            "Only if it is right by your exit and safe to reach, turn off the gas at the cylinder or meter.",
            "Don't try to find the leak or repair anything. Don't go back in until the gas provider says it is safe.",
        ),
        "your gas provider or a registered gas engineer",
        leave_area=True,
    ),
    "carbon_monoxide": Guidance(
        1,
        "A carbon monoxide alarm means a poisonous gas may be in the air. You can't see or smell it.",
        f"Get everyone out into fresh air now, then call {EMERGENCY_NUMBER_HINT} or your gas provider's emergency line.",
        (
            "Get everyone, including pets, out into fresh air now.",
            "Don't go back inside until professionals say it is safe.",
            f"Call {EMERGENCY_NUMBER_HINT} or your gas provider's emergency line from outside.",
            "Get medical help if anyone has a headache, dizziness, sickness or drowsiness.",
            "Don't use the boiler, heater or appliance again until a registered engineer has checked it.",
        ),
        "a registered gas engineer",
        leave_area=True,
    ),
    "electrical_fire": Guidance(
        2,
        "Sparks, smoke, burning smells or scorch marks can mean wiring is overheating, which can start a fire.",
        "Keep away from it and don't touch it. If there is smoke or fire, leave and call the emergency number. Otherwise contact a qualified electrician.",
        (
            "Don't touch the socket, switch, appliance or cable.",
            f"If there is smoke or flames, get everyone out and call {EMERGENCY_NUMBER_HINT}.",
            "Never use water on an electrical fire.",
            "Only if your main switch is in a dry place you can reach safely, switch off the power there.",
            "Don't use that socket, switch or appliance again until a qualified electrician has checked it.",
        ),
        "a qualified electrician",
        leave_area=True,
    ),
    "electrical_contact": Guidance(
        2,
        "Exposed wires, electric shocks or very hot electrical parts mean live electricity may be reachable. This can cause serious injury.",
        "Keep everyone away and don't touch it. If it is safe and dry, switch off the power at the main switch, then call a qualified electrician.",
        (
            "Don't touch the wires, socket, appliance or anything connected to them, and keep children and pets away.",
            "Only if your main switch is in a dry place you can reach safely, switch off the power there.",
            f"If someone has had a shock and is still touching the source, don't touch them — switch off the power first, then call {EMERGENCY_NUMBER_HINT}.",
            "Anyone who had a strong shock should get medical advice, even if they feel fine.",
            "Call a qualified electrician. Don't use it until it has been checked.",
        ),
        "a qualified electrician",
    ),
    "water_electrical": Guidance(
        2,
        "Water near sockets, switches, lights or the fuse box can make surfaces live and cause electric shocks.",
        "Don't touch anything electrical or walk through the water. Switch off the power at the main switch only if you can reach it from a dry place; otherwise leave the area and call for help.",
        (
            "Don't walk through the water, and don't touch switches, sockets, plugs or appliances near it.",
            "Only if your main switch is in a dry place you can reach without touching water, switch off the power there.",
            "If you can't safely reach the main switch, leave the area and call an electrician or the emergency number.",
            "Once the power is safely off, turn off the main water valve if you can reach it safely.",
            "Call a qualified electrician and a plumber. Don't switch the power back on until it has been checked.",
        ),
        "a qualified electrician and a plumber",
        leave_area=True,
    ),
    "structural": Guidance(
        3,
        "Sagging ceilings, widening cracks or moving walls and beams can be signs that part of the building may give way.",
        "Move everyone out of and away from the area, including rooms below it. Don't try to prop it up or repair it. Call a structural engineer or builder, or the emergency number if it looks close to collapsing.",
        (
            "Move everyone, including pets, out of and away from the area — including rooms below it.",
            "Don't put weight on it, prop it up or try to repair it.",
            f"If it looks like it could collapse soon, call {EMERGENCY_NUMBER_HINT}.",
            "Otherwise contact a structural engineer or qualified builder before using the area again.",
        ),
        "a structural engineer or qualified builder",
        leave_area=True,
    ),
    "major_leak": Guidance(
        4,
        "A burst pipe or uncontrolled leak can quickly flood your home and reach electrics.",
        "If you can reach it safely and away from electrics, turn off the main water valve, then call an emergency plumber.",
        (
            "If water is near sockets, lights or the fuse box, don't touch them or walk through the water — follow electrical safety first.",
            "If you can reach it safely, turn off the main water valve (stop valve).",
            "Switch off the water heater or geyser if you can do so from a dry place.",
            "Move valuables away from the water if it is safe to do so.",
            "Call an emergency plumber.",
        ),
        "an emergency plumber",
    ),
    "sanitation": Guidance(
        5,
        "Sewage or contaminated water can carry germs that make people seriously ill.",
        "Keep away from the water, don't drink or cook with it, and contact a plumber or your water supplier.",
        (
            "Avoid touching the water, and keep children and pets away.",
            "Don't drink the water or use it for cooking or brushing teeth until it has been checked.",
            "Wash your hands well if you have touched it.",
            "Contact a plumber or your water supplier. Get medical advice if anyone feels unwell.",
        ),
        "a plumber or your water supplier",
    ),
    "falling_object": Guidance(
        4,
        "Heavy furniture or fixtures that are tipping, loose or coming away from the wall or ceiling can fall and seriously injure someone.",
        "Keep everyone, especially children, away from it. Don't try to hold it up or climb to fix it. Get a carpenter or installer to secure it.",
        (
            "Keep everyone — especially children and pets — away from under it and in front of it.",
            "Don't try to hold it up on your own, and don't climb on furniture or a ladder to fix it.",
            "Don't put anything on it or open its doors or drawers.",
            "Contact a carpenter or installer to secure it.",
        ),
        "a qualified carpenter or installer",
    ),
    "fall_hazard": Guidance(
        4,
        "Broken or unstable stairs, railings, balconies or floors can give way and cause a serious fall.",
        "Stop using it and block access to it, then contact a carpenter or builder.",
        (
            "Stop using the stairs, railing, balcony or floor area.",
            "Block access to it if you can, and keep children and pets away.",
            "Contact a qualified carpenter or builder to make it safe.",
        ),
        "a qualified carpenter or builder",
    ),
    "general_danger": Guidance(
        3,
        "What you've described could involve immediate danger.",
        f"Move away from the danger. If anyone is at risk, call {EMERGENCY_NUMBER_HINT}; otherwise contact a qualified professional before doing anything else.",
        (
            "Move everyone away from the danger.",
            f"If anyone is hurt or at risk, call {EMERGENCY_NUMBER_HINT}.",
            "Don't try to inspect or repair it yourself.",
            "Contact a qualified professional.",
        ),
        "a qualified professional",
    ),
}


# ---------------------------------------------------------------------------
# Hazard rules
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Rule:
    id: str
    category: Category
    risk: Literal["medium", "high"]
    label: str
    patterns: tuple[str, ...]
    guidance: str = "general_danger"  # GUIDANCE key used when this hazard is (or becomes) high
    explanation: str = ""  # medium only: why it may be risky
    questions: tuple[str, ...] = ()  # medium only: QUESTIONS ids


_ELEC_NOUNS = r"(socket|outlet|plug|switch|switchboard|light fitting|wire|wiring|cable|cord|extension|panel|fuse ?box|breaker|consumer unit|charger|adapter|meter)"
_STRUCT_NOUNS = r"(ceiling|roof|wall|beam|floor|plaster|balcony|stair\w*|joist|pillar|column|foundation|lintel)"
_HEAVY_FURNITURE = r"(wardrobe|almirah|bookcase|bookshelf|book shelf|shelving unit|cabinet|cupboard|dresser|chest of drawers|tv|television|tv stand|mirror|fridge|refrigerator|heavy furniture|heavy unit)"
_OVERHEAD = r"(ceiling fan|fan|chandelier|light fitting|ceiling light|pendant light|pendant)"
_WALL_MOUNTED = r"(shelf|shelves|cabinet|cupboard|mirror|tv|television|bracket|board|geyser|water heater)"

RULES: tuple[Rule, ...] = (
    # ----------------------------- GAS (high) -----------------------------
    Rule(
        "gas_leak", "gas", "high", "Suspected gas leak",
        (
            r"\bgas (smell|leak\w*|odou?r)\b",
            r"\bsmell\w* (of |like )?(lpg |cooking )?gas\b",
            r"\brotten[- ]eggs?\b",
            r"\bleak\w* (of )?gas\b",
            r"\bhiss\w*\b[^.]{0,40}\b(gas|cylinder|stove|cooker|hob|boiler|meter|regulator|burner)\b",
            r"\b(gas|cylinder|stove|cooker|hob|regulator|burner)\b[^.]{0,40}\bhiss\w*",
            r"\b(lpg|cylinder|regulator)\b[^.]{0,30}\b(leak\w*|smell\w*)\b",
        ),
        guidance="gas_leak",
    ),
    Rule(
        "carbon_monoxide", "gas", "high", "Carbon monoxide alarm",
        (r"\bcarbon monoxide\b", r"\bco (alarm|detector)\b"),
        guidance="carbon_monoxide",
    ),
    # -------------------------- ELECTRICAL (high) --------------------------
    Rule(
        "electrical_sparking", "electrical", "high", "Sparking or arcing",
        (
            r"\bspark(s|ing|ed|y)?\b",
            r"\barc(ing|ed)\b",
            r"\bflash(es|ed|ing)?\b[^.]{0,20}\b(from|in|at|out of|behind)\b[^.]{0,15}\b" + _ELEC_NOUNS,
        ),
        guidance="electrical_fire",
    ),
    Rule(
        "electrical_smoke_burning", "electrical", "high", "Smoke, burning smell or scorch marks",
        (
            r"\bsmok(e|ing|ey|y)\b(?!\s*(detector|alarm))",
            r"\b(burning|burnt|burned|melting|melted|scorch(ed|ing)?)\b(?!\s+out\b)",
            r"\bfishy smell\b|\bsmells? (of |like )?fish\b",
            r"\bfire\b(?!\s*(alarm|detector|place|wood|extinguisher))",
            r"\bflames?\b",
            r"\bblack (marks?|soot)\b[^.]{0,30}\b" + _ELEC_NOUNS,
        ),
        guidance="electrical_fire",
    ),
    Rule(
        "electrical_exposed_wires", "electrical", "high", "Exposed or damaged wiring",
        (
            r"\b(exposed|bare|live|frayed|dangling|hanging|damaged|chewed|melted|broken|cut)\s+(electrical\s+)?(wire|wires|wiring|cable|cables)\b",
            r"\b(wire|wires|wiring|cable|cables)\b[^.]{0,20}\b(exposed|hanging out|sticking out|showing|frayed|chewed)\b",
        ),
        guidance="electrical_contact",
    ),
    Rule(
        "electrical_shock", "electrical", "high", "Electric shock",
        (
            r"\b(electric(al)?|got an?|getting|gets?|gave me an?|gives? (me )?an?|giving)\s+(small |little |mild |slight |minor )?shocks?\b",
            r"\bshock(s|ed)?\b[^.]{0,30}\b(from|when i touch(ed)?|touching)\b",
            r"\belectrocut\w*",
            r"\btingl\w*\b[^.]{0,30}\b(touch\w*|tap|metal|appliance|switch|socket|fridge|washing machine)\b",
        ),
        guidance="electrical_contact",
    ),
    Rule(
        "electrical_overheating", "electrical", "high", "Overheating electrical equipment",
        (
            r"\b" + _ELEC_NOUNS + r"s?\b[^.]{0,30}\b(very hot|too hot|hot to (the )?touch|overheat\w*|is hot|are hot|gets? hot|getting hot|feels? hot|was hot|became hot)\b",
            r"\b(hot|overheating)\s+" + _ELEC_NOUNS + r"s?\b",
        ),
        guidance="electrical_contact",
    ),
    # ----------------------- WATER + ELECTRICS (high) ----------------------
    Rule(
        "water_near_electrics", "electrical", "high", "Water near electrics",
        (
            r"\bwater\b(?!\s*(heater|pressure|tank|pump|bill|meter))[^.]{0,40}\b(socket|outlet|switch|fuse ?box|breaker|panel|wiring|light fitting|ceiling light|consumer unit|extension|power strip|fan)s?\b",
            r"\b(socket|outlet|switch|fuse ?box|breaker|panel|wiring|light fitting|ceiling light|consumer unit|extension|power strip)s?\b[^.]{0,40}\b(wet|(?<!hot )(?<!no )water(?!\s*(heater|pressure|tank|pump|bill|meter|supply|flow|motor))|flood\w*|dripping|soaked)\b",
            r"\bflood\w*\b[^.]{0,50}\b(electric\w*|socket|plug|appliance|wiring|power|fuse ?box|outlet)s?\b",
            r"\b(electric\w*|socket|appliance|wiring|fuse ?box|outlet)s?\b[^.]{0,50}\bflood\w*",
        ),
        guidance="water_electrical",
    ),
    # --------------------------- STRUCTURAL (high) -------------------------
    Rule(
        "structural_instability", "structural", "high", "Signs of structural instability",
        (
            r"\bcollaps\w*",
            r"\b(cav(e|ed|ing) in|giv(e|es|ing|en) way|gave way)\b",
            r"\b" + _STRUCT_NOUNS + r"s?\b[^.]{0,30}\b(sagging|sags|bulging|bowing|leaning|caving|collapsing|giving way|coming down|crumbling|shifting|moving|dropping|falling)\b",
            r"\b(sagging|bulging|bowing|leaning|crumbling)\s+" + _STRUCT_NOUNS,
            r"\bcracks?\b[^.]{0,40}\b(widening|getting (wider|bigger|longer)|growing|spreading|opening up)\b",
            r"\bcracked\s+(beam|joist|pillar|column|lintel|foundation|load[- ]bearing wall)s?\b",
            r"\b(beam|joist|pillar|column|lintel)s?\b[^.]{0,20}\b(cracked|cracking|split|splitting|broken)\b",
            r"\b(chunks?|pieces?|lumps?) of (plaster|concrete|ceiling|brick)s?\b[^.]{0,30}\b(fall\w*|fell|coming down|dropp\w*)\b",
        ),
        guidance="structural",
    ),
    # ---------------------------- PLUMBING (high) --------------------------
    Rule(
        "plumbing_major_leak", "plumbing", "high", "Major uncontrolled leak or flooding",
        (
            r"\bburst\b",
            r"\bwater\b[^.]{0,20}\b(pouring|gushing|spraying|spurting|flooding|everywhere|won'?t stop|can'?t stop|not stopping|rising)\b",
            r"\bflood(ed|ing|s)?\b",
            r"\bcan'?t (turn|shut|switch) (off )?the (water|main|stop ?cock|valve)\b",
            r"\b(stop ?cock|main valve|stop valve)\b[^.]{0,20}\b(won'?t|doesn'?t|isn'?t|not) (work\w*|turn\w*|clos\w*)\b",
        ),
        guidance="major_leak",
    ),
    Rule(
        "plumbing_sewage", "plumbing", "high", "Sewage backing up or contaminated water",
        (
            r"\bsewage\b[^.]{0,30}\b(backing up|back up|overflow\w*|flood\w*|coming (up|out)|on the floor|everywhere|in the (house|home|kitchen|bathroom))\b",
            r"\b(raw sewage)\b",
            r"\bcontaminat\w*",
            r"\b(sewage|sewer water) in (the |my )?(drinking |tap )?water\b",
        ),
        guidance="sanitation",
    ),
    # ---------------------------- CARPENTRY (high) -------------------------
    Rule(
        "carpentry_tipping", "carpentry", "high", "Heavy furniture tipping or falling",
        (
            r"\b" + _HEAVY_FURNITURE + r"s?\b[^.]{0,40}\b(tipping|tips over|tilting|leaning (forward|over)|toppl\w*|falling|fell|about to fall|could fall|might fall|nearly fell|coming (off|away) from the wall|pulling (out of|away from) the wall)\b",
        ),
        guidance="falling_object",
    ),
    Rule(
        "carpentry_overhead", "carpentry", "high", "Overhead or wall-mounted item coming loose",
        (
            r"\b" + _OVERHEAD + r"s?\b[^.]{0,40}\b(hanging (down|loose|by)|dangling|coming (down|loose|off)|falling|about to fall|fell|pulling (out|away)|loose from the ceiling|dropp\w*)\b",
            r"\b" + _WALL_MOUNTED + r"\b[^.]{0,40}\b(coming (off|away|loose|down) (from |off )?(the )?(wall|ceiling)|pulling (out of|away from) the (wall|ceiling)|falling off the wall|about to fall|ripping out|hanging off)\b",
        ),
        guidance="falling_object",
    ),
    Rule(
        "carpentry_fall_hazard", "carpentry", "high", "Unsafe stairs, railing, balcony or floor",
        (
            r"\b(stair\w*|railing|banister|handrail|balcony|deck)\b[^.]{0,30}\b(broken|rotten|rotting|loose|wobbly|unstable|gave way|giving way|cracked through|missing|collapsed|snapped)\b",
            r"\b(rotten|rotting|broken|loose|wobbly|unstable)\s+(stair\w*|railing|banister|handrail|balcony|deck)\b",
            r"\b(floor|floorboards?)\b[^.]{0,30}\b(rotten|rotting|gave way|giving way|cracked through|collapsed|snapped|soft and sinking)\b",
        ),
        guidance="fall_hazard",
    ),
    # ============================ MEDIUM (uncertain) ============================
    Rule(
        "electrical_buzzing", "electrical", "medium", "Buzzing or crackling from electrics",
        (
            r"\b(buzz\w*|crackl\w*|humming|hums)\b[^.]{0,40}\b" + _ELEC_NOUNS,
            r"\b" + _ELEC_NOUNS + r"s?\b[^.]{0,40}\b(buzz\w*|crackl\w*|humming|hums)\b",
        ),
        guidance="electrical_fire",
        explanation="Buzzing or crackling can be a sign of a loose or overheating connection.",
        questions=("electrical_danger_signs", "electrical_opening"),
    ),
    Rule(
        "electrical_tripping", "electrical", "medium", "Breaker or fuse keeps tripping",
        (
            r"\b(breaker|fuse|trip switch|rcd|mcb|rccb|elcb|circuit)s?\b[^.]{0,40}\b(trip\w*|blow\w*|blew|keeps? going off|goes off|cuts? out|keeps? switching off)\b",
            r"\b(trip\w*|keeps? tripping)\b[^.]{0,20}\b(breaker|fuse|trip switch|rcd|mcb|power)\b",
            r"\bpower (keeps )?(goes|going|cuts?|cutting) (off|out)\b",
        ),
        guidance="electrical_fire",
        explanation="A breaker or fuse that keeps tripping is a safety device warning about a fault.",
        questions=("electrical_danger_signs", "breaker_repeats"),
    ),
    Rule(
        "electrical_warm", "electrical", "medium", "Warm electrical part",
        (r"\b" + _ELEC_NOUNS + r"s?\b[^.]{0,30}\b(warm|heats up|heating up)\b", r"\bwarm\s+" + _ELEC_NOUNS),
        guidance="electrical_contact",
        explanation="Electrical parts that feel warm can be overloaded or have a loose connection.",
        questions=("electrical_danger_signs",),
    ),
    Rule(
        "gas_appliance", "gas", "medium", "Gas appliance or gas pipework",
        (
            r"\bgas\s+(stove|cooker|hob|boiler|heater|geyser|water heater|appliance|pipe|line|valve|meter|connection|cylinder|burner|oven|fire)\b",
            r"\b(pilot light|lpg|gas cylinder|regulator)\b",
        ),
        guidance="gas_leak",
        explanation="Work on gas appliances and gas pipes must be done by a registered gas engineer.",
        questions=("gas_signs",),
    ),
    Rule(
        "structural_crack", "structural", "medium", "Crack in a wall, ceiling or floor",
        (
            r"\bcrack(s|ed|ing)?\b[^.]{0,40}\b" + _STRUCT_NOUNS,
            r"\b" + _STRUCT_NOUNS + r"s?\b[^.]{0,40}\bcrack(s|ed|ing)?\b",
        ),
        guidance="structural",
        explanation="Most small cracks are harmless, but growing or wide cracks can be a sign of movement in the building.",
        questions=("crack_signs",),
    ),
    Rule(
        "plumbing_ceiling_leak", "plumbing", "medium", "Leak through a ceiling",
        (
            r"\b(water|leak\w*|drip\w*|stain\w*|damp|wet)\b[^.]{0,40}\bceiling\b",
            r"\bceiling\b[^.]{0,40}\b(leak\w*|drip\w*|stain\w*|damp|wet|water)\b",
        ),
        guidance="water_electrical",
        explanation="Water coming through a ceiling can weaken it and may reach light fittings.",
        questions=("ceiling_leak_signs",),
    ),
    Rule(
        "plumbing_water_heater", "plumbing", "medium", "Water heater problem",
        (
            r"\b(water heater|geyser|boiler|hot water (cylinder|tank))\b[^.]{0,40}\b(bang\w*|knock\w*|rumbl\w*|leak\w*|very hot|too hot|scalding|steam\w*|pressure|relief valve|bulg\w*|hiss\w*|overheat\w*)\b",
        ),
        guidance="major_leak",
        explanation="Water heaters run at high temperature and pressure, so faults need a professional.",
        questions=("water_heater_signs",),
    ),
    Rule(
        "plumbing_water_quality", "plumbing", "medium", "Possible water contamination",
        (
            r"\b(tap water|drinking water|water from the tap|water)\b[^.]{0,40}\b(brown|black|yellow|cloudy|dirty|discolou?red|muddy|smells?|stinks?|smelly|tastes? (bad|strange|funny|odd|weird|of|like)|oily|worms?|insects?)\b",
        ),
        guidance="sanitation",
        explanation="Discoloured, smelly or strange-tasting water may not be safe to drink until it has been checked.",
        questions=("contamination_signs",),
    ),
    Rule(
        "plumbing_sewage_smell", "plumbing", "medium", "Sewage smell",
        (r"\b(sewage|sewer|drain)\s+(smell|odou?r|stink)\w*", r"\bsmells? (like|of) (sewage|sewer)\b"),
        guidance="sanitation",
        explanation="A sewage smell can come from a dry trap, but it can also mean a leak or blockage in the waste pipes.",
        questions=("sewage_backup",),
    ),
    Rule(
        "carpentry_unstable_furniture", "carpentry", "medium", "Unstable heavy furniture",
        (
            r"\b" + _HEAVY_FURNITURE + r"s?\b[^.]{0,40}\b(wobbl\w*|unstable|unsteady|rocks|rocking|not (fixed|secured|anchored)|leaning)\b",
            r"\b(wobbly|unstable|unsteady)\s+" + _HEAVY_FURNITURE,
        ),
        guidance="falling_object",
        explanation="Tall or heavy furniture that isn't stable can tip over, especially if children climb on it.",
        questions=("furniture_tip",),
    ),
    Rule(
        "carpentry_overhead_loose", "carpentry", "medium", "Overhead item wobbling or loose",
        (
            r"\b" + _OVERHEAD + r"s?\b[^.]{0,40}\b(wobbl\w*|shak\w*|sway\w*|loose|rattl\w*)\b",
            r"\b" + _WALL_MOUNTED + r"\b[^.]{0,40}\b(loose|wobbl\w*|sagging|sags|pulling)\b[^.]{0,20}\b(wall|ceiling|bracket|above)\b",
        ),
        guidance="falling_object",
        explanation="Something overhead that wobbles or is loose could fall if its fixing is failing.",
        questions=("overhead_signs",),
    ),
    Rule(
        "carpentry_broken_glass", "carpentry", "medium", "Broken glass",
        (r"\b(broken|shattered|smashed|cracked)\s+(glass|window|mirror|glass door|glass panel|pane)\b", r"\bglass\b[^.]{0,40}\b(broke|broken|shattered|smashed)\b"),
        guidance="general_danger",
        explanation="Broken glass can cause cuts, and broken glass in doors or windows can give way.",
        questions=("glass_injury",),
    ),
    Rule(
        "general_danger_signals", "general", "medium", "Possible danger mentioned",
        (
            r"\b(danger(ous)?|unsafe|emergency|urgent(ly)?|hazard(ous)?|scared|frightened|afraid|terrified|panic\w*)\b",
            r"\b(not sure|unsure|don'?t know|no idea) (if|whether) (it'?s|it is|this is) (safe|dangerous)\b",
            r"\b(hurt|injur\w*|bleed\w*|cut (myself|himself|herself|my hand|my finger))\b",
            r"\b(loud bang|bang(ed|ing)? sound|explosion|explod\w*|pop(ped|ping)? sound|boom)\b",
            r"\b(strange|weird|funny|odd|unusual|bad|chemical) (smell|odou?r|noise|sound)s?\b",
            r"\bhot to (the )?touch\b",
        ),
        guidance="general_danger",
        explanation="Your description mentions something that could be dangerous, so it needs a closer look.",
        questions=("general_danger",),
    ),
)

RULES_BY_ID: dict[str, Rule] = {r.id: r for r in RULES}

# The engine uses this for electrical jobs with no specific hazard: unless the job is clearly one of these
# simple, plug-in or no-wiring tasks, it is treated as MEDIUM ("electrical work usually needs an electrician").
ELECTRICAL_SIMPLE: tuple[str, ...] = (
    r"\b(light ?bulbs?|bulbs?|lamps?|tube ?lights?|led tube|fairy lights|torch|flashlight)\b",
    r"\bbatter(y|ies)\b",
    r"\b(remote|remote control)\b",
    r"\b(smoke|fire) (alarm|detector)\b[^.]{0,30}\b(chirp\w*|beep\w*|battery)\b",
    r"\breset (the |my )?(breaker|trip switch|rcd|mcb)\b[^.]{0,40}\b(fine|worked|working|ok|okay|now)\b",
    r"\bplug[- ]in\b",
    r"\bextension (lead|cord|board)\b",
    r"\b(phone )?charger\b(?![^.]{0,30}\b(hot|warm|melt\w*|spark\w*|smok\w*))",
)

# Text that would amount to dangerous do-it-yourself instructions. Used to screen what the AI writes,
# so an unsafe suggestion is removed even if the AI produces one.
UNSAFE_INSTRUCTION_PATTERNS: tuple[str, ...] = (
    r"\b(open|remove|unscrew|take off|pull off|prise|pry|unclip)\b[^.]{0,30}\b(cover|faceplate|face plate|panel|fuse ?box|breaker box|consumer unit|distribution board|db box|socket|outlet|switch ?board|switch|light fitting|junction box)\b",
    r"\b(touch|cut|strip|splice|reconnect|disconnect|rewire|join|twist|tape|tighten|loosen)\b[^.]{0,20}\b(wire|wires|wiring|cable|cables|live|neutral|earth wire|terminals?)\b",
    r"\b(bypass|override|tape (down|over)|hold (down|in)|force)\b[^.]{0,20}\b(breaker|fuse|rcd|mcb|trip|safety valve|relief valve|thermostat|cut-?out)\b",
    r"\b(replace|change|swap|install|fit|upgrade)\b[^.]{0,20}\b(fuse box|breaker|mcb|rcd|wiring|socket|outlet|light switch|switch board|consumer unit)\b",
    r"\b(soap(y)? (water|solution)|bubble test|leak[- ]?test|sniff (for|around))\b",
    r"\b(find|locate|trace|look for|check for)\b[^.]{0,15}\b(gas )?leak",
    r"\b(tighten|loosen|repair|fix|disconnect|reconnect|adjust|remove|seal|tape)\b[^.]{0,25}\b(gas (pipe|line|valve|fitting|hose|connection|regulator|meter)|regulator|burner|gas cylinder)\b",
    r"\b(relight|re-light|light)\b[^.]{0,15}\bpilot\b",
    r"\b(prop up|support|jack up|remove|cut|knock (down|through)|drill (into|through))\b[^.]{0,25}\b(beam|joist|load[- ]bearing|pillar|column|lintel)\b",
    r"\b(climb|get) (on|onto) (the )?roof\b",
    r"\b(open|drain|release)\b[^.]{0,20}\b(pressure relief valve|relief valve|tpr valve)\b",
)
