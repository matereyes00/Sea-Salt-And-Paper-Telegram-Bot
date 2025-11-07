import re
from collections import defaultdict

# Points for collector cards based on count (index 0 is for 0 cards)
SHELL_POINTS = [0, 0, 2, 4, 6, 8, 10]
OCTOPUS_POINTS = [0, 0, 3, 6, 9, 12]
PENGUIN_POINTS = [0, 1, 3, 5]
SAILOR_POINTS = [0, 0, 5]
COLLECTOR_POINTS_MAP = {
    "shell": SHELL_POINTS,
    "octopus": OCTOPUS_POINTS,
    "penguin": PENGUIN_POINTS,
    "sailor": SAILOR_POINTS,
}
COLLECTOR_TYPES = ["shell", "octopus", "penguin", "sailor"]

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
    "basket": "basket", "basket of crabs": "basket",
    "jellyfish": "jellyfish", "jellyfishes": "jellyfish",
    "seahorse": "seahorse",
    "starfish": "starfish",
    "lobster": "lobster",
}

def calculate_score(card_text: str):
    """Parses a string of cards and calculates the total score."""
    card_counts = defaultdict(int)
    
    # Build a dynamic regex from the card map keys
    sorted_card_names = sorted(CARD_MAP.keys(), key=len, reverse=True)
    card_pattern = "|".join(re.escape(name) for name in sorted_card_names)
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

    # --- Collector Cards ---
    if "seahorse" in card_counts and card_counts["seahorse"] > 0:
        max_gain = -1
        best_collector_type = None
        for collector_type in COLLECTOR_TYPES:
            if card_counts.get(collector_type, 0) > 0:
                current_count = card_counts[collector_type]
                new_count = current_count + 1
                points_array = COLLECTOR_POINTS_MAP[collector_type]
                current_points_index = min(current_count, len(points_array) - 1)
                new_points_index = min(new_count, len(points_array) - 1)
                gain = points_array[new_points_index] - points_array[current_points_index]
                if gain > max_gain:
                    max_gain = gain
                    best_collector_type = collector_type

        if best_collector_type is not None and max_gain > 0:
            card_counts["seahorse"] -= 1
            card_counts[best_collector_type] += 1
            score_breakdown.append(f"1 Seahorse used for {best_collector_type}: +{max_gain} pts")

    # Scoring collector sets
    for card, points_list in COLLECTOR_POINTS_MAP.items():
        if card in card_counts:
            count = min(card_counts[card], len(points_list) - 1)
            points = points_list[count]
            total_score += points
            score_breakdown.append(f"{count} {card.capitalize()}(s): {points} pts")

    # --- Duo Cards (1 point per pair) ---
    for card in ["crab", "boat", "fish"]:
        if card in card_counts:
            pairs = card_counts[card] // 2
            if pairs > 0:
                total_score += pairs
                score_breakdown.append(f"{pairs} pair(s) of {card.capitalize()}s: {pairs} pts")

    # --- Duo Combos ---
    sharks = card_counts.get("shark", 0)
    swimmers = card_counts.get("swimmer", 0)
    jellyfish = card_counts.get("jellyfish", 0)

    # 🦈 Shark + Swimmer
    if sharks > 0 and swimmers > 0:
        combos = min(sharks, swimmers)
        total_score += combos
        score_breakdown.append(f"{combos} Shark+Swimmer combo(s): {combos} pts")
        swimmers -= combos  # reduce swimmer count after use

    leftover_sharks = sharks - min(sharks, card_counts.get("swimmer", 0))
    if leftover_sharks > 0:
        score_breakdown.append(f"{leftover_sharks} leftover Shark(s): 0 pts")

    # 🪼 Jellyfish + Swimmer
    if jellyfish > 0 and swimmers > 0:
        combos = min(jellyfish, swimmers)
        total_score += combos
        score_breakdown.append(f"{combos} Jellyfish+Swimmer combo(s): {combos} pts")
        swimmers -= combos

    leftover_jellyfish = jellyfish - min(jellyfish, card_counts.get("swimmer", 0))
    if leftover_jellyfish > 0:
        score_breakdown.append(f"{leftover_jellyfish} leftover Jellyfish(es): 0 pts")

    if swimmers > 0:
        score_breakdown.append(f"{swimmers} leftover Swimmer(s): 0 pts")

    # 🦞 Crab + Lobster
    crabs = card_counts.get("crab", 0)
    lobsters = card_counts.get("lobster", 0)
    if crabs > 0 and lobsters > 0:
        combos = min(crabs, lobsters)
        total_score += combos
        score_breakdown.append(f"{combos} Crab+Lobster combo(s): {combos} pts")
        crabs -= combos
        lobsters -= combos
    leftover_crabs = crabs - min(crabs, card_counts.get("lobster", 0))
    if leftover_crabs > 0:
        if card_counts.get("basket", 0) > 0:
            score_breakdown.append(f"{leftover_crabs} leftover Crab(s): counted by Basket")
        else:
            score_breakdown.append(f"{leftover_crabs} leftover Crab(s): 0 pts")
    if lobsters > 0:
        score_breakdown.append(f"{lobsters} leftover Lobster(s): 0 pts")

        # 🩷 Starfish Trio Logic
    starfish = card_counts.get("starfish", 0)
    if starfish > 0:
        trio_points = 0
        used_starfish = 0

        # Define which pairs can form duos
        duo_pairs = {
            "crab": card_counts.get("crab", 0) // 2,
            "boat": card_counts.get("boat", 0) // 2,
            "fish": card_counts.get("fish", 0) // 2,
            "shark_swimmer": min(card_counts.get("shark", 0), card_counts.get("swimmer", 0)),
            "jellyfish_swimmer": min(card_counts.get("jellyfish", 0), card_counts.get("swimmer", 0)),
            "crab_lobster": min(card_counts.get("crab", 0), card_counts.get("lobster", 0)),
        }

        # Each trio replaces the duo score (1 point) with 3 points → net gain of +2
        for pair_name, num_duos in duo_pairs.items():
            while num_duos > 0 and starfish > 0:
                trio_points += 3
                used_starfish += 1
                starfish -= 1
                num_duos -= 1

        if used_starfish > 0:
            total_score += trio_points  # already accounts for trio points
            score_breakdown.append(f"{used_starfish} Starfish Trio(s): {trio_points} pts (duo effect canceled)")
    
    # --- Multiplier Cards ---
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

    if "basket" in card_counts and "crab" in card_counts:
        points = card_counts["basket"] * card_counts["crab"]
        total_score += points
        score_breakdown.append(f"Basket + Crabs: {points} pts")

    # --- Final Output ---
    if not score_breakdown:
        return (
            "I couldn't find any scorable cards in your message. Try again! "
            "If you were trying to score a mermaid card, do it under /color_bonus.",
            {},
        )

    response_text = "Here's your score breakdown:\n"
    response_text += "\n".join(f"• {item}" for item in score_breakdown)
    response_text += f"\n\n**Total Score: {total_score}**"

    return response_text, card_counts


