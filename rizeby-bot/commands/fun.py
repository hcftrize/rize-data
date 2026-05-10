"""Commands: /sayhello, /insult"""
import random

GREETINGS = [
    "Hello mf, welcome in Tokerize — buy more RIZE or I'll eat it before you do 🦅",
    "Sup anon. You found the best RIZE intel bot in the known universe. You're welcome.",
    "Greetings, future multi-millionaire. RIZE is still cheap. Don't say I didn't warn you.",
    "Welcome to RizeBy — where degens come to feel smarter than they actually are. 🧠",
    "Oh look, another one. Pull up a chair, check the charts, try not to panic.",
    "RizeBy at your service. Price is down. Governance is up. Make it make sense.",
    "You have arrived. Now go bond some RIZE before you do anything else.",
    "Hello traveler. The governance protocol won't bond itself. Just saying.",
    "Welcome, fren. RIZE, bond, hold. In that order. Don't complicate it.",
    "Hey hey hey. Your favourite RIZE bot is operational. Let's get into it.",
]

INSULTS = [
    "You absolute fungible token.",
    "You're the gas fee nobody wants to pay.",
    "Sir, this is a DeFi protocol, not a therapy session.",
    "Your wallet address is more trustworthy than your opinions.",
    "You're as liquid as a locked vesting schedule.",
    "Cope harder, ser.",
    "Ngmi. But in a charming way.",
    "You'd rugged yourself in a solo game.",
    "Your alpha is older than your conviction.",
    "Even the bears think you're too bearish.",
    "You're the slippage nobody accounts for.",
    "Mate, your risk tolerance is a liability.",
    "You sold the bottom. Again.",
    "Absolute goblin-mode energy.",
    "Your bonding curve goes straight down.",
    "Paper hands spotted. Incredible.",
    "You're the rebase nobody asked for.",
    "Fren, you're an impermanent loss walking.",
    "Your portfolio looks like a rug pull chart.",
    "You're the 'dev doxxed' of people — not reassuring.",
    "Sir, put down the leverage.",
    "You bought the top and called it 'early'.",
    "You're a governance proposal that never passed.",
    "Absolute smoothbrain move.",
    "Your DD is a Discord screenshot from 2021.",
    "You're a sybil attack on common sense.",
    "Certified bagholder energy.",
    "You're the sandwich bot nobody detected.",
    "Exit liquidity? No thanks, that's your job.",
    "You're what happens when FOMO has a baby with FUD.",
    "Absolutely rekt in the politest possible way.",
    "You couldn't find alpha in a yield farm.",
    "You're the 'one more dip' guy. Every time.",
    "You'd sell a RIZE bond at 3% maturity.",
    "Your conviction expires faster than a flash loan.",
    "You're more volatile than a 100x meme coin.",
    "Did you just market buy? Ser.",
    "You're the 'just 5 more minutes' of crypto investors.",
    "Absolutely meatbrained thesis.",
    "You're the phishing link in the group chat.",
    "Your tokenomics understanding is NFT-level.",
    "Sir, that's not alpha, that's cope.",
    "You're a rug pull waiting to happen.",
    "Your DAO governance vote doesn't count.",
    "Confirmed: you bought based on vibes.",
    "You're the impermanent in impermanent loss.",
    "Even the liquidity pool wants you out.",
    "Your analysis: line go up because number go up.",
    "You're what a panic sell looks like IRL.",
    "Certified exit liquidity. Touch grass.",
]


async def cmd_sayhello(args: list[str]) -> str:
    return random.choice(GREETINGS)


async def cmd_insult(args: list[str]) -> str:
    return f"🔥 {random.choice(INSULTS)}"
