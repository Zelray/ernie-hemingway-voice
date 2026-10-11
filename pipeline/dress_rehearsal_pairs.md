# Bucket-3 dress rehearsal — flatten-restore fidelity check

Model `gemini-2.5-flash` · temperature 0.3 · 22 attempted, 12 clean, 10 flagged, 0 errors.

FLATTENED = training INPUT (must be voiceless/bureaucratic). REAL TARGET = training answer (genuine Hemingway). Gate checks: under-flatten leak, named-entity loss, number loss, first-person drift.


5-gram-Jaccard(flatten,target) distribution — min 0.000 / median 0.021 / max 0.068 (lower = more thoroughly re-worded).


---


## ✅ CLEAN — b3_the-sun-also-rises_00002755

_the-sun-also-rises · chars [2755:3263] · 5gram=0.0 edit=0.079 · person third→third_


**FLATTENED (input):** I am generally suspicious of individuals who present themselves as frank and simple, particularly when their narratives are consistent. I had a persistent doubt that Robert Cohn had actually been a middleweight boxing champion. I considered alternative explanations for his facial appearance, such as an injury from a horse, a prenatal fright experienced by his mother, or an accident during his early childhood. However, I eventually arranged for Spider Kelly to confirm the story. Spider Kelly not only recalled Cohn but also frequently pondered his subsequent whereabouts.


**REAL TARGET (answer):** I mistrust all frank and simple people, especially when their stories hold together, and I always had a suspicion that perhaps Robert Cohn had never been middleweight boxing champion, and that perhaps a horse had stepped on his face, or that maybe his mother had been frightened or seen something, or that he had, maybe, bumped into something as a young child, but I finally had somebody verify the story from Spider Kelly. Spider Kelly not only remembered Cohn. He had often wondered what had become of him.


---


## ✅ CLEAN — b3_the-sun-also-rises_00129947

_the-sun-also-rises · chars [129947:130321] · 5gram=0.027 edit=0.056 · person third→third_


**FLATTENED (input):** Robert Cohn attempted to communicate that he did not desire any of the second meat course. However, we declined to translate his request, which resulted in the waitress bringing him a different item, specifically a plate of cold meats, as a substitute. I believe this is what it was. Cohn had exhibited a degree of nervousness since our meeting in Bayonne. This was because he was uncertain if we were aware that Brett had been with him in San Sebastian, and this uncertainty caused him to feel somewhat uncomfortable.


**REAL TARGET (answer):** Robert Cohn tried to say he did not want any of the second meat course, but we would not interpret for him, and so the waitress brought him something else as a replacement, a plate of cold meats, I think. Cohn had been rather nervous ever since we had met at Bayonne. He did not know whether we knew Brett had been with him at San Sebastian, and it made him rather awkward.


---


## 🚩 FLAGGED — b3_the-sun-also-rises_00213867

_the-sun-also-rises · chars [213867:214249] · 5gram=0.0 edit=0.065 · person first→first_

- 🚩 NAMED-ENTITY LOST: ['turgenieff']

- 🚩 NAMED-ENTITY ADDED (possible hallucination): ['turgenev']

- 🚩 NUMBER ADDED/CHANGED: ['one']

- (diag) second-person target=True vs flatten=False (soft: generic 'you'->'one' is OK)


**FLATTENED (input):** I reactivated the light source and began to read. The text I read was by Turgenev. I understood that because I was reading it in a highly sensitive mental state, which was a result of consuming an excessive amount of brandy, I would later recall this experience. Subsequently, it would feel as if the events described in the text had actually occurred to me. This memory would be a permanent possession. This was another positive outcome that one acquired after an initial cost. I eventually fell asleep sometime as daylight approached.


**REAL TARGET (answer):** I turned on the light again and read. I read the Turgenieff. I knew that now, reading it in the oversensitized state of my mind after much too much brandy, I would remember it somewhere, and afterward it would seem as though it had really happened to me. I would always have it. That was another good thing you paid for and then had. Some time along toward daylight I went to sleep.


---


## 🚩 FLAGGED — b3_the-sun-also-rises_00304114

_the-sun-also-rises · chars [304114:304341] · 5gram=0.024 edit=0.025 · person third→third_

- 🚩 NUMBER LOST: ['first']


**FLATTENED (input):** I had not seen her behaving in her previous happy and carefree manner since the time before she left with Cohn. We had returned to the area in front of the hotel. All of the tables were now prepared, and multiple tables already had people eating at them.


