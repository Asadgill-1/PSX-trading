"""Deterministic mock agent replies — pipeline runs end-to-end with no API key.

Realistic shape, deterministic content (seeded by symbol) so demos and tests
are reproducible. Swap to real calls by setting ANTHROPIC_API_KEY.
"""
import hashlib
import json
import re


def _pick(symbol: str, options: list) -> object:
    h = int(hashlib.sha256(symbol.encode()).hexdigest(), 16)
    return options[h % len(options)]


def respond(role: str, user_prompt: str) -> dict | list:
    symbols = re.findall(r'"symbol":\s*"([A-Z0-9]+)"', user_prompt)
    if role == "scout":
        picks = symbols[:2] if symbols else []
        return [{
            "symbol": s,
            "action": "buy",
            "strategy": _pick(s, ["volume-momentum", "value-pe", "sector-follow"]),
            "thesis": f"[MOCK] {s} is trading with unusually high activity today, which often "
                      "means big investors are building a position. The price is holding firm "
                      "while the volume (number of shares changing hands) is well above normal.",
            "evidence": [f"[MOCK] {s} volume above its recent average",
                         f"[MOCK] {s} price stable near the day's high"],
        } for s in picks]
    if role == "devil":
        s = symbols[0] if symbols else "THIS"
        return {
            "objections": [
                f"[MOCK] High volume in {s} can also mean big investors are SELLING to small ones.",
                "[MOCK] One strong day proves nothing about next week.",
                f"[MOCK] If buyers vanish, {s} could be hard to exit quickly without accepting a lower price.",
            ],
            "strongest": f"[MOCK] High volume in {s} cuts both ways — it may be smart money leaving, not arriving.",
            "fatal": False,
        }
    if role == "judge":
        s = symbols[0] if symbols else "THIS"
        conviction = _pick(s, [6.5, 7.0, 5.0, 6.0])
        verdict = "propose" if conviction >= 6 else "drop"
        return {
            "verdict": verdict,
            "conviction": conviction,
            "what_company_does": f"[MOCK] {s} is a company listed on the Pakistan Stock Exchange.",
            "why_now": f"[MOCK] Trading activity in {s} is unusually strong today and the price is "
                       "holding up, which historically often continues for a few days.",
            "strongest_objection": "[MOCK] The same heavy trading could be big investors quietly exiting.",
            "worst_case": "[MOCK] The price drops and the automatic stop-loss sells the position "
                          "at about a 5% loss.",
            "report": f"[MOCK PROPOSAL] {s}: buying interest looks genuine based on today's volume "
                      "and steady price. The Devil's Advocate warns the volume could be sellers, "
                      "not buyers — a fair point. On balance the odds look slightly favourable. "
                      "If it goes wrong, the stop-loss caps the damage at roughly 5% of the amount invested.",
        }
    raise ValueError(f"unknown mock role {role}")


# self-check: python -m app.agents.mock
if __name__ == "__main__":
    scout = respond("scout", json.dumps([{"symbol": "LUCK"}, {"symbol": "ENGRO"}]))
    assert isinstance(scout, list) and scout[0]["symbol"] == "LUCK"
    devil = respond("devil", '{"symbol": "LUCK"}')
    assert devil["strongest"]
    judge = respond("judge", '{"symbol": "LUCK"}')
    assert judge["verdict"] in ("propose", "drop") and (judge["conviction"] >= 6) == (judge["verdict"] == "propose")
    print("mock self-check OK")
