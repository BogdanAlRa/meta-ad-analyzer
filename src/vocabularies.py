"""
Controlled vocabularies for ad analysis.
Ported from the Meta Ads Intelligence Platform shared/vocabularies.py.
"""

# --- Claim Types ---
CLAIM_TYPES = [
    "causal",
    "comparative",
    "descriptive",
    "predictive",
    "normative",
    "identity",
    "exclusionary",
    "procedural",
]

# --- Claim Scopes ---
CLAIM_SCOPES = [
    "product_performance",
    "user_outcome",
    "time_to_result",
    "risk_safety",
    "cost_value",
    "social_status",
    "moral_virtue",
    "simplicity_control",
    "novelty_uniqueness",
    "scarcity_access",
    "comfort_convenience",
    "compatibility_fit",
    "compliance_legality",
    "service_support",
    "health_wellness",
]

# --- Polarity ---
POLARITY_TYPES = ["positive", "negative", "neutral"]

# --- Quantification ---
QUANTIFICATION_TYPES = [
    "absolute",
    "bounded",
    "relative",
    "probabilistic",
    "conditional",
    "vague",
]

# --- Confidence Basis ---
CONFIDENCE_BASIS_LEVELS = [
    "direct_quote",
    "multi_signal",
    "implied",
    "weak_signal",
    "conflict_present",
]

# --- Proof Primitive Types ---
PROOF_PRIMITIVE_TYPES = [
    "authority",
    "popularity",
    "demonstration",
    "measurement",
    "narrative_testimony",
    "comparison",
    "guarantee",
    "constraint_scarcity",
    "certification",
    "peer_affiliation",
    "mechanistic_visualization",
]

# --- Proof Source Classes ---
PROOF_SOURCE_CLASSES = [
    "self_asserted",
    "third_party_influencer",
    "third_party_media",
    "institutional",
    "platform_verified",
    "user_generated",
    "peer_network",
    "unknown",
]

# --- Source Weight Map (for proof strength scoring) ---
PROOF_SOURCE_WEIGHTS = {
    "institutional": 1.0,
    "platform_verified": 0.9,
    "third_party_media": 0.8,
    "third_party_influencer": 0.6,
    "user_generated": 0.55,
    "peer_network": 0.55,
    "self_asserted": 0.35,
    "unknown": 0.25,
}

# --- Hook Archetypes ---
ARCHETYPE_NAMES = [
    "direct_address_hook",
    "rapid_montage_hook",
    "problem_agitation_hook",
    "demonstration_hook",
    "social_proof_hook",
    "curiosity_gap_hook",
    "offer_led_hook",
    "before_after_hook",
]

# --- Mechanism Markers ---
STEPWISE_MARKERS = [
    "first", "then", "next", "step 1", "step 2", "after that",
    "starts by", "followed by", "finally",
]

CAUSAL_VERBS = [
    "causes", "triggers", "blocks", "inhibits", "restores",
    "boosts", "reduces", "activates", "converts", "breaks down",
    "absorbs", "stimulates", "regulates", "prevents",
]

NAMED_SYSTEMS = [
    "metabolism", "immune system", "gut", "microbiome", "collagen",
    "cortisol", "insulin", "serotonin", "algorithm", "auction",
    "neural", "cellular", "enzyme", "hormone", "receptor",
]

IO_MARKERS = [
    "because", "therefore", "so that", "which means", "resulting in",
    "leading to", "this allows", "enabling",
]

CONDITION_MARKERS = [
    "when used", "if you", "within", "after", "daily",
    "with regular", "at a dose of", "for best results",
]

# --- Tension Marker Clusters ---
TENSION_MARKERS = {
    "speed_vs_trust": {
        "speed": ["fast", "quick", "immediate", "in days", "overnight", "instant", "rapid"],
        "trust": ["proven", "clinically", "guaranteed", "tested", "verified", "trusted", "science"],
    },
    "simplicity_vs_control": {
        "simplicity": ["easy", "simple", "just", "one-click", "no effort", "automatic"],
        "control": ["customize", "control", "configure", "adjust", "your way", "choose"],
    },
    "cheap_vs_risky": {
        "cheap": ["affordable", "save", "budget", "cheap", "low cost", "value"],
        "risky": ["risk-free", "guarantee", "refund", "no risk", "money back", "safe"],
    },
    "novelty_vs_safety": {
        "novelty": ["new", "revolutionary", "breakthrough", "first", "innovation", "cutting-edge"],
        "safety": ["proven", "trusted", "established", "reliable", "time-tested", "backed by"],
    },
}

# --- Negation Markers ---
NEGATION_MARKERS = [
    "tired of", "sick of", "struggling", "frustrated", "can't",
    "stop", "never", "failing", "don't", "won't", "no more",
    "fed up", "enough of", "hate", "annoying", "painful",
]

# --- Curiosity Markers ---
CURIOSITY_MARKERS = [
    "secret", "nobody tells you", "what if", "you won't believe",
    "the truth about", "most people don't know", "hidden",
    "little-known", "surprising", "shocking", "revealed",
]

# --- Urgency Markers ---
URGENCY_MARKERS = [
    "limited time", "act now", "hurry", "last chance", "today only",
    "expires", "ending soon", "don't miss", "while supplies last",
    "only .* left", "countdown", "deadline", "urgent", "now or never",
]
