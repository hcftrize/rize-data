"""
Commands: /canton, /ecosystem, /vision87, /vision60, /kairos, /cantonboard
Data from entities.json (GitHub) + hardcoded learn box texts.
"""
from utils.github_data import get_entities
from utils.fuzzy import find_entity

# ── /rizeby canton {entity} ───────────────────────────────────────────────────

async def cmd_canton(args: list[str]) -> str:
    if not args:
        return (
            "🏛 *Canton Network Ecosystem*\n\n"
            "Type `/rizeby canton {entity name}` to get info about any of the 290+ entities.\n\n"
            "Examples:\n"
            "`/rizeby canton franklin templeton`\n"
            "`/rizeby canton deutsche bank`\n"
            "`/rizeby canton cumberland`"
        )

    query = " ".join(args)
    entities = await get_entities()
    if not entities:
        return "❌ Could not load Canton entities data."

    entity = find_entity(query, entities)
    if not entity:
        return (
            f"❓ No entity found matching *{query}*.\n\n"
            "Try a partial name or check the spelling.\n"
            "Example: `/rizeby canton bnp` or `/rizeby canton societe`"
        )

    name     = entity.get("name") or entity.get("id", "Unknown")
    tags     = entity.get("tags") or entity.get("categories") or []
    subtitle = entity.get("subtitle") or ""
    text     = entity.get("text") or entity.get("description") or ""
    category = entity.get("category") or entity.get("type") or ""

    tag_str = " · ".join(tags) if isinstance(tags, list) else str(tags)
    if category and category not in tag_str:
        tag_str = f"{category} · {tag_str}" if tag_str else category

    lines = [f"🏛 *{name}*"]
    if tag_str:
        lines.append(f"_{tag_str}_")
    if subtitle:
        lines.append(f"\n{subtitle}")
    if text:
        # Trim to ~600 chars to avoid huge messages
        trimmed = text[:600] + ("…" if len(text) > 600 else "")
        lines.append(f"\n{trimmed}")

    return "\n".join(lines)


# ── /rizeby ecosystem [{entity}] ──────────────────────────────────────────────

# Hardcoded T-RIZE ecosystem entities
TRIZE_ECOSYSTEM = [
    {"id": "canton-network",    "name": "Canton Network",    "tag": "BLOCKCHAIN",     "text": "The institutional-grade blockchain infrastructure that RIZE governance is built on. Canton enables privacy-preserving smart contracts and tokenized real-world assets at scale, with participation from the world's leading financial institutions."},
    {"id": "particula",         "name": "Particula",         "tag": "SERVICES",       "text": "Particula is an independent digital asset risk rating agency — the first to issue a pre-issuance risk rating on the Canton Network, assigning a B+ rating to a tokenized real estate asset. Particula provides institutional-grade risk intelligence for DeFi and tokenized asset markets."},
    {"id": "chainlink",         "name": "Chainlink",         "tag": "ORACLES",        "text": "Chainlink provides RIZE with decentralized oracle infrastructure, enabling secure, tamper-proof price feeds and cross-chain interoperability. As the industry standard for DeFi oracles, Chainlink ensures RIZE governance data is accurate and manipulation-resistant."},
    {"id": "base",              "name": "Base",              "tag": "BLOCKCHAIN",     "text": "Base is the Layer 2 blockchain by Coinbase where RIZE governance smart contracts are deployed. Built on the OP Stack, Base offers low fees, fast finality, and deep Ethereum ecosystem compatibility — making RIZE governance accessible to institutional and retail participants alike."},
    {"id": "fireblocks",        "name": "Fireblocks",        "tag": "CUSTODY",        "text": "Fireblocks provides institutional-grade digital asset custody and transfer infrastructure. As a key custody partner in the T-RIZE ecosystem, Fireblocks enables secure, compliant access to RIZE tokenized assets for institutional investors."},
    {"id": "arrakis",           "name": "Arrakis Finance",   "tag": "LIQUIDITY",      "text": "Arrakis Finance manages automated liquidity strategies for RIZE, optimizing market depth on decentralized exchanges. By automating LP management, Arrakis ensures RIZE maintains healthy liquidity conditions at all times."},
    {"id": "aerodrome",         "name": "Aerodrome Finance", "tag": "DEX",            "text": "Aerodrome is the leading DEX on Base, providing RIZE with deep on-chain liquidity. As the primary AMM venue for RIZE trading on Base, Aerodrome enables efficient price discovery and permissionless access to RIZE."},
    {"id": "dfns",              "name": "Dfns",              "tag": "WALLET INFRA",   "text": "Dfns provides programmable wallet infrastructure for the T-RIZE ecosystem, enabling seamless, compliant onboarding of institutional clients into tokenized real estate investments with enterprise-grade key management."},
    {"id": "ets",               "name": "ETS",               "tag": "SERVICES",       "text": "ETS (European Token Service) provides tokenization and compliance infrastructure for real-world assets on Canton Network, supporting T-RIZE in deploying regulatory-compliant tokenized securities across European markets."},
    {"id": "hashlock",          "name": "Hashlock",          "tag": "SECURITY",       "text": "Hashlock is a smart contract auditing and security firm that has reviewed RIZE governance contracts. Their independent security assessments ensure the integrity of RIZE on-chain infrastructure."},
    {"id": "ekitas",            "name": "Ekitas",            "tag": "SERVICES",       "text": "Ekitas provides institutional real estate transaction advisory within the T-RIZE ecosystem, bridging traditional real estate capital markets with blockchain-native tokenized asset distribution."},
    {"id": "lvc",               "name": "LVC",               "tag": "SERVICES",       "text": "LVC is a strategic partner in the T-RIZE ecosystem, supporting institutional adoption of tokenized real estate assets across global markets."},
    {"id": "7ridge",            "name": "7Ridge",            "tag": "VENTURE",        "text": "7Ridge is a venture capital firm and strategic investor in the T-RIZE ecosystem, backing the development of tokenized real-world asset infrastructure on Canton Network."},
    {"id": "trize",             "name": "T-RIZE Group",      "tag": "ISSUER",         "text": "T-RIZE Group is the issuer behind the RIZE governance token and the operator of the T-RIZE tokenization platform. Building on Canton Network, T-RIZE enables institutional-grade tokenization of real estate and real-world assets at scale."},
]