**REAL TARGET (answer):** It was the first time I had seen her in the old happy, careless way since before she went off with Cohn. We were back again in front of the hotel. All the tables were set now, and already several were filled with people eating.


---


## ✅ CLEAN — b3_the-sun-also-rises_00364326

_the-sun-also-rises · chars [364326:364941] · 5gram=0.048 edit=0.178 · person first→first_


**FLATTENED (input):** We exited the first-floor dining room and went out to the street. A waiter then went to get a taxi for us. The weather was hot and bright. Further up the street, there was a small square that contained trees, grass, and parked taxis. A taxi approached us from up the street, with the waiter leaning out from its side. I gave the waiter a tip and instructed the driver on our destination, then I entered the taxi and sat next to Brett. The driver began to move the taxi up the street. I leaned back into my seat. Brett then moved closer to me, and we sat pressed against each other. I put my arm around her, and she leaned against me in a comfortable position. The weather remained very hot and bright, and the houses appeared distinctly white. We then turned onto the Gran Via.


**REAL TARGET (answer):** Down-stairs we came out through the first-floor dining-room to the street. A waiter went for a taxi. It was hot and bright. Up the street was a little square with trees and grass where there were taxis parked. A taxi came up the street, the waiter hanging out at the side. I tipped him and told the driver where to drive, and got in beside Brett. The driver started up the street. I settled back. Brett moved close to me. We sat close against each other. I put my arm around her and she rested against me comfortably. It was very hot and bright, and the houses looked sharply white. We turned out onto the Gran Via.


---


## 🚩 FLAGGED — b3_farewell-to-arms_00001007

_farewell-to-arms · chars [1007:1657] · 5gram=0.029 edit=0.069 · person first→first_

- 🚩 NUMBER ADDED/CHANGED: ['one']


**FLATTENED (input):** During the late summer of that year, we resided in a house located in a village. From this village, one could see across a river and a plain, towards some mountains. The riverbed contained pebbles and boulders, which appeared dry and white due to the sun. The water in the river's channels was clear, moved quickly, and was blue. Military troops passed by our house and proceeded down the road. The dust generated by their movement coated the leaves of the trees. The tree trunks were also dusty. That year, the leaves began to fall earlier than usual. We observed the troops marching along the road, the dust ascending, and leaves, moved by the breeze, descending. After the soldiers had passed, the road was bare and white, with the exception of the fallen leaves.


**REAL TARGET (answer):** In the late summer of that year we lived in a house in a village that looked across the river and the plain to the mountains. In the bed of the river there were pebbles and boulders, dry and white in the sun, and the water was clear and swiftly moving and blue in the channels. Troops went by the house and down the road and the dust they raised powdered the leaves of the trees. The trunks of the trees too were dusty and the leaves fell early that year and we saw the troops marching along the road and the dust rising and leaves, stirred by the breeze, falling and the soldiers marching and afterward the road bare and white except for the leaves.


---


## ✅ CLEAN — b3_farewell-to-arms_00121058

_farewell-to-arms · chars [121058:121289] · 5gram=0.037 edit=0.085 · person first→first_


**FLATTENED (input):** As we conversed, she removed my clothing. After I was undressed, with the exception of the bandages, she proceeded to wash me. This washing was performed very gently and smoothly, and it felt very pleasant. Although there was a bandage on my head, she washed the areas around its edges.


**REAL TARGET (answer):** While we were talking she was undressing me, and when I was undressed, except for the bandages, she washed me, very gently and smoothly. The washing felt very good. There was a bandage on my head but she washed all around the edge.


---


## 🚩 FLAGGED — b3_farewell-to-arms_00268592

_farewell-to-arms · chars [268592:269003] · 5gram=0.026 edit=0.144 · person first→first_

- 🚩 NAMED-ENTITY LOST: ['rinaldi’s']

- 🚩 NAMED-ENTITY ADDED (possible hallucination): ["rinaldi's"]


**FLATTENED (input):** I exited the dining room, proceeded through the hall, and ascended the marble stairs to the room I had shared with Rinaldi. Outside, rain was falling. I approached the window and observed the exterior. As darkness was approaching, I saw three cars positioned in a line beneath the trees. The trees were dripping water due to the rain. The temperature was low, and drops of water were clinging to the branches. I returned to Rinaldi's bed, lay down, and subsequently fell asleep.


