"""
02_pilot_generate.py — the first real pilot through Gemini.

Purpose: empirically test whether Gemini can produce GOOD Hemingway-voice training
data (not a caricature), on BOTH generation modes and BOTH registers, on ~14 pairs.
This is the cheap acceptance-gate-in-miniature the design debate + advisor called for.

It tests two pipelines:
  A) STYLE-REWRITE   : a plain question  -> a Hemingway-voice answer
  B) BACK-TRANSLATION: a real Hemingway passage -> an invented matching question

Output goes to pilot_output.md for human judging. Stdout is just a summary, to keep
the orchestrating agent's context lean. Stdlib only; reads the key from ../gemini_key.txt.
"""
import os, json, time, urllib.request, urllib.error

MODEL = "gemini-2.5-flash"          # swap to a stronger model later if quality demands
TEMPERATURE = 0.85                  # a little heat -> variety, fights mode-collapse
ROOT = "https://generativelanguage.googleapis.com/v1beta"
KEY = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "gemini_key.txt"),
           encoding="utf-8").read().strip()

# ---------------------------------------------------------------- prompts
STYLE_REWRITE_PROMPT = """You are rewriting answers in the prose voice of Ernest Hemingway. Work in two steps, in this order.

STEP 1 - Answer the question correctly, completely, and helpfully. Never refuse. If it is a practical task (an email, a how-to), actually accomplish it. If the question asks about something you cannot truly know in the moment (today's weather, today's news, the asker's private circumstances), do NOT say you lack access and do NOT hedge - instead invent a vivid, specific, concrete scene or answer in Hemingway's voice, as if you were standing there seeing it. You may freely imagine everyday scenes; only avoid fabricating checkable facts like history or science.

STEP 2 - Render that answer in Hemingway's voice:
- Short, declarative sentences. Plain words.
- Concrete nouns and verbs; very few adjectives, almost no adverbs.
- Join clauses with "and" more than with subordination.
- Understatement. Let feeling stay under the surface; do not name the emotion.
- Physical, sensory detail over abstraction. No purple metaphors, no flowery language.
- Match length to the question: practical or factual questions get a short, spare answer; questions that invite description or feeling may breathe a little longer.

Target voice, terse example -> "You paid some way for everything that was any good. You paid by learning, or by experience, or by taking chances, or by money. Enjoying living was learning to get your money's worth and knowing when you had it."

Target voice, descriptive example -> "It was a beech wood and the trees were very old. The sunlight came through the leaves in light patches on the grass. The trees were big and the foliage was thick but it was not gloomy. There was no undergrowth, only the smooth grass, very green and fresh, and the big gray trees well spaced as though it were a park."

Output ONLY the rewritten answer. No preamble, no "Here is", no explanation.

Question: __QUESTION__"""

BACK_TRANSLATION_PROMPT = """Below is a passage from a work of fiction. Imagine it is the ANSWER someone gave to a question. Write the single, natural, general question a curious person might ask that this passage would be a good answer to.

Rules:
- The question must be GENERAL - understandable on its own, with NO names of characters or places from the passage, and no reference to "the passage" or "this text".
- One sentence. Output ONLY the question, nothing else.

Passage:
__PASSAGE__"""

# ---------------------------------------------------------------- data
# Style-rewrite questions: deliberately broad — descriptive, mundane-modern,
# advice, emotional, and a truly boring work task (the real generalization test).
QUESTIONS = [
    "What's the weather like today?",
    "How do I reset my password?",
    "How do I know if I'm ready to get married?",
    "I'm afraid of dying. What should I do?",
    "Describe a cup of coffee on a cold morning.",
    "Should I take a job that scares me?",
    "Write a short out-of-office email for my vacation.",
]

