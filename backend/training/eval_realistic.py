"""A hand-written evaluation set of realistic weather reports.

The synthetic corpus states the event type almost literally ("Heavy rain
reported near Pune"), which is exactly what the keyword classifier searches
for — so accuracy on it is circular and tells us nothing about real intake.

These cases are written the way people actually post: implicit phrasing,
misspellings, Hinglish code-mixing, and consequences described instead of
causes. None of them is drawn from the generator's templates.
"""

# (text, true_label, why_it_is_hard)
REALISTIC_CASES: list[tuple[str, str, str]] = [
    # --- consequence described, event implied ---------------------------------
    ("Roads near Andheri station have turned into rivers, autos are stuck",
     "FLOOD", "consequence only, no keyword"),
    ("Knee deep water inside shops at Dadar market, nothing moving",
     "FLOOD", "consequence only"),
    ("Cant see the building across the road this morning in Delhi",
     "FOG", "consequence only, misspelling"),
    ("Flights at Indira Gandhi airport delayed again, zero visibility since 5am",
     "FOG", "implicit, domain knowledge"),
    ("AC has been running non stop since morning and still sweating in Nagpur",
     "HEATWAVE", "consequence only"),
    ("Three people admitted with heat stroke in Jhansi today",
     "HEATWAVE", "medical consequence"),
    ("Hoardings came down near the flyover, wind is howling in Chennai",
     "STRONG_WIND", "consequence only"),
    ("Sky went completely dark at 3pm and the power just tripped in Kolkata",
     "THUNDERSTORM", "implicit"),

    # --- Hinglish / code-mixed ------------------------------------------------
    ("Bhai Mumbai mein bohot paani bhar gaya hai, office jaana mushkil",
     "FLOOD", "Hinglish, romanised"),
    ("Aaj Jaipur mein bahut garmi hai, bahar nikalna mushkil",
     "HEATWAVE", "Hinglish, romanised"),
    ("Delhi mein aaj subah kuch dikh hi nahi raha, poora dhundh hai",
     "FOG", "Hinglish, romanised"),
    ("Baarish ho rahi hai Pune mein pichle do ghante se",
     "RAIN", "Hinglish, romanised"),

    # --- misspellings and informal register -----------------------------------
    ("heavvy rainfal in kochi since morning, drenched completely",
     "RAIN", "misspelling"),
    ("thunderstrom warning for bhopal tonight, stay indoors",
     "THUNDERSTORM", "misspelling"),
    ("dust evrywhere in jodhpur, cant even open eyes",
     "DUST_STORM", "misspelling + consequence"),

    # --- native script, no transliteration ------------------------------------
    ("अहमदाबाद में आज बहुत तेज़ धूल उड़ रही है, कुछ दिखाई नहीं दे रहा",
     "DUST_STORM", "Hindi, implicit"),
    ("गुवाहाटी में लगातार पानी बरस रहा है", "RAIN", "Hindi"),
    ("સુરતમાં રસ્તા પર પાણી ભરાઈ ગયું છે", "FLOOD", "Gujarati"),

    # --- negation and near-miss traps ----------------------------------------
    ("No rain in Bengaluru today despite the forecast, just heat",
     "HEATWAVE", "negation trap — mentions rain"),
    ("Fog warning was issued but visibility is fine, only strong winds now",
     "STRONG_WIND", "negation trap — mentions fog"),
]