**REAL TARGET (answer):** I went out then through the dining-room and the hall and up the marble stairs to the room where I had lived with Rinaldi. It was raining outside. I went to the window and looked out. It was getting dark and I saw the three cars standing in line under the trees. The trees were dripping in the rain. It was cold and the drops hung to the branches. I went back to Rinaldi’s bed and lay down and let sleep take me.


---


## 🚩 FLAGGED — b3_farewell-to-arms_00365764

_farewell-to-arms · chars [365764:365992] · 5gram=0.0 edit=0.031 · person first→first_

- 🚩 NUMBER LOST: ['five', 'quarter']

- 🚩 NUMBER ADDED/CHANGED: ['4', '45']


**FLATTENED (input):** At 4:45, I said goodbye to Catherine by kissing her, and then I entered the bathroom to get dressed. While I was tying my tie and observing my reflection in the mirror, I perceived my appearance in the civilian clothes as unfamiliar. I needed to acquire additional shirts and socks.


**REAL TARGET (answer):** At a quarter to five I kissed Catherine good-by and went into the bathroom to dress. Knotting my tie and looking in the glass I looked strange to myself in the civilian clothes. I must remember to buy some more shirts and socks.


---


## ✅ CLEAN — b3_farewell-to-arms_00469433

_farewell-to-arms · chars [469433:469653] · 5gram=0.035 edit=0.061 · person first→first_


**FLATTENED (input):** After I had removed them, closed the door, and turned off the light, the situation did not improve. It felt comparable to saying good-bye to an inanimate object. Subsequently, I exited the hospital and proceeded to walk back to the hotel, during which time it was raining.


**REAL TARGET (answer):** But after I had got them out and shut the door and turned off the light it wasn’t any good. It was like saying good-by to a statue. After a while I went out and left the hospital and walked back to the hotel in the rain.


---


## 🚩 FLAGGED — b3_in-our-time_00001425

_in-our-time · chars [1425:2063] · 5gram=0.015 edit=0.069 · person third→third_

- 🚩 NUMBER LOST: ['last']

- 🚩 NUMBER ADDED/CHANGED: ['fifth', 'third']

- (diag) second-person target=True vs flatten=False (soft: generic 'you'->'one' is OK)


**FLATTENED (input):** The first matador was gored in his sword hand, and the crowd booed him, causing him to leave. The second matador lost his footing, and the bull gored him in the abdomen. He held onto the bull's horn with one hand and pressed his other hand against the wound. The bull then forcefully pushed him against the wall, dislodging the horn. He fell into the sand, but then rose as if intoxicated and attempted to hit the men who were carrying him away, demanding his sword before he lost consciousness. The third matador, a young man, subsequently entered the arena and was required to kill five bulls because regulations permit a maximum of three matadors. By the time he faced the fifth bull, he was so fatigued that he was unable to insert the sword; he could barely lift his arm.


**REAL TARGET (answer):** The first matador got the horn through his sword hand and the crowd hooted him out. The second matador slipped and the bull caught him through the belly and he hung on to the horn with one hand and held the other tight against the place, and the bull rammed him wham against the wall and the horn came out, and he lay in the sand, and then got up like crazy drunk and tried to slug the men carrying him away and yelled for his sword but he fainted. The kid came out and had to kill five bulls because you can’t have more than three matadors, and the last bull he was so tired he couldn’t get the sword in. He couldn’t hardly lift his arm.


---


## 🚩 FLAGGED — b3_in-our-time_00009483

_in-our-time · chars [9483:10239] · 5gram=0.057 edit=0.059 · person third→third_

- 🚩 NAMED-ENTITY LOST: ['italians']

- 🚩 NAMED-ENTITY ADDED (possible hallucination): ['italian', 'united']


**FLATTENED (input):** He traveled to America by boat, departing from Genoa. Ag returned to Torre di Mosta with the intention of opening a hospital. The town was characterized by loneliness and rain, and a battalion of arditi was stationed there. During the winter, while living in the muddy, rainy town, the major of the battalion initiated a romantic relationship with Ag. She had not previously been involved with Italian men. Eventually, she sent a letter to the United States, stating that their relationship had been merely a "boy and girl affair." She expressed regret and acknowledged that he would likely not comprehend her decision, but hoped he might eventually forgive her and be grateful to her. She also stated that she anticipated, quite unexpectedly, getting married in the spring. She affirmed that she loved him as always, but now understood it was only a "boy and girl love." She expressed hope for his successful career and maintained absolute belief in him.


