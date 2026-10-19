"""
Runtime Question & Scene Customization Pipeline for MyInteliBooks.

Dynamically personalizes question text, mathematical visual objects,
and thematic backgrounds based on child interests:
- Favourite Foods (Pizza, Burger, Ice Cream, etc., or custom)
- Favourite Sports (Football, Tennis, Basketball, Swimming, etc., or custom)
- Hobbies & Toys (Gardening, Lego, Painting, Toy Cars, etc., or custom)
- Famous Characters & Cartoons (Spider-Man, Elsa, Pikachu, Paw Patrol, etc., or custom)

Ensures mathematical correctness (answers and counts are preserved 100%)
while transforming stems into personalized adventures (e.g. gardening equipement
in a lush garden, footballs on a pitch, or pizza slices in a cozy kitchen).
"""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional, Tuple


# Known default countable nouns across all grade question banks
_DEFAULT_OBJECT_TOKENS = {
    # Fruit / Food
    "apples": ("apple", "apples"),
    "apple": ("apple", "apples"),
    "mangoes": ("mango", "mangoes"),
    "mango": ("mango", "mangoes"),
    "bananas": ("banana", "bananas"),
    "banana": ("banana", "bananas"),
    "oranges": ("orange", "oranges"),
    "orange": ("orange", "oranges"),
    "strawberries": ("strawberry", "strawberries"),
    "strawberry": ("strawberry", "strawberries"),
    "biscuits": ("biscuit", "biscuits"),
    "biscuit": ("biscuit", "biscuits"),
    "cookies": ("cookie", "cookies"),
    "cookie": ("cookie", "cookies"),
    "cupcakes": ("cupcake", "cupcakes"),
    "cupcake": ("cupcake", "cupcakes"),
    "breadsticks": ("breadstick", "breadsticks"),
    "breadstick": ("breadstick", "breadsticks"),
    "ice lollies": ("ice lolly", "ice lollies"),
    "ice lolly": ("ice lolly", "ice lollies"),
    "ice-lollies": ("ice lolly", "ice lollies"),
    "ice-lolly": ("ice lolly", "ice lollies"),
    "pancakes": ("pancake", "pancakes"),
    "pancake": ("pancake", "pancakes"),
    "doughnuts": ("doughnut", "doughnuts"),
    "doughnut": ("doughnut", "doughnuts"),
    "donuts": ("donut", "donuts"),
    "donut": ("donut", "donuts"),
    "carrots": ("carrot", "carrots"),
    "carrot": ("carrot", "carrots"),
    "pears": ("pear", "pears"),
    "pear": ("pear", "pears"),
    "peaches": ("peach", "peaches"),
    "peach": ("peach", "peaches"),
    "cherries": ("cherry", "cherries"),
    "cherry": ("cherry", "cherries"),
    "grapes": ("grape", "grapes"),
    "grape": ("grape", "grapes"),
    "watermelons": ("watermelon", "watermelons"),
    "watermelon": ("watermelon", "watermelons"),
    "pineapples": ("pineapple", "pineapples"),
    "pineapple": ("pineapple", "pineapples"),
    "muffins": ("muffin", "muffins"),
    "muffin": ("muffin", "muffins"),
    "sweets": ("sweet", "sweets"),
    "sweet": ("sweet", "sweets"),
    "chocolates": ("chocolate", "chocolates"),
    "chocolate": ("chocolate", "chocolates"),

    # Toys & Hobbies
    "balloons": ("balloon", "balloons"),
    "balloon": ("balloon", "balloons"),
    "marbles": ("marble", "marbles"),
    "marble": ("marble", "marbles"),
    "toy cars": ("toy car", "toy cars"),
    "toy car": ("toy car", "toy cars"),
    "cars": ("car", "cars"),
    "car": ("car", "cars"),
    "toy trains": ("toy train", "toy trains"),
    "toy train": ("toy train", "toy trains"),
    "trains": ("train", "trains"),
    "train": ("train", "trains"),
    "blocks": ("block", "blocks"),
    "block": ("block", "blocks"),
    "counting blocks": ("counting block", "counting blocks"),
    "counting block": ("counting block", "counting blocks"),
    "pencils": ("pencil", "pencils"),
    "pencil": ("pencil", "pencils"),
    "crayons": ("crayon", "crayons"),
    "crayon": ("crayon", "crayons"),
    "stickers": ("sticker", "stickers"),
    "sticker": ("sticker", "stickers"),
    "books": ("book", "books"),
    "book": ("book", "books"),
    "paint pots": ("paint pot", "paint pots"),
    "paint pot": ("paint pot", "paint pots"),
    "gemstones": ("gemstone", "gemstones"),
    "gemstone": ("gemstone", "gemstones"),
    "gems": ("gem", "gems"),
    "gem": ("gem", "gems"),
    "seashells": ("seashell", "seashells"),
    "seashell": ("seashell", "seashells"),
    "shells": ("shell", "shells"),
    "shell": ("shell", "shells"),
    "kites": ("kite", "kites"),
    "kite": ("kite", "kites"),
    "candles": ("candle", "candles"),
    "candle": ("candle", "candles"),
    "buttons": ("button", "buttons"),
    "button": ("button", "buttons"),
    "counters": ("counter", "counters"),
    "counter": ("counter", "counters"),
    "items": ("item", "items"),
    "item": ("item", "items"),
    "objects": ("object", "objects"),
    "object": ("object", "objects"),
    "figures": ("figure", "figures"),
    "figure": ("figure", "figures"),
    "bird figures": ("bird figure", "bird figures"),
    "bird figure": ("bird figure", "bird figures"),
    "birds": ("bird", "birds"),
    "bird": ("bird", "birds"),
}


