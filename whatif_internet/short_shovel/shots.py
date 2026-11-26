"""Поиск фото для шортса «Хакер с лопатой» в PD12M (используется pd_search.py)."""
PD_QUERIES = {
    "georgia_land": {"all": [r"georgia|georgian|caucasus|tbilisi|kakheti|svaneti|mtskheta|kazbegi",
                             r"mountains?|village|landscape|valley|river|town|hills"],
                     "not": r"atlanta|savannah|usa|united states|u\.s\.|county|peach|alabama|florida|rug|carpet|kilim|textile"},
    "spade_soil": [r"shovel|spade", r"soil|dirt|ground|earth|digging"],
    "trench_cable": [r"trench|excavat|dug up|digging", r"cables?|wires|pipes?"],
    "fiber_glow": [r"fib(er|re) optic|optical fib(er|re)"],
    "armenia": {"all": [r"armenia|armenian|yerevan|ararat"], "not": r"church interior|manuscript|coin"},
    "phone_nosignal": [r"smartphone|mobile phone|cell phone", r"dark|night|black background|screen"],
    "street_feet": [r"feet|shoes|boots|legs", r"walking|street|sidewalk|pavement"],
    "cable_reel": [r"cable (reel|drum|spool)|reel of cable|spool of (cable|wire)|cable laying|laying cables?"],
}
ASSETS = {k: k for k in PD_QUERIES}