**REAL TARGET (answer):** He went to America on a boat from Genoa. Ag went back to Torre di Mosta to open a hospital. It was lonely and rainy there, and there was a battalion of arditi quartered in the town. Living in the muddy, rainy town in the winter the major of the battalion made love to Ag, and she had never known Italians before, and finally wrote a letter to the States that theirs had been only a boy and girl affair. She was sorry, and she knew he would probably not be able to understand, but might some day forgive her, and be grateful to her, and she expected, absolutely unexpectedly, to be married in the spring. She loved him as always, but she realized now it was only a boy and girl love. She hoped he would have a great career, and believed in him absolutely.


---


## 🚩 FLAGGED — b3_in-our-time_00014263

_in-our-time · chars [14263:14844] · 5gram=0.014 edit=0.032 · person third→third_

- 🚩 NUMBER LOST: ['one']

- 🚩 NUMBER ADDED/CHANGED: ['single']


**FLATTENED (input):** When Villalta began the killing process, it occurred very quickly. The bull was positioned directly in front of him, appearing hostile. Villalta removed the sword from theleta's folds and simultaneously aimed it. He then called to the bull, saying "Toro! Toro!" The bull charged, and Villalta also charged, resulting in a brief moment where they converged. Villalta and the bull became a single entity, and then the event concluded. Villalta remained standing upright, and the red hilt of the sword was protruding without shine from between the bull's shoulders. Villalta raised his hand towards the spectators as the bull made a sound like roaring, bleeding, and looking directly at Villalta before its legs collapsed.


**REAL TARGET (answer):** When he started to kill it was all in the same rush. The bull looking at him straight in front, hating. He drew out the sword from the folds of the muleta and sighted with the same movement and called to the bull, Toro! Toro! and the bull charged and Villalta charged and just for a moment they became one. Villalta became one with the bull and then it was over. Villalta standing straight and the red kilt of the sword sticking out dully between the bull’s shoulders. Villalta, his hand up at the crowd and the bull roaring blood, looking straight at Villalta and his legs caving.


---


## ✅ CLEAN — b3_in-our-time_00018637

_in-our-time · chars [18637:18957] · 5gram=0.068 edit=0.299 · person third→third_


**FLATTENED (input):** After everyone else had moved back onto the scaffolding located behind the drop, which was a heavy structure made of oak and steel that moved on ball bearings, Sam Cardinella remained in his seat, tightly strapped in. The younger of the two priests was kneeling next to the chair. The priest then quickly moved back onto the scaffolding just before the drop descended.


**REAL TARGET (answer):** When they all stepped back on the scaffolding back of the drop, which was very heavy, built of oak and steel and swung on ball bearings, Sam Cardinella was left sitting there strapped tight, the younger of the two priests kneeling beside the chair. The priest skipped back onto the scaffolding just before the drop fell.


---


## ✅ CLEAN — b3_men-without-women_00047369

_men-without-women · chars [47369:47842] · 5gram=0.006 edit=0.09 · person third→third_


**FLATTENED (input):** He conceptualized situations using bullfighting terminology. Occasionally, he would have an idea but be unable to recall the specific slang term needed to articulate it, which prevented him from fully comprehending the thought. His instincts and existing knowledge functioned automatically, while his brain processed information at a slower pace and through verbalization. He possessed comprehensive knowledge regarding bulls and did not need to consciously deliberate about them; instead, he consistently executed the correct actions. His vision registered details, and his body executed the required movements without conscious thought. If he were to engage in conscious thought about these actions, he believed he would fail.


**REAL TARGET (answer):** He thought in bull-fight terms. Sometimes he had a thought and the particular piece of slang would not come into his mind and he could not realize the thought. His instincts and his knowledge worked automatically, and his brain worked slowly and in words. He knew all about bulls. He did not have to think about them. He just did the right thing. His eyes noted things and his body performed the necessary measures without thought. If he thought about it, he would be gone.


---


## ✅ CLEAN — b3_men-without-women_00106404

_men-without-women · chars [106404:106922] · 5gram=0.055 edit=0.169 · person third→third_