# Pre-mapped replacements and environments for popular hobbies
HOBBY_THEMES = {
    "gardening": {
        "singular": "flower pot",
        "plural": "flower pots",
        "alternates": [
            ("flower pot", "flower pots"),
            ("watering can", "watering cans"),
            ("sunflower", "sunflowers"),
            ("tulip", "tulips"),
            ("seed packet", "seed packets"),
        ],
        "environment": (
            "A bright, sunny home flower garden with colorful blooming flowerbeds, terracotta pots, "
            "a charming wooden garden shed, green lawn, and sunlit outdoor atmosphere. "
            "The foreground features a clean garden potting bench or lawn where flower pots and gardening tools are neatly placed."
        ),
        "attire": (
            "The characters wear cute, colorful gardening aprons, casual gardening clothes, sun hats, "
            "or cheerful denim overalls, looking like happy young gardeners."
        ),
    },
    "lego": {
        "singular": "Lego brick",
        "plural": "Lego bricks",
        "alternates": [
            ("Lego brick", "Lego bricks"),
            ("building block", "building blocks"),
            ("colourful construction tile", "colourful construction tiles"),
        ],
        "environment": (
            "A bright, cheerful children's playroom and creation studio with organized Lego sorting trays, "
            "colorful building mats, and playful display shelves with soft depth of field."
        ),
        "attire": (
            "The characters wear cheerful, vibrant casual clothes perfect for creative indoor building activities."
        ),
    },
    "painting": {
        "singular": "paint pot",
        "plural": "paint pots",
        "alternates": [
            ("paint pot", "paint pots"),
            ("paintbrush", "paintbrushes"),
            ("bottle of colourful paint", "bottles of colourful paint"),
        ],
        "environment": (
            "A sunlit, inspiring art studio with easels, white canvases, wooden art tables, and colorful paint splashes."
        ),
        "attire": (
            "The characters wear cute artist smocks or paint-splattered aprons with sleeves rolled up, looking like enthusiastic young painters."
        ),
    },
    "art": {
        "singular": "paint pot",
        "plural": "paint pots",
        "alternates": [
            ("paint pot", "paint pots"),
            ("colourful marker", "colourful markers"),
            ("sketchbook", "sketchbooks"),
        ],
        "environment": "A warm, bright art workshop with colorful art supplies, paper rolls, and wooden craft tables.",
        "attire": "Cute art aprons and creative casual wear.",
    },
    "toy_cars": {
        "singular": "toy race car",
        "plural": "toy race cars",
        "alternates": [
            ("toy race car", "toy race cars"),
            ("mini model car", "mini model cars"),
            ("toy racing truck", "toy racing trucks"),
        ],
        "environment": (
            "A lively playroom floor featuring miniature toy roads, wooden racetrack loops, and checkered flag pit-stops."
        ),
        "attire": "Cool sporty casual clothing or mini racing jackets.",
    },
    "reading": {
        "singular": "storybook",
        "plural": "storybooks",
        "alternates": [
            ("storybook", "storybooks"),
            ("adventure book", "adventure books"),
            ("illustrated book", "illustrated books"),
        ],
        "environment": (
            "A cozy, peaceful children's library nook with plush cushions, warm wooden bookshelves, and soft window sunlight."
        ),
        "attire": "Comfortable, cozy knit sweaters and relaxed casual clothes.",
    },
    "baking": {
        "singular": "cupcake",
        "plural": "cupcakes",
        "alternates": [
            ("cupcake", "cupcakes"),
            ("cookie", "cookies"),
            ("fresh bread roll", "fresh bread rolls"),
        ],
        "environment": "A warm bakery kitchen with flour-dusted wooden counters and stone ovens.",
        "attire": "White baker aprons and chef hats.",
    },
    "fishing": {
        "singular": "toy fish",
        "plural": "toy fish",
        "alternates": [
            ("toy fish", "toy fish"),
            ("colourful float", "colourful floats"),
            ("fishing bobber", "fishing bobbers"),
        ],
        "environment": "A calm, picturesque freshwater lakeside dock with green reeds and clear blue water.",
        "attire": "Outdoor sun hats, lightweight waterproof jackets, and casual outdoor gear.",
    },
}

