"""Поиск фото для шортса «Пчела или оса» в PD12M (pd_search.py)."""
PD_QUERIES = {
    "bee_fuzzy": [r"honey ?bee|bumble ?bee|\bbees?\b", r"close-up|close up|macro|fuzzy|hairy|furry|pollen"],
    "bee_flower": [r"honey ?bee|\bbees?\b", r"flower|nectar|blossom"],
    "wasp_close": {"all": [r"yellow ?jackets?|vespula|common wasp|german wasp|paper wasps?|polistes|\\bwasps?\\b"], "not": r"background|lateral|dorsal|studio|spider|parasitic|mud|velvet|potter|sawfly"},
    "wasp_food": {"all": [r"\bwasps?\b|yellow ?jacket", r"eating|feeding|fruit|meat|jam|drink|sugar|apple|grape|pear|plum"],
                  "not": r"spider|parasitic|mud"},
    "honeycomb": [r"honeycomb|honey comb", r"bees|wax|honey|cells"],
    "wasp_nest": [r"wasp nest|wasps' nest|paper nest|hornet nest|hornets' nest|wasp's nest|nest of wasps"],
    "hornet": {"all": [r"\\bhornets?\\b|european hornet|vespa crabro|giant hornet|vespa velutina|vespa mandarinia"], "not": r"scooter|motor|piaggio|bike|vehicle|logo|background"},
    "bumblebee": [r"bumble ?bee|bombus"],
    "honeybee_hand": [r"\bbees?\b|honey ?bee", r"hand|finger|skin|arm"],
    "picnic": [r"picnic|outdoor table|garden table", r"food|drinks|lemonade|fruit|cake|plates"],
    "jam": [r"\bjam\b|jams|marmalade|honey jar|jar of jam|preserves"],
    "wasp_flower": {"all": [r"\bwasps?\b", r"flower|blossom|nectar"], "not": r"spider|parasitic"},
}
PD_BAD = (r"painting|drawing|illustration|engraving|lithograph|sketch|diagram|poster|postcard|stamp|cartoon|"
          r"watercolor|etching|woodcut|print of|map of|specimen|herbarium|pinned|museum|logo|coin|dead|preserved|"
          r"white background")
ASSETS = {k: k for k in PD_QUERIES}
