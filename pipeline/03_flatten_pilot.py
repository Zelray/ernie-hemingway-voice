"""
03_flatten_pilot.py — micro-pilot for the FLATTEN-THEN-RESTORE data idea.

WHY THIS EXISTS (plain English):
  Our richest training asset is 212K words of REAL Hemingway, but only ~25 of
  those passages are "answer-shaped" (good for back-translation). To use the
  rest as real-voice training targets, we flip the style-rewrite direction:
    - Take a REAL Hemingway passage  -> this becomes the training ANSWER (target).
    - Ask Gemini to FLATTEN it into bland, voiceless prose -> the training INPUT.
    - Train the model on  flat -> real  (i.e. "rewrite this in Hemingway's voice").
  Every target is genuine Hemingway, never an imitation, so it cannot teach a
  caricature. It also directly teaches the paid product's "translate my blog
  into my voice" feature.

  THE ONE THING THIS TESTS: does Gemini's flatten actually STRIP the voice?
  If the flattened input still sounds like Hemingway, the pair is leaky/trivial
  and the idea fails. We look at 4 passages and judge by eye.

RUN (Bash; PowerShell hangs this environment):
  python pipeline/03_flatten_pilot.py
"""
import os, json, time, urllib.request, urllib.error

MODEL = "gemini-2.5-flash"
TEMPERATURE = 0.4   # flattening wants RELIABILITY, not creativity -> low heat
ROOT = "https://generativelanguage.googleapis.com/v1beta"
KEY = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gemini_key.txt"),
           encoding="utf-8").read().strip()

# The flatten prompt must FULLY neutralize: kill rhythm, kill word choice, keep meaning.
FLATTEN_PROMPT = """You will be given a short passage of literary prose. Rewrite it in plain, neutral, expository English that conveys the SAME literal information and meaning, but strips ALL distinctive style.

Requirements:
- Ordinary modern vocabulary. No literary or poetic word choices.
- Standard medium-to-long sentences with normal subordination (because, which, although, since). Do NOT copy the original's sentence lengths or rhythm.
- Neutral, explanatory tone — like a flat paraphrase a bored student or a textbook would write.
- Preserve the meaning and the concrete facts. Add NO new facts. Remove NO facts.
- The result must NOT sound like the original author. Erase the voice completely.

Output ONLY the rewritten plain version. No preamble, no quotes, no explanation.

Passage:
__PASSAGE__"""

# Real, verbatim Hemingway. Reflective + descriptive, short + medium — the two
# registers our 4-bucket plan relies on. These are the TARGETS.
PASSAGES = [
    ("Farewell / reflective",
     "The world breaks every one and afterward many are strong at the broken places. But those that will not break it kills. It kills the very good and the very gentle and the very brave impartially. If you are none of these you can be sure it will kill you too but there will be no special hurry."),
    ("Farewell / descriptive",
     "In the late summer of that year we lived in a house in a village that looked across the river and the plain to the mountains. In the bed of the river there were pebbles and boulders, dry and white in the sun, and the water was clear and swiftly moving and blue in the channels."),
    ("Sun / aphoristic-short",
     "It is awfully easy to be hard-boiled about everything in the daytime, but at night it is another thing."),
    ("Men Without Women / descriptive",
     "The hills across the valley of the Ebro were long and white. On this side there was no shade and no trees and the station was between two lines of rails in the sun. Close against the side of the station there was the warm shadow of the building."),
]


def generate(prompt, retries=4):
    url = f"{ROOT}/models/{MODEL}:generateContent?key={KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": 800,
                             "thinkingConfig": {"thinkingBudget": 0}},
    }).encode("utf-8")
    for attempt in range(retries):
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 503) and attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR HTTP {e.code}: {e.read().decode('utf-8')[:160]}]"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(2 ** attempt * 2)
                continue
            return f"[ERROR {type(e).__name__}: {e}]"


def main():
    out = ["# Flatten-then-restore micro-pilot",
           f"\nModel: `{MODEL}` · temperature {TEMPERATURE}\n",
           "For each: FLATTENED = the training INPUT (must sound voiceless); "
           "ORIGINAL = the training TARGET (real Hemingway). "
           "Judge: did the flatten strip the voice? Is `flattened -> original` a clean pair?\n",
           "\n---\n"]
    errors = 0
    for i, (label, original) in enumerate(PASSAGES, 1):
        flat = generate(FLATTEN_PROMPT.replace("__PASSAGE__", original))
        if flat.startswith("[ERROR"):
            errors += 1
        out.append(f"\n## {i}. {label}\n")
        out.append(f"**FLATTENED (input):** {flat}\n")
        out.append(f"**ORIGINAL (target):** {original}\n")
        out.append("\n---\n")
        time.sleep(1.2)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "flatten_pilot_output.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    print(f"DONE: {len(PASSAGES)} flatten pairs. Errors: {errors}")
    print(f"Written to: {out_path}")


if __name__ == "__main__":
    main()