# Pre-mapped replacements and environments for popular sports
SPORT_THEMES = {
    "football": {
        "singular": "football",
        "plural": "footballs",
        "alternates": [
            ("football", "footballs"),
            ("training cone", "training cones"),
            ("sports water bottle", "sports water bottles"),
            ("winner medal", "winner medals"),
        ],
        "environment": (
            "A sunny, pristine green football pitch with white painted lines, goal nets, and open athletic park background."
        ),
        "attire": (
            "The characters wear clean, colorful football kits/jerseys, athletic shorts, and sporty trainers, ready to play."
        ),
    },
    "soccer": {
        "singular": "soccer ball",
        "plural": "soccer balls",
        "alternates": [
            ("soccer ball", "soccer balls"),
            ("training marker", "training markers"),
        ],
        "environment": "A bright green grass soccer stadium training ground with nets and cones.",
        "attire": "Official athletic soccer jerseys and team tracksuits.",
    },
    "tennis": {
        "singular": "tennis ball",
        "plural": "tennis balls",
        "alternates": [
            ("tennis ball", "tennis balls"),
            ("tennis racket", "tennis rackets"),
            ("wristband", "wristbands"),
        ],
        "environment": (
            "A professional sunlit outdoor tennis court with pristine green and blue hardcourt, net, and courtside benches."
        ),
        "attire": "Crisp white or vibrant tennis polo shirts, athletic shorts or skirts, and sports visors.",
    },
    "basketball": {
        "singular": "basketball",
        "plural": "basketballs",
        "alternates": [
            ("basketball", "basketballs"),
            ("mini basketball hoop", "mini basketball hoops"),
        ],
        "environment": "A polished indoor hardwood basketball gymnasium court or vibrant outdoor park court with hoop backboards.",
        "attire": "Sleeveless basketball jerseys and sports high-top trainers.",
    },
    "swimming": {
        "singular": "pair of swimming goggles",
        "plural": "swimming goggles",
        "alternates": [
            ("pair of swimming goggles", "swimming goggles"),
            ("swimming kickboard", "swimming kickboards"),
            ("swim float", "swim floats"),
        ],
        "environment": "A bright, clean indoor Olympic-style community swimming pool with shimmering crystal-blue water and tiled lanes.",
        "attire": "Bright sports swimsuits or rash guards with swim caps and goggles rested comfortably.",
    },
    "cricket": {
        "singular": "cricket ball",
        "plural": "cricket balls",
        "alternates": [
            ("cricket ball", "cricket balls"),
            ("wooden cricket bat", "wooden cricket bats"),
            ("cricket wicket", "cricket wickets"),
        ],
        "environment": "A lush English cricket ground with green turf, white boundary ropes, and cricket pavilion.",
        "attire": "Traditional white cricket polo and athletic sports trousers.",
    },
    "cycling": {
        "singular": "cycling helmet",
        "plural": "cycling helmets",
        "alternates": [
            ("cycling helmet", "cycling helmets"),
            ("bicycle bell", "bicycle bells"),
            ("sports water bottle", "sports water bottles"),
        ],
        "environment": "A scenic, sunny paved park cycling path surrounded by tall green trees and blooming wild flowers.",
        "attire": "Colorful cycling jerseys, safety helmets, and athletic cycling gloves.",
    },
    "gymnastics": {
        "singular": "gymnastics ribbon",
        "plural": "gymnastics ribbons",
        "alternates": [
            ("gymnastics ribbon", "gymnastics ribbons"),
            ("gymnastics hoop", "gymnastics hoops"),
            ("balance beanbag", "balance beanbags"),
        ],
        "environment": "A modern gymnastics arena with padded floor mats, balance beams, and bright gymnasium lighting.",
        "attire": "Sleek, sparkly gymnastics leotards or athletic activewear.",
    },
}