def calculate_color_bonus(card_text: str, called_last_chance: bool = True, caller: bool = True, caller_succeeded: bool = True):
    """Calculates color bonus according to official Sea Salt & Paper rules."""
    if not called_last_chance:
        return 0, "No color bonus is scored when the round ends with **Stop**."

    pattern = re.compile(r"(\d+)\s+([a-zA-Z]+)")
    matches = pattern.findall(card_text.lower())

    if not matches:
        return 0, "Please list your cards by color count. Example: `/color-bonus 4 blue, 3 pink, 1 mermaid`"

    mermaid_count = 0
    color_counts = []

    for count_str, name in matches:
        count = int(count_str)
        if "mermaid" in name:
            mermaid_count = count
        else:
            color_counts.append(count)

    bonus_points = 0
    if mermaid_count >= 1:
        color_counts.sort(reverse=True)
        groups_to_score = min(mermaid_count, len(color_counts))
        selected_groups = color_counts[:groups_to_score]
        bonus_points = sum(selected_groups)
        breakdown = " + ".join(map(str, selected_groups))
        explanation = (
            f"You have **{mermaid_count} Mermaid(s)** → score your top **{groups_to_score}** color group(s): {breakdown}.\n"
            f"**Total Color Bonus: {bonus_points}**"
        )
    else:
        bonus_points = max(color_counts) if color_counts else 0
        explanation = (
            f"No Mermaids → score your largest color group only.\n"
            f"**Total Color Bonus: {bonus_points}**"
        )

    if caller:
        if caller_succeeded:
            explanation += "\n(Called Last Chance and succeeded: you keep your full points **plus** this bonus.)"
        else:
            explanation += "\n(Called Last Chance and failed: you score **only this color bonus**.)"
    else:
        if caller_succeeded:
            explanation += "\n(Another player called Last Chance and succeeded: you score **only this color bonus**.)"
        else:
            bonus_points = 0
            explanation += "\n(Caller failed their Last Chance: you score your **normal card points only**, no color bonus.)"

    return bonus_points, explanation
