# In game_logic.py

import re
from collections import defaultdict

# Points for collector cards based on count (index 0 is for 0 cards)
SHELL_POINTS = [0, 0, 2, 4, 6, 8, 10]
OCTOPUS_POINTS = [0, 0, 3, 6, 9, 12]
PENGUIN_POINTS = [0, 1, 3, 5]
SAILOR_POINTS = [0, 0, 5]

# Canonical names to handle user input variations (plural, typos, etc.)
CARD_MAP = {
    "crab": "crab", "crabs": "crab",
    "boat": "boat", "boats": "boat",
    "fish": "fish",
    "swimmer": "swimmer",
    "shark": "shark",
    "shell": "shell", "shells": "shell",
    "octopus": "octopus", "octopuses": "octopus",
    "penguin": "penguin", "penguins": "penguin",
    "sailor": "sailor", "sailors": "sailor",
    "lighthouse": "lighthouse",
    "shoal": "shoal", "shoal of fish": "shoal",
    "colony": "colony", "penguin colony": "colony",
    "captain": "captain",
}

def calculate_score(card_text: str):
    """Parses a string of cards and calculates the total score."""
    card_counts = defaultdict(int)
    
    # Build a dynamic regex from the card map keys.
    # Sort keys by length, descending, to match longer names first (e.g., "shoal of fish" before "fish").
    sorted_card_names = sorted(CARD_MAP.keys(), key=len, reverse=True)
    card_pattern = "|".join(re.escape(name) for name in sorted_card_names)
    
    # This pattern finds all occurrences of "number card_name" in the text.
    pattern = re.compile(r"(\d+)\s+(" + card_pattern + r")", re.IGNORECASE)
    matches = pattern.findall(card_text)

    if not matches:
        return "I couldn't find any valid cards in your message. Please use the format: `/score 2 crabs, 3 shells`", {}

    for count, name in matches:
        canonical_name = CARD_MAP.get(name.lower().strip())
        if canonical_name:
            card_counts[canonical_name] += int(count)

    total_score = 0
    score_breakdown = []

    # --- Calculate Score ---
    # 1. Collector Cards
    if "shell" in card_counts:
        count = min(card_counts["shell"], len(SHELL_POINTS) - 1)
        points = SHELL_POINTS[count]
        total_score += points
        score_breakdown.append(f"{count} Shells: {points} pts")

    if "octopus" in card_counts:
        count = min(card_counts["octopus"], len(OCTOPUS_POINTS) - 1)
        points = OCTOPUS_POINTS[count]
        total_score += points
        score_breakdown.append(f"{count} Octopuses: {points} pts")
        
    if "penguin" in card_counts:
        count = min(card_counts["penguin"], len(PENGUIN_POINTS) - 1)
        points = PENGUIN_POINTS[count]
        total_score += points
        score_breakdown.append(f"{count} Penguins: {points} pts")

    if "sailor" in card_counts:
        count = min(card_counts["sailor"], len(SAILOR_POINTS) - 1)
        points = SAILOR_POINTS[count]
        total_score += points
        score_breakdown.append(f"{count} Sailors: {points} pts")

    # 2. Duo Cards (1 point per pair)
    for card in ["crab", "boat", "fish"]:
        if card in card_counts:
            pairs = card_counts[card] // 2
            if pairs > 0:
                total_score += pairs
                score_breakdown.append(f"{pairs} pair(s) of {card.capitalize()}s: {pairs} pts")

    # Shark + Swimmer combo (1 point per combo of 1 Shark + 1 Swimmer)
    sharks = card_counts.get("shark", 0)
    swimmers = card_counts.get("swimmer", 0)
    
    if sharks > 0 or swimmers > 0:
        combos = min(sharks, swimmers)
        leftover_sharks = sharks - combos
        leftover_swimmers = swimmers - combos
        
        if combos > 0:
            total_score += combos
            score_breakdown.append(f"{combos} Shark+Swimmer combo(s): {combos} pts")
        
        if leftover_sharks > 0:
            score_breakdown.append(f"{leftover_sharks} leftover Shark(s): 0 pts")
            
        if leftover_swimmers > 0:
            score_breakdown.append(f"{leftover_swimmers} leftover Swimmer(s): 0 pts")

    # 3. Multiplier Cards
    if "lighthouse" in card_counts and "boat" in card_counts:
        points = card_counts["lighthouse"] * card_counts["boat"]
        total_score += points
        score_breakdown.append(f"Lighthouse + Boats: {points} pts")

    if "shoal" in card_counts and "fish" in card_counts:
        points = card_counts["shoal"] * card_counts["fish"]
        total_score += points
        score_breakdown.append(f"Shoal + Fish: {points} pts")

    if "colony" in card_counts and "penguin" in card_counts:
        points = card_counts["colony"] * card_counts["penguin"] * 2
        total_score += points
        score_breakdown.append(f"Colony + Penguins: {points} pts")
        
    if "captain" in card_counts and "sailor" in card_counts:
        points = card_counts["captain"] * card_counts["sailor"] * 3
        total_score += points
        score_breakdown.append(f"Captain + Sailors: {points} pts")

    # --- Format final response ---
    if not score_breakdown:
        return "I couldn't find any scorable cards in your message. Try again! If you were trying to score a mermaid card, do it under /color_bonus. A Mermaid card's only role in scoring is to act as a key that unlocks your ability to claim a color bonus. The points from the bonus come from your colored cards, not from the Mermaid itself.", {}
        
    response_text = "Here's your score breakdown:\n"
    response_text += "\n".join(f"• {item}" for item in score_breakdown)
    response_text += f"\n\n**Total Score: {total_score}**"
    
    return response_text, card_counts