async def cmd_ecosystem(args: list[str]) -> str:
    if not args:
        lines = [
            "🌐 *T-RIZE Ecosystem*",
            "_Type `/rizeby ecosystem {name}` to learn more about any entity_",
            "",
        ]
        for e in TRIZE_ECOSYSTEM:
            lines.append(f"• *{e['name']}* — {e['tag']}")
        return "\n".join(lines)

    query = " ".join(args)
    entity = find_entity(query, TRIZE_ECOSYSTEM)
    if not entity:
        return (
            f"❓ No T-RIZE ecosystem entity found matching *{query}*.\n\n"
            "Type `/rizeby ecosystem` to see all entities."
        )

    lines = [
        f"🌐 *{entity['name']}*",
        f"_{entity['tag']}_",
        "",
        entity.get("text", "No description available."),
    ]
    return "\n".join(lines)


# ── /rizeby cantonboard ───────────────────────────────────────────────────────

CANTON_BOARD = [
    ("Madani Boukalba",  "T-RIZE Group"),
    ("Yuval Rooz",       "Digital Asset"),
    ("Jörgen Ouaknine", "7Ridge"),
    ("Chris Zuehlke",    "Cumberland SV"),
    ("Ryan Trinkle",     "IOHK / Cardano"),
    ("Kinga Bósse",      "Citi"),
    ("James Lang",       "Broadridge"),
    ("Jack Yang",        "Hang Seng Bank"),
    ("Amy Kalnoki",      "Digital Asset"),
    ("Etienne Richard",  "Canton Foundation"),
]


async def cmd_cantonboard(args: list[str]) -> str:
    lines = [
        "🏛 *Canton Foundation Board Members*",
        "",
    ]
    for name, org in CANTON_BOARD:
        lines.append(f"• *{name}* — {org}")

    lines += [
        "",
        "_The Canton Foundation oversees the strategic direction, governance framework, and ecosystem development of the Canton Network._",
    ]
    return "\n".join(lines)


# ── /rizeby vision87 / vision60 / kairos ─────────────────────────────────────

async def cmd_vision87(args: list[str]) -> str:
    return """🏢 *Vision 87 by Champfleury*
_$23M · 87 Units · Montréal · $300M Program · Texture Capital_

Vision 87 by Champfleury is an 87-unit, $23 million tokenized real estate development in Montréal, Canada. Part of Champfleury's broader $300M tokenization program, Vision 87 represents T-RIZE's flagship Canadian real estate asset.

The project is structured as a tokenized security offering via Texture Capital, enabling fractional ownership of institutional-grade Canadian real estate through the T-RIZE platform.

Key highlights:
• 87 residential units, Montréal QC
• $23M total asset value
• Part of $300M multi-asset tokenization program
• Distributed via Texture Capital
• Built on Canton Network infrastructure"""


async def cmd_vision60(args: list[str]) -> str:
    return """🏢 *Vision 60 by Champfleury*
_Tokenized Real Estate · Montréal · T-RIZE Program_

Vision 60 by Champfleury is a complementary tokenized real estate asset in the T-RIZE RWA portfolio, part of the same Montréal-based multi-asset program as Vision 87.

The project extends Champfleury's tokenization strategy, offering institutional and qualified investors fractional access to Canadian real estate through the T-RIZE and Canton Network infrastructure.

Part of the broader $300M Champfleury tokenization initiative, Vision 60 demonstrates the scalability of T-RIZE's real-world asset issuance platform."""


async def cmd_kairos(args: list[str]) -> str:
    return """⚡ *Kairos DLN*
_Digital Lending Network · RWA Credit Infrastructure_

Kairos DLN is a digital lending network integrated into the T-RIZE ecosystem, providing on-chain credit infrastructure for real-world asset-backed lending.

Building on Canton Network's privacy-preserving smart contract architecture, Kairos DLN enables institutional-grade lending against tokenized real estate and other RWA collateral — bringing DeFi-native capital efficiency to traditional asset classes.

Kairos represents T-RIZE's expansion into RWA-backed credit markets, complementing the equity tokenization work of the Vision series with debt financing capabilities."""