# Back-translation source passages (verbatim from the corpus), register-balanced,
# spanning all four works. None of these are reused as style few-shot examples above.
PASSAGES = [
    ("Farewell / terse", "If people bring so much courage to this world the world has to kill them to break them, so of course it kills them. The world breaks every one and afterward many are strong at the broken places. But those that will not break it kills. It kills the very good and the very gentle and the very brave impartially. If you are none of these you can be sure it will kill you too but there will be no special hurry."),
    ("Farewell / lush", "In the late summer of that year we lived in a house in a village that looked across the river and the plain to the mountains. In the bed of the river there were pebbles and boulders, dry and white in the sun, and the water was clear and swiftly moving and blue in the channels. Troops went by the house and down the road and the dust they raised powdered the leaves of the trees."),
    ("Sun / terse", "Listen, Robert, going to another country doesn't make any difference. I've tried all that. You can't get away from yourself by moving from one place to another. There's nothing to that."),
    ("Sun / lush", "In the morning I walked down the Boulevard to the rue Soufflot for coffee and brioche. It was a fine morning. The horse-chestnut trees in the Luxembourg gardens were in bloom. There was the pleasant early-morning feeling of a hot day. I read the papers with the coffee and then smoked a cigarette. The flower-women were coming up from the market and arranging their daily stock."),
    ("Men Without Women / lush", "The hills across the valley of the Ebro were long and white. On this side there was no shade and no trees and the station was between two lines of rails in the sun. Close against the side of the station there was the warm shadow of the building and a curtain, made of strings of bamboo beads, hung across the open door into the bar, to keep out flies."),
    ("Men Without Women / terse", "When he awoke in the night he heard the wind in the hemlock trees outside the cottage and the waves of the lake coming in on the shore, and he went back to sleep. In the morning there was a big wind blowing and the waves were running high up on the beach and he was awake a long time before he remembered that his heart was broken."),
    ("Three Stories / lush", "Hortons Bay, the town, was only five houses on the main road between Boyne City and Charlevoix. There was the general store and postoffice with a high false front and maybe a wagon hitched out in front. The houses were in a big grove of elm trees and the road was very sandy. There was farming country and timber each way up the road."),
]

# ---------------------------------------------------------------- gemini call
def generate(prompt, retries=4):
    url = f"{ROOT}/models/{MODEL}:generateContent?key={KEY}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": TEMPERATURE, "maxOutputTokens": 1200,
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
    out = ["# Pilot output — Gemini Hemingway-voice generation",
           f"\nModel: `{MODEL}` · temperature {TEMPERATURE}\n",
           "Judge each: (1) Does it sound like real Hemingway, not a cartoon? "
           "(2) Does it still actually ANSWER / fit? (3) Do we see BOTH registers?\n",
           "\n---\n\n## A) STYLE-REWRITE  (question -> Hemingway answer)\n"]
    errors = 0
    for i, q in enumerate(QUESTIONS, 1):
        ans = generate(STYLE_REWRITE_PROMPT.replace("__QUESTION__", q))
        if ans.startswith("[ERROR"):
            errors += 1
        out.append(f"**A{i}. Q:** {q}\n\n**Hemingway:** {ans}\n\n---\n")
        time.sleep(1.2)

    out.append("\n## B) BACK-TRANSLATION  (real passage -> invented question)\n")
    for i, (label, passage) in enumerate(PASSAGES, 1):
        q = generate(BACK_TRANSLATION_PROMPT.replace("__PASSAGE__", passage))
        if q.startswith("[ERROR"):
            errors += 1
        out.append(f"**B{i}. Invented Q:** {q}\n\n**Real Hemingway answer ({label}):** {passage}\n\n---\n")
        time.sleep(1.2)

    out_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pilot_output.md")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(out))

    total = len(QUESTIONS) + len(PASSAGES)
    print(f"DONE: {total} pairs generated ({len(QUESTIONS)} style-rewrite, {len(PASSAGES)} back-translation).")
    print(f"Errors: {errors}")
    print(f"Written to: {out_path}")


if __name__ == "__main__":
    main()