# Pre-mapped replacements and environments for popular foods
FOOD_THEMES = {
    "pizza": {
        "singular": "slice of pizza",
        "plural": "slices of pizza",
        "alternates": [
            ("slice of pizza", "slices of pizza"),
            ("mini pizza", "mini pizzas"),
        ],
        "environment": "A cozy, warm family kitchen and dining table neatly set with clean plates, napkins, and an authentic pizza paddle.",
        "attire": "Comfortable, cheerful casual clothes suitable for enjoying lunch with family.",
    },
    "burger": {
        "singular": "mini burger",
        "plural": "mini burgers",
        "alternates": [
            ("mini burger", "mini burgers"),
            ("burger", "burgers"),
        ],
        "environment": "A cheerful garden patio picnic or sunny diner table with checkered napkins.",
        "attire": "Casual summer clothing or picnic shirts.",
    },
    "ice_cream": {
        "singular": "ice cream cone",
        "plural": "ice cream cones",
        "alternates": [
            ("ice cream cone", "ice cream cones"),
            ("ice lolly", "ice lollies"),
            ("cup of frozen yogurt", "cups of frozen yogurt"),
        ],
        "environment": "A charming, pastel-toned seaside ice cream parlour or sunny park ice cream cart.",
        "attire": "Light, breezy summer shirts and happy holiday clothes.",
    },
    "cupcake": {
        "singular": "frosted cupcake",
        "plural": "frosted cupcakes",
        "alternates": [
            ("frosted cupcake", "frosted cupcakes"),
            ("sprinkled cupcake", "sprinkled cupcakes"),
        ],
        "environment": "A lovely home baking kitchen with cake stands and pastel party decorations.",
        "attire": "Cute kitchen aprons or colorful party tops.",
    },
    "strawberries": {
        "singular": "ripe strawberry",
        "plural": "ripe strawberries",
        "alternates": [
            ("ripe strawberry", "ripe strawberries"),
            ("punnet of strawberries", "punnets of strawberries"),
        ],
        "environment": "A sunny English strawberry farm with green leafy rows and woven harvest baskets.",
        "attire": "Gardener dungarees, sun hats, and cheerful casual shirts.",
    },
    "pancakes": {
        "singular": "golden pancake",
        "plural": "golden pancakes",
        "alternates": [
            ("golden pancake", "golden pancakes"),
            ("fluffy pancake", "fluffy pancakes"),
        ],
        "environment": "A bright morning breakfast table with maple syrup pitchers and fresh fruit bowls.",
        "attire": "Cozy morning loungewear or cheerful breakfast casuals.",
    },
    "donuts": {
        "singular": "frosted donut",
        "plural": "frosted donuts",
        "alternates": [
            ("frosted donut", "frosted donuts"),
            ("glazed doughnut", "glazed doughnuts"),
        ],
        "environment": "A colourful pastry counter and cozy family cafe table.",
        "attire": "Vibrant everyday casual wear.",
    },
    "pasta": {
        "singular": "bowl of pasta",
        "plural": "bowls of pasta",
        "alternates": [
            ("bowl of pasta", "bowls of pasta"),
            ("plate of spaghetti", "plates of spaghetti"),
        ],
        "environment": "A cozy rustic dining table with warm lighting and authentic Italian ceramic dinnerware.",
        "attire": "Neat, comfortable dining attire.",
    },
    "cookies": {
        "singular": "chocolate cookie",
        "plural": "chocolate cookies",
        "alternates": [
            ("chocolate cookie", "chocolate cookies"),
            ("crunchy biscuit", "crunchy biscuits"),
        ],
        "environment": "A warm bakery cooling rack and sunny kitchen table.",
        "attire": "Cute chef aprons or everyday play clothes.",
    },
    "watermelon": {
        "singular": "slice of juicy watermelon",
        "plural": "slices of juicy watermelon",
        "alternates": [
            ("slice of watermelon", "slices of watermelon"),
            ("wedge of watermelon", "wedges of watermelon"),
        ],
        "environment": "A sunny summer park picnic blanket surrounded by green trees and wildflowers.",
        "attire": "Summer t-shirts and shorts.",
    },
    "apples": {
        "singular": "crisp apple",
        "plural": "crisp apples",
        "alternates": [
            ("crisp red apple", "crisp red apples"),
            ("green apple", "green apples"),
        ],
        "environment": "A sun-drenched apple orchard with wooden harvest crates and fruit-laden apple trees.",
        "attire": "Farmer dungarees, denim shirts, and sun hats.",
    },
}