**FLATTENED (input):** The pasta asciuta was satisfactory. The wine had an alum taste, so we diluted it with water. Following this, the waiter served beefsteak and fried potatoes. At the opposite end of the restaurant, a man and a woman were seated. The man appeared to be middle-aged, and the woman was young and dressed in black. Throughout the meal, she repeatedly exhaled, causing her breath to become visible in the cold, damp air. The man observed this action and shook his head. They consumed their meal in silence, and the man held her hand beneath the table. The woman was attractive, and both individuals appeared to be very sad. They had a travelling-bag with them.


**REAL TARGET (answer):** The pasta asciuta was good; the wine tasted of alum, and we poured water in it. Afterward the waiter brought beefsteak and fried potatoes. A man and a woman sat at the far end of the restaurant. He was middle-aged and she was young and wore black. All during the meal she would blow out her breath in the cold damp air. The man would look at it and shake his head. They ate without talking and the man held her hand under the table. She was good-looking and they seemed very sad. They had a travelling-bag with them.


---


## ✅ CLEAN — b3_men-without-women_00163302

_men-without-women · chars [163302:163750] · 5gram=0.041 edit=0.014 · person third→third_


**FLATTENED (input):** The wagon traveled down the long hill, and its movement was uneven. Upon arrival at the farmhouse, all occupants exited the wagon. Mrs. Garner unlocked the door, entered the house, and then reappeared holding a lamp. Carl and Nick removed items from the rear of the wagon. Frank remained on the front seat of the wagon to drive it to the barn and stable the horses. Nick ascended the steps and opened the kitchen door. Inside, Mrs. Garner was preparing to start a fire in the stove; she turned away from the act of pouring kerosene onto the wood.


**REAL TARGET (answer):** They trotted down the long hill, the wagon jolting. At the farmhouse everybody got down. Mrs. Garner unlocked the door, went inside, and came out with a lamp in her hand. Carl and Nick unloaded the things from the back of the wagon. Frank sat on the front seat to drive to the barn and put up the horses. Nick went up the steps and opened the kitchen door. Mrs. Garner was building a fire in the stove. She turned from pouring kerosene on the wood.


---


## ✅ CLEAN — b3_men-without-women_00221854

_men-without-women · chars [221854:222160] · 5gram=0.018 edit=0.073 · person third→third_


**FLATTENED (input):** Several months later, he visited me at the hospital in Milan. He expressed significant disappointment that I had not yet married. I am aware that he would be very upset if he knew that I have not married to date. He was preparing to return to America, and he held a strong conviction that marriage would resolve all issues.


**REAL TARGET (answer):** He came to the hospital in Milan to see me several months after and was very disappointed that I had not yet married, and I know he would feel very badly if he knew that, so far, I have never married. He was going back to America and he was very certain about marriage and knew it would fix up everything.


---


## ✅ CLEAN — b3_three-short-stories-and-ten-poems_00001391

_three-short-stories-and-ten-poems · chars [1391:1964] · 5gram=0.008 edit=0.015 · person third→third_


**FLATTENED (input):** Liz had a strong positive regard for Jim. She appreciated his manner of walking from the shop, and she frequently positioned herself at the kitchen door to observe him beginning his walk down the road. She also found his mustache appealing. Furthermore, she liked the whiteness of his teeth when he smiled. A significant aspect of her liking for him was that he did not resemble a blacksmith. She also valued the fact that A. J. Smith and Mrs. Smith held Jim in high esteem. On one occasion, she noticed and appreciated the black color of the hair on his arms, as well as the whiteness of his skin above the tan line when he used the washbasin located outside the house. This particular observation caused her to experience an unusual sensation.


**REAL TARGET (answer):** Liz liked Jim very much. She liked it the way he walked over from the shop and often went to the kitchen door to watch for him to start down the road. She liked it about his mustache. She liked it about how white his teeth were when he smiled. She liked it very much that he didn’t look like a blacksmith. She liked it how much A. J. Smith and Mrs. Smith liked Jim. One day she found that she liked it the way the hair was black on his arms and how white they were above the tanned line when he washed up in the washbasin outside the house. Liking that made her feel funny.


---


## ✅ CLEAN — b3_three-short-stories-and-ten-poems_00032881

_three-short-stories-and-ten-poems · chars [32881:33473] · 5gram=0.018 edit=0.092 · person third→third_