def calculate_color_bonus(card_text: str, called_last_chance: bool = True, caller: bool = True, caller_succeeded: bool = True):
    """
    Calculate color bonus for Sea Salt & Paper according to official rules.

    Parameters:
    - card_text: string, e.g. "4 blue, 3 pink, 2 yellow, 1 mermaid"
    - called_last_chance: bool, True if the round ended by a "Last Chance" call
    - caller: bool, True if this player was the one who called Last Chance
    - caller_succeeded: bool, True if the caller's bet succeeded (they had highest or tied-highest score)

    Returns:
    - (bonus_points, explanation)
    """

    # --- 1️⃣ Early exit if no color bonus should apply ---
    if not called_last_chance:
        return 0, "No color bonus is scored when the round ends with **Stop**."

    # --- 2️⃣ Parse input text ---
    pattern = re.compile(r"(\d+)\s+([a-zA-Z]+)")
    matches = pattern.findall(card_text.lower())

    if not matches:
        return 0, (
            "Please list your cards by color count. \n"
            "Example: `/color-bonus 4 blue, 3 pink, 1 mermaid`"
        )

    mermaid_count = 0
    color_counts = []

    for count_str, name in matches:
        count = int(count_str)
        if "mermaid" in name:
            mermaid_count = count
        else:
            color_counts.append(count)

    # --- 3️⃣ Compute bonus value ---
    bonus_points = 0
    breakdown = ""

    if mermaid_count >= 1:
        # Sort colors from highest to lowest
        color_counts.sort(reverse=True)
        groups_to_score = min(mermaid_count, len(color_counts))
        selected_groups = color_counts[:groups_to_score]
        bonus_points = sum(selected_groups)
        breakdown = " + ".join(map(str, selected_groups))
        explanation = (
            f"You have **{mermaid_count} Mermaid(s)** → "
            f"score your top **{groups_to_score}** color group(s): {breakdown}.\n"
            f"**Total Color Bonus: {bonus_points}**"
        )
    else:
        # No mermaids → only the largest color group counts
        bonus_points = max(color_counts) if color_counts else 0
        explanation = (
            f"No Mermaids → score your largest color group only.\n"
            f"**Total Color Bonus: {bonus_points}**"
        )

    # --- 4️⃣ Determine which players actually receive the bonus ---
    if caller:
        if caller_succeeded:
            # Caller wins → caller gets full bonus + normal points, others only bonus
            explanation += "\n(Called Last Chance and succeeded: you keep your full points **plus** this bonus.)"
        else:
            # Caller loses → caller gets only bonus
            explanation += "\n(Called Last Chance and failed: you score **only this color bonus**.)"
    else:
        if caller_succeeded:
            # Other players get only the color bonus
            explanation += "\n(Another player called Last Chance and succeeded: you score **only this color bonus**.)"
        else:
            # Other players score normal points, no color bonus
            bonus_points = 0
            explanation += "\n(Caller failed their Last Chance: you score your **normal card points only**, no color bonus.)"

    return bonus_points, explanation