# Thematic mapping for famous characters & cartoons
CHARACTER_THEMES = {
    "spiderman": {
        "singular": "Spider-Man action figure",
        "plural": "Spider-Man action figures",
        "alternates": [
            ("Spider-Man action figure", "Spider-Man action figures"),
            ("Spider-Man sticker", "Spider-Man stickers"),
            ("hero web shooter toy", "hero web shooter toys"),
        ],
        "environment": "A vibrant activity playroom decorated with Spider-Man city murals, superhero posters, and building blocks.",
        "attire": "Casual superhero t-shirts or red and blue hoodies.",
    },
    "batman": {
        "singular": "Batman batarang toy",
        "plural": "Batman batarang toys",
        "alternates": [
            ("Batman action figure", "Batman action figures"),
            ("Batman collector card", "Batman collector cards"),
        ],
        "environment": "A cool detective playroom with high-tech superhero gadgets and sleek midnight-blue decor.",
        "attire": "Cool dark graphic superhero tees or casual hoodies.",
    },
    "elsa": {
        "singular": "crystal snowflake wand",
        "plural": "crystal snowflake wands",
        "alternates": [
            ("Elsa ice crystal figure", "Elsa ice crystal figures"),
            ("sparkling snowflake badge", "sparkling snowflake badges"),
        ],
        "environment": "An enchanting winter wonderland themed playroom with soft glowing ice crystals, blue fairy lights, and snow decor.",
        "attire": "Sparkly pale blue cardigans or elegant winter party clothes.",
    },
    "pikachu": {
        "singular": "Pikachu plush toy",
        "plural": "Pikachu plush toys",
        "alternates": [
            ("Pikachu figurine", "Pikachu figurines"),
            ("Pokeball toy", "Pokeball toys"),
            ("lightning bolt badge", "lightning bolt badges"),
        ],
        "environment": "A vibrant anime/gaming activity lounge with colorful Pokemon posters, yellow cushions, and gaming displays.",
        "attire": "Cheerful yellow and black casual hoodies or graphic tees.",
    },
    "sonic": {
        "singular": "golden Sonic ring",
        "plural": "golden Sonic rings",
        "alternates": [
            ("Sonic toy figurine", "Sonic toy figurines"),
            ("golden power ring", "golden power rings"),
        ],
        "environment": "A high-speed adventure themed playroom with checkered green hills and blue loops in the background.",
        "attire": "Sporty blue track jackets and red athletic sneakers.",
    },
    "paw_patrol": {
        "singular": "Paw Patrol rescue badge",
        "plural": "Paw Patrol rescue badges",
        "alternates": [
            ("Paw Patrol rescue badge", "Paw Patrol rescue badges"),
            ("Paw Patrol rescue pup toy", "Paw Patrol rescue pup toys"),
        ],
        "environment": "A high-tech adventure rescue station themed playroom with puppy pawprints and bright look-out tower decor.",
        "attire": "Cute colorful rescue vests and sporty caps.",
    },
    "peppa_pig": {
        "singular": "Peppa Pig story badge",
        "plural": "Peppa Pig story badges",
        "alternates": [
            ("Peppa Pig story badge", "Peppa Pig story badges"),
            ("Peppa toy figurine", "Peppa toy figurines"),
        ],
        "environment": "A sunny, cheerful grassy hill with blue skies, cute yellow sunshine, and pastel family playground.",
        "attire": "Bright red or pink cheerful everyday shirts and yellow boots.",
    },
    "spongebob": {
        "singular": "pineapple house toy",
        "plural": "pineapple house toys",
        "alternates": [
            ("SpongeBob figurine", "SpongeBob figurines"),
            ("jellyfish toy", "jellyfish toys"),
        ],
        "environment": "A playful underwater themed room with sea bubble wallpaper and cheerful yellow decorations.",
        "attire": "Fun yellow graphic tees and nautical shorts.",
    },
    "bluey": {
        "singular": "Bluey keepsake figure",
        "plural": "Bluey keepsake figures",
        "alternates": [
            ("Bluey keepsake figure", "Bluey keepsake figures"),
            ("magic xylophone toy", "magic xylophone toys"),
        ],
        "environment": "A cozy, sunlit suburban Queensland veranda and playroom filled with wooden toys and colorful cushions.",
        "attire": "Comfortable, cheerful play clothes.",
    },
}