**FLATTENED (input):** If a jockey is employed by someone, they cannot consume alcohol excessively because their trainer monitors them if they are young. If they are not young, they monitor themselves. Therefore, when a jockey is not working, they typically spend time at the Café de Paris with their associates. They can remain there for approximately two or three hours, consuming a drink such as vermouth and seltzer, while engaging in conversation, sharing anecdotes, and playing pool. This environment resembles a club or the Galleria in Milan. However, it is not precisely like the Galleria because in the Galleria, people are constantly moving past, and there are many individuals seated at the tables.


**REAL TARGET (answer):** If a jock’s riding for somebody too he can’t go boozing around because the trainer always has an eye on him if he’s a kid and if he aint a kid he’s always got an eye on himself. So mostly if a jock aint working he sits around the Café de Paris with the gang and they can all sit around about two or three hours in front of some drink like a vermouth and seltz and they talk and tell stories and shoot pool and it’s sort of like a club or the Galleria in Milan. Only it aint really like the Galleria because there everybody is going by all the time and there’s everybody around at the tables.


---


## 🚩 FLAGGED — b3_three-short-stories-and-ten-poems_00041160

_three-short-stories-and-ten-poems · chars [41160:41757] · 5gram=0.008 edit=0.027 · person third→first_

- 🚩 NAMED-ENTITY LOST: ['i’d']

- (diag) second-person target=True vs flatten=False (soft: generic 'you'->'one' is OK)


**FLATTENED (input):** After that race, my father had a substantial amount of money, which resulted in him visiting Paris more frequently. If races were held at Tremblay, he would arrange for people to drop him off in Paris as they returned to Maisons. My father and I would then sit outside the Café de la Paix and observe the people passing by. This activity was enjoyable. Many people would walk past, and various individuals would approach us, attempting to sell items. I particularly enjoyed sitting there with my father. These occasions were when we had the most enjoyment. For example, men would come by selling novelty rabbits that would jump when a bulb was squeezed, and they would approach us, at which point my father would joke with them.


**REAL TARGET (answer):** My old man had a big lot of money after that race and he took to coming into Paris oftener. If they raced at Tremblay he’d have them drop him in town on their way back to Maisons and he and I’d sit out in front of the Café de la Paix and watch the people go by. It’s funny sitting there. There’s streams of people going by and all sorts of guys come up and want to sell you things and I loved to sit there with my old man. That was when we’d have the most fun. Guys would come by selling funny rabbits that jumped if you squeezed a bulb and they’d come up to us and my old man would kid with them.


---


## 🚩 FLAGGED — b3_three-short-stories-and-ten-poems_00049906

_three-short-stories-and-ten-poems · chars [49906:50450] · 5gram=0.0 edit=0.067 · person third→first_

- 🚩 NAMED-ENTITY ADDED (possible hallucination): ["gillford's"]


**FLATTENED (input):** When my father was brought in, he was already deceased. A doctor was using a stethoscope to listen to his heart. At that time, I heard a gunshot from further up the track, which indicated that Gillford had been killed. After the stretcher carrying my father was brought into the hospital room, I lay down next to him and held onto the stretcher. I cried extensively because he appeared very pale, lifeless, and profoundly dead. I had a feeling that if my father was dead, then it might not have been necessary to shoot Gillford. It was possible that Gillford's hoof could have healed. I am uncertain about this. I had a deep affection for my father.


**REAL TARGET (answer):** My old man was dead when they brought him in and while a doctor was listening to his heart with a thing plugged in his ears I heard a shot up the track that meant they’d killed Gillford. I lay down beside my old man when they carried the stretcher into the hospital room and hung onto the stretcher and cried and cried and he looked so white and gone and so awfully dead and I couldn’t help feeling that if my old man was dead maybe they didn’t need to have shot Gillford. His hoof might have got well. I don’t know. I loved my old man so much.


---


## Skipped (skeptic-flagged, NOT attempted)

- **b3_three-short-stories-and-ten-poems_00021369** — HARD FAIL - pure unmarked DIALOGUE/monologue, zero narration (imperatives). Training the model to 'restore' an article into spoken dialogue is the caricature failure.

- **b3_men-without-women_00002112** — FLAG - all-caps drop-cap artifact ('MANUEL GARCIA') would teach the model to SHOUT names; also proper-noun-dense (pn=9.3%).

- **b3_in-our-time_00005830** — BORDERLINE FLAG - hands ~half the span to a repetitive embedded prayer/monologue; a flattened article would never produce 'please please please christ'.