def _slugify(text: str) -> str:
    """Normalize user input to clean lookup key."""
    s = re.sub(r"[^\w\s-]", "", str(text or "").lower())
    s = re.sub(r"[\s-]+", "_", s).strip("_")
    return s


def _make_custom_plural_and_singular(name: str) -> Tuple[str, str]:
    """Infer sensible singular and plural forms for custom user input."""
    clean = name.strip()
    clean_lower = clean.lower()
    
    # Common English plural endings
    if clean_lower.endswith("ies"):
        singular = clean[:-3] + "y"
        plural = clean
    elif clean_lower.endswith(("boxes", "watches", "dishes", "glasses")):
        singular = clean[:-2]
        plural = clean
    elif clean_lower.endswith("s") and not clean_lower.endswith(("ss", "us", "is")):
        singular = clean[:-1]
        plural = clean
    else:
        singular = clean
        if clean_lower.endswith(("ch", "sh", "x", "s", "z")):
            plural = clean + "es"
        elif clean_lower.endswith("y") and len(clean_lower) > 1 and clean_lower[-2] not in "aeiou":
            plural = clean[:-1] + "ies"
        else:
            plural = clean + "s"
            
    return singular, plural


def resolve_interest_theme(
    category: str,
    name: str,
) -> Dict[str, Any]:
    """
    Produce singular/plural tokens and environment context for any selected item,
    including custom user inputs!
    """
    slug = _slugify(name)
    
    # Check pre-mapped dictionaries
    lookup_maps = {
        "hobby": HOBBY_THEMES,
        "sport": SPORT_THEMES,
        "food": FOOD_THEMES,
        "character": CHARACTER_THEMES,
    }
    
    cat_map = lookup_maps.get(category, {})
    for k, v in cat_map.items():
        if k in slug or slug in k:
            return {
                "category": category,
                "name": name,
                "singular": v["singular"],
                "plural": v["plural"],
                "environment": v.get("environment", ""),
                "attire": v.get("attire", ""),
            }
            
    # Also cross-check all maps if not found under specific category
    for cm in lookup_maps.values():
        for k, v in cm.items():
            if k in slug or slug in k:
                return {
                    "category": category,
                    "name": name,
                    "singular": v["singular"],
                    "plural": v["plural"],
                    "environment": v.get("environment", ""),
                    "attire": v.get("attire", ""),
                }

    # Fallback for custom user inputs (e.g. custom sport "Karate", custom food "Sushi")
    sing, plur = _make_custom_plural_and_singular(name)
    
    if category == "food":
        env = f"A warm, inviting family dining table neatly set with clean plates and napkins to enjoy delicious {plur}."
        attire = "Comfortable, cheerful everyday casual wear."
    elif category == "sport":
        env = f"A vibrant, sunny athletic sports field or training area prepared for {name} practice with sports equipment in the foreground."
        attire = f"Athletic sports training jerseys and sneakers suited for {name}."
    elif category == "hobby":
        env = f"A bright, cheerful activity room or outdoor setting dedicated to {name}, with equipment neatly organized."
        attire = "Comfortable, energetic casual activity clothing."
    elif category == "character":
        sing = f"{name} figurine"
        plur = f"{name} figurines"
        env = f"A vibrant, colorful play and activity room decorated with cheerful {name} themed posters and banners in the background."
        attire = f"Cool graphic t-shirts or casual hoodies featuring vibrant {name} colours."
    else:
        env = "A bright, cheerful learning and activity setting with natural daylight."
        attire = "Neat, colorful casual wear."
        
    return {
        "category": category,
        "name": name,
        "singular": sing,
        "plural": plur,
        "environment": env,
        "attire": attire,
    }


def customize_question_and_stem(
    stem: Dict[str, Any],
    question_text: str,
    meta: Dict[str, Any],
    *,
    favourite_foods: Optional[List[str]] = None,
    favourite_sports: Optional[List[str]] = None,
    favourite_hobbies: Optional[List[str]] = None,
    favourite_characters: Optional[List[str]] = None,
    favourite_cartoons: Optional[List[str]] = None,
    question_index: int = 0,
) -> Tuple[str, Dict[str, Any], Dict[str, str]]:
    """
    Main runtime customization pipeline entrypoint.
    
    Cycles through selected child preferences across workbook questions,
    replaces countable objects in question text & visual_groups, and
    provides customized thematic background/attire specifications for AI rendering.
    
    Returns:
        (customized_question_text, customized_meta, thematic_context_dict)
    """
    favourite_foods = [f.strip() for f in (favourite_foods or []) if f.strip()]
    favourite_sports = [s.strip() for s in (favourite_sports or []) if s.strip()]
    favourite_hobbies = [h.strip() for h in (favourite_hobbies or []) if h.strip()]
    chars = [c.strip() for c in (favourite_characters or []) if c.strip()]
    cartoons = [c.strip() for c in (favourite_cartoons or []) if c.strip()]
    all_characters = chars + [c for c in cartoons if c not in chars]

    # Collect available categories into an alternating playlist so ALL chosen interests appear
    playlist: List[Tuple[str, str]] = []
    
    # Interleave categories: [hobby, sport, food, character]
    max_len = max(len(favourite_hobbies), len(favourite_sports), len(favourite_foods), len(all_characters), 1)
    for idx in range(max_len):
        if idx < len(favourite_hobbies):
            playlist.append(("hobby", favourite_hobbies[idx]))
        if idx < len(favourite_sports):
            playlist.append(("sport", favourite_sports[idx]))
        if idx < len(favourite_foods):
            playlist.append(("food", favourite_foods[idx]))
        if idx < len(all_characters):
            playlist.append(("character", all_characters[idx]))

    # If no preferences selected, return original
    if not playlist:
        return question_text, meta, {}

    # Pick the preference for this specific question index
    category, interest_name = playlist[question_index % len(playlist)]
    theme = resolve_interest_theme(category, interest_name)

    # 1. Identify target object words in the question & meta visual_groups
    target_tokens: List[Tuple[str, str]] = []  # list of (singular, plural)
    
    # Check visual_groups in meta
    visual_groups = meta.get("visual_groups") or []
    for g in visual_groups:
        sing = g.get("singular")
        plur = g.get("plural") or g.get("object_id")
        if sing and plur:
            target_tokens.append((sing.lower(), plur.lower()))
        elif plur:
            target_tokens.append((plur.rstrip("s").lower(), plur.lower()))

    # If visual_groups didn't yield tokens, search question text for known default object tokens
    q_lower = question_text.lower()
    for tok_word, (s_form, p_form) in _DEFAULT_OBJECT_TOKENS.items():
        if re.search(r"\b" + re.escape(tok_word) + r"\b", q_lower):
            if (s_form, p_form) not in target_tokens:
                target_tokens.append((s_form, p_form))

    # If still no known tokens found, check common nouns like "items", "counters"
    if not target_tokens:
        target_tokens.append(("item", "items"))

    # 2. Perform intelligent object word replacement in question_text
    new_singular = theme["singular"]
    new_plural = theme["plural"]
    
    customized_q = question_text
    replaced_any = False

    is_pattern_question = (
        (meta.get("topic") or "").lower() == "patterns"
        or "repeating pattern" in q_lower
        or ("pattern:" in q_lower and "comes next" in q_lower)
    )

    single_pass_pattern = None
    rep_map: Dict[str, str] = {}

    if not is_pattern_question and target_tokens:
        # Build mapping of target word forms to new theme forms
        for s_w, p_w in target_tokens:
            s_clean = (s_w or "").strip().lower()
            p_clean = (p_w or "").strip().lower()
            if p_clean and p_clean not in rep_map:
                rep_map[p_clean] = new_plural
            if s_clean and s_clean not in rep_map:
                rep_map[s_clean] = new_singular

        if rep_map:
            # Sort longest first so compound phrases (e.g. "toy car") match before short ones (e.g. "car")
            sorted_keys = sorted(rep_map.keys(), key=len, reverse=True)
            single_pass_pattern = re.compile(
                r"\b(" + "|".join(re.escape(k) for k in sorted_keys) + r")\b",
                flags=re.IGNORECASE,
            )

            def _single_pass_sub(m: re.Match) -> str:
                matched_str = m.group(0)
                replacement = rep_map.get(matched_str.lower(), matched_str)
                if matched_str.isupper():
                    return replacement.upper()
                if matched_str[0].isupper():
                    return replacement.capitalize()
                return replacement

            new_text = single_pass_pattern.sub(_single_pass_sub, customized_q)
            if new_text != customized_q:
                customized_q = new_text
                replaced_any = True

    # 3. Update meta copy so mathematical counts, visual specs, and answers point to the new objects
    customized_meta = copy.deepcopy(meta)
    if not is_pattern_question:
        new_groups = []
        for g in (customized_meta.get("visual_groups") or []):
            g_copy = dict(g)
            g_copy["object_id"] = new_plural
            g_copy["singular"] = new_singular
            g_copy["plural"] = new_plural
            g_copy["item"] = new_plural
            new_groups.append(g_copy)
        if new_groups:
            customized_meta["visual_groups"] = new_groups

        # Synchronize answer options and correct answer with replaced token in a single pass
        if replaced_any and single_pass_pattern and "answer" in customized_meta:
            ans_dict = customized_meta["answer"]
            old_opts = ans_dict.get("options") or []
            new_opts = [single_pass_pattern.sub(_single_pass_sub, str(opt)) for opt in old_opts]
            if new_opts:
                ans_dict["options"] = new_opts

            corr_str = str(ans_dict.get("correct") or "")
            ans_dict["correct"] = single_pass_pattern.sub(_single_pass_sub, corr_str)

    # 4. Build prompt-ready thematic block
    thematic_info = {
        "theme_name": f"{category.title()}: {interest_name}",
        "environment": theme["environment"],
        "attire": theme["attire"],
        "prompt_block": (
            f"- THEMATIC INTEREST ({category.upper()}): {interest_name}\n"
            f"- ENVIRONMENT & BACKGROUND: {theme['environment']}\n"
            f"- CHARACTER ATTIRE: {theme['attire']}\n"
            f"- PROPS & OBJECTS: " + (
                "The repeating pattern objects from the question must be clearly arranged left-to-right."
                if is_pattern_question else
                f"The learning objects being counted/held MUST strictly be {new_plural}."
            )
        ),
    }

    return customized_q, customized_meta, thematic_info
