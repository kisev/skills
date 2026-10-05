# Pattern catalog

The complete editing catalog for `humanize`, mapped to the 26 categories of
[blader/humanizer](https://github.com/blader/humanizer), which draws on
Wikipedia's "Signs of AI writing". Groups A through E are numbered strongest
first. A pattern without the "weak alone" mark justifies an edit on one
sighting; the weak-alone set is 6, 7, 9, 10, 11, 12, 15, 18, 19, 20, 24, and
25, and one weak-alone sighting that does not obstruct the meaning is not
enough for an edit. The mandatory punctuation and no-invention rules apply
regardless of this classification.

Two boundaries differ from that upstream catalog and always win:

- A writing sample never overrides the punctuation rule, the no-invention
  rule, or any other mandatory constraint. Match the voice, not the defects.
- Do not add an opinion, reaction, or objection that the source or the user
  did not express.

Every pattern is a structural move that exists in every human language, so the
rules below apply to prose in any language; the worked examples are in English,
and the same move transfers by structure, not by translated word list. Do not
edit a watched phrase inside an exact quotation, a title, a proper name, or a
passage that discusses the phrase rather than uses it.

## A. Staging instead of stating

### 1. Not X but Y

Watch for: "not just X, but Y", "it's not X, it's Y", the reversed "X rather
than Y", the appended "X, not Y" tail, the same contrast split across
sentences, a clipped negative tail. State the point directly. Keep a contrast
only when the negative half corrects a belief the reader actually holds or
both halves carry information.

**Before:**

> It's not just about the beat riding under the vocals; it's part of the
> aggression and atmosphere.

**After:**

> The beat rides under the vocals and adds to the aggression and atmosphere.

**Before:**

> The patch adds retry with backoff to the webhook client, not a rewrite of
> the delivery pipeline.

**After:**

> The patch adds retry with backoff to the webhook client.

### 2. One-line closers and dramatic fragments

Watch for: a one-sentence paragraph that restates the paragraph before it,
"That is the real win.", "Let that sink in.", the same closer after several
sections, a sentence that names what an example just showed, a row of
fragments. Cut a closer that repeats; keep one that adds a fact or
consequence the example does not show.

**Before:**

> Caching cuts repeat work.
>
> That is the real win.
>
> Retries hide brief outages.
>
> That is the real win.

**After:**

> Caching cuts repeat work.
>
> Retries hide brief outages.

### 3. Sayings that sound deep

Watch for: "the real question is", "at its core", "what really matters",
"X is the Y of Z", "the language of", "the currency of", and their exact
equivalents in the working language. Replace the saying with the specific
claim it hides.

**Before:**

> The real question is whether teams can adapt. At its core, what really
> matters is organizational readiness.

**After:**

> The question is whether teams can adapt, and that depends on how ready the
> organization is.

### 4. Staged run-up before the point

Watch for: "Let's dive in", "here's what you need to know", "without further
ado", "quick note", "Honestly?", "Here's the thing". Remove the run-up, not
just its tone. "Honestly" inside a casual sentence is ordinary; the tell is
the standalone opener before a routine claim.

**Before:**

> Let's dive into how caching works in Next.js. Here's what you need to know.
> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.

**After:**

> Next.js caches data at multiple layers: request memoization, the data cache,
> and the router cache.

### 5. Arguing with no one

Watch for: "This isn't mainly about", "I'm not saying", "Some might say... but",
"A tempting approach would be", "One might be tempted to". Remove the defense;
if it holds a real claim, state the claim. Keep an objection the text
attributes or answers in full.

**Before:**

> Session tokens are rotated every 24 hours. A tempting approach would be to
> rotate them by restarting the auth service on a cron job, but that would
> drop every active session. Rotation happens in place, and clients refresh
> transparently.

**After:**

> Session tokens are rotated every 24 hours. Restarting the auth service would
> drop every active session, so rotation happens in place and clients refresh
> transparently.

## B. Rhythm by rule

### 6. Forced triads (weak alone)

Ideas arrive in threes to sound complete, whether the meaning has three parts
or not. Check that each item adds a distinct idea; merge examples or develop
the strongest one when they do not. Keep three real items when the meaning
needs three.

**Before:**

> The event features keynote sessions, panel discussions, and networking
> opportunities. Attendees can expect innovation, inspiration, and industry
> insights.

**After:**

> The event includes keynote sessions and panels. There is also time for
> networking.

### 7. Repeated sentence openings (weak alone)

Several sentences in a row start with the same subject because repetition is
handled by rule instead of by ear. Merge the sentences, change the subject, or
begin with the action. Do not ban the repeated word; writers also repeat an
opening on purpose for rhythm.

**Before:**

> She noted the door. She noted the lock on it. She filed both away.

**After:**

> She noted the door and its lock, then filed both away.

### 8. Dashes as the universal connector

The final rewrite must not contain en dashes (U+2013) or em dashes (U+2014),
including spaced dashes and double hyphens used as dashes. Replace each dash
with a period, comma, colon, or parentheses, or rewrite the sentence. Leave
dashes inside code, commands, paths, and URLs alone. One dash is weak
evidence of template writing, and a dash-free text is not evidence at all;
the mandatory punctuation rule settles the outcome regardless of clustering,
so edited prose loses every dash outside protected fragments. In Russian,
recast sentences that grammar would punctuate with a copula dash instead of
keeping the dash.

**Before:**

> The new policy — announced without warning — affects thousands of workers.

**After:**

> The new policy, announced without warning, affects thousands of workers.

### 9. Stacked qualifiers (weak alone)

Watch for: "to be fair", "could potentially", "might arguably", "in some cases
it may". Keep a qualifier only when the source supports it and the meaning
needs it. Keep scope statements, legal and safety notices, and real
corrections.

**Before:**

> It could potentially possibly be argued that the policy might have some
> effect on outcomes.

**After:**

> The policy may affect outcomes.

### 10. Hyphenated pairs everywhere (weak alone)

Keep the hyphen before a noun ("a high-quality report") and drop it after the
noun ("the report is high quality"). Words the dictionary always spells with a
hyphen keep it everywhere. In Russian, hyphenated compounds follow dictionary
spelling; do not add hyphens by analogy with English.

**Before:**

> The report is high-quality, the process is well-documented, and the plan is
> long-term.

**After:**

> The report is high quality, the process is well documented, and the plan is
> long term.

### 11. Passive voice and missing subjects (weak alone)

The text hides who acts or drops the subject. Use active voice when it makes
the actor and action clearer. Keep a passive clause that is meaningful on its
own.

**Before:**

> No configuration file is needed. The import script preserves the results
> automatically.

**After:**

> You do not need a configuration file. The import script preserves the
> results automatically.

## C. Inflation and borrowed authority

The fact underneath is usually sound. Keep it and remove the dressing.

### 12. Overused AI words (weak alone)

Watch for stock words wherever they appear: "additionally", "crucial",
"delve", "enhance", "landscape" (abstract), "pivotal", "robust" (figurative),
"showcase", "testament", "underscore", "vibrant", and each language's own
stock equivalents. The watchlist is an example, not a fixed blacklist; a
formal word outside such lists is not a tell by itself.

**Before:**

> Additionally, a pivotal feature of the culinary landscape is the
> incorporation of camel meat, showcasing enduring traditions.

**After:**

> The cuisine also includes camel meat, a long-standing tradition.

### 13. Inflated significance

Watch for: "stands as a testament", "a pivotal moment", "plays a key role",
"marking the", "evolving landscape", "the future looks bright", stock
"challenges and outlook" sections, and send-off paragraphs. Keep the fact and
drop the significance; end on the last concrete fact.

**Before:**

> The Statistical Institute of Catalonia was officially established in 1989,
> marking a pivotal moment in the evolution of regional statistics in Spain.

**After:**

> The Statistical Institute of Catalonia was established in 1989.

### 14. Vague connection or association

Watch for: "associated with", "connected to", "in connection with", "linked
to". The text says two things are connected without saying how. Name the
relationship the source gives; if the source does not say, keep the vague
wording rather than inventing a role.

**Before:**

> He is associated with the Rajhans Orchestra, which he founded and conducts.

**After:**

> He founded and conducts the Rajhans Orchestra.

### 15. Shallow participial riders (weak alone)

Watch for: "highlighting", "underscoring", "emphasizing", "reflecting",
"symbolizing", "showcasing", and the working language's adverbial participle
riders bolted onto a simple fact. Keep the fact; keep the rider only when the
source supports what it claims.

**Before:**

> The temple's color palette of blue, green, and gold resonates with the
> region's natural beauty, symbolizing Texas bluebonnets, reflecting the
> community's deep connection to the land.

**After:**

> The temple is painted blue, green, and gold, colors meant to evoke Texas
> bluebonnets.

### 16. Sales language

Watch for: "rich" (figurative), "profound", "nestled", "in the heart of",
"groundbreaking" (figurative), "renowned", "breathtaking", "stunning". The
text reads like an advertisement; state what the thing is.

**Before:**

> Nestled within the breathtaking region of Gonder in Ethiopia, Alamata Raya
> Kobo stands as a vibrant town with a rich cultural heritage.

**After:**

> Alamata Raya Kobo is a town in the Gonder region of Ethiopia.

### 17. Borrowed authority

Watch for: "experts argue", "observers have cited", "industry reports",
"some critics". Unnamed experts prop up a claim; a list of prestige outlets
props up a person. When the source names the real source and what it said,
use that; otherwise cut the unsupported claim. A missing citation alone is
not a tell.

**Before:**

> Experts believe the Haolai River plays a crucial role in the regional
> ecosystem. The 2021 basin survey recorded 40 fish species in the river.

**After:**

> The 2021 basin survey recorded 40 fish species in the Haolai River.

### 18. Avoiding is, are, and has (weak alone)

Watch for: "serves as", "stands as", "functions as", "boasts", "features".
Use "is", "are", and "has". In Russian, prefer a direct verb over a copula
dash when the dash is forbidden.

**Before:**

> Gallery 825 serves as LAAA's exhibition space for contemporary art and
> boasts over 3,000 square feet.

**After:**

> Gallery 825 is LAAA's exhibition space for contemporary art and has over
> 3,000 square feet.

## D. Formatting by rule

Templates and visual editors also produce clean formatting. The tell is
decoration on every item.

### 19. Bold as decoration (weak alone)

Words are bolded without a reason, and vertical lists give every item a bold
label and a colon. Remove the bold. Turn a labeled list into prose when the
labels carry no information of their own.

**Before:**

> It blends **OKRs (Objectives and Key Results)**, **KPIs (Key Performance
> Indicators)**, and visual strategy tools such as the **Business Model
> Canvas (BMC)**.

**After:**

> It blends OKRs (Objectives and Key Results), KPIs (Key Performance
> Indicators), and visual strategy tools such as the Business Model Canvas
> (BMC).

### 20. Decorative headings (weak alone)

Headings capitalize every main word, and headings or list items carry emojis
or arrows as decoration. A heading written for effect should name what the
section holds. Use sentence case, remove the decoration, and let the title
stand once.

**Before:**

> ## Strategic Negotiations And Global Partnerships

**After:**

> ## Strategic negotiations and global partnerships

### 21. Curly quotation marks

Curly quotes (U+201C, U+201D) and guillemets (U+00AB, U+00BB) appear where the
target format uses straight quotes. Use `"` in newly written prose; keep the
original marks inside exact quotations and source data. Most editors
auto-curl, which makes the tell common, but the mandatory punctuation rule
applies to edited prose regardless of clustering.

**Before:**

> He said “the project is on track” but others disagreed.

**After:**

> He said "the project is on track" but others disagreed.

## E. Leftovers from the chat and the draft

Categories 22 and 23 are chat and draft residue: remove the wrapper outright
and keep the content. Categories 24 and 25 are weak alone: a single sighting
that does not obstruct the meaning is not enough for an edit, and the
mandatory punctuation and no-invention rules still apply.

### 22. Chatbot residue

Watch for: "I hope this helps", "Of course!", "Great question!", "You're
absolutely right", "Would you like...?", "let me know", and their exact
equivalents in the working language. A chatbot's greeting, praise, offer, or
closing remains in text that should stand on its own. Remove the wrapper and
keep the content.

**Before:**

> Great question! Here is an overview of the French Revolution. It began in
> 1789 when a financial crisis and food shortages led to widespread unrest.
> I hope this helps! Let me know if you'd like me to expand on any section.

**After:**

> The French Revolution began in 1789 when a financial crisis and food
> shortages led to widespread unrest.

### 23. Knowledge-limit disclaimers and guesses

Watch for: "as of \[date]", "up to my last training update", "while specific
details are limited", "likely \[grew up, studied]", "it is believed that".
State what the source does not show, or remove the sentence. Never fill the
gap with a plausible guess.

**Before:**

> While specific details about the company's founding are not extensively
> documented in readily available sources, it appears to have been
> established sometime in the 1990s.

**After:**

> The company's founding date is not documented in the available sources.

### 24. A heading repeated in the first sentence (weak alone)

A heading is followed by a one-line paragraph that restates it before the real
content begins. Remove the repeated sentence.

**Before:**

> ## Performance
>
> Speed matters.
>
> When users hit a slow page, they leave.

**After:**

> ## Performance
>
> When users hit a slow page, they leave.

### 25. Writing about the document instead of its subject (weak alone)

Watch for: how the text was assembled or sourced, what it replaced, and
legends the reader can already see. Mention a previous version only in change
logs, release notes, and migration guides. Keep a caveat that changes what
the reader should do; cut the account of how you worked.

**Before:**

> This function looks up an item by key. It was added to replace the previous
> approach of iterating through all items, which caused O(n²) performance.

**After:**

> This function looks up an item by key.

## F. Writing for the wrong reader

A model writes for a reader who shares no context. A reply in a thread has a
reader who already knows the background. Act on this when you can see the
surrounding conversation, or when the text plainly is a reply.

### 26. Re-explaining what the reader knows

A short reply restates the problem, walks through the diagnosis, and lays out
the evidence before it reaches the decision. Lead with the decision and keep
only the reasoning that would change whether the reader agrees: usually one
fact they lack and any link they need to act. Show the cut only when the
conversation context is explicit, as below.

*Thread context: the reviewer asked whether the patch fixes the wrong
`pipeline_id` on child moves.*

**Before:**

> Great question! Let me walk through what happens today. When you move a
> child under a new parent, `MergeService` keeps the old `pipeline_id`, which
> is why you saw the wrong pipeline attached. This patch clears the field in
> the controller instead. So to answer your question: it works around the
> issue rather than fixing it. The real fix is to update `pipeline_id` along
> with `parent_id` in `MergeService`. I checked QA: 123 past merges, only 6
> rows wrong now, so the cleanup is small. I'd rather open a separate ticket
> than widen this PR.

**After:**

> This patch is a workaround: it clears `pipeline_id` in the controller. The
> real fix updates `pipeline_id` along with `parent_id` in `MergeService`. QA
> shows 123 past merges, 6 rows wrong now, so the cleanup is small. I'd open
> a separate ticket rather than widen this PR.

## When not to act

Each pattern describes a default choice, and a person can make any one of
them on purpose. Leave a watched phrase alone inside a quotation, a title, a
proper name, or a passage that discusses the phrase rather than uses it. One
word, one passive clause, or a genuine list is not a defect. Salutations and
sign-offs on a letter or comment predate chatbots. Several tells together are
the safeguard.

Keep the details that carry the writer's voice unless they hurt the meaning:

- A specific, unusual detail or an odd quotation.
- Mixed feelings and unresolved tension that the source actually expresses.
- Dated, era-bound references that map to a specific year and subculture.
- A first-person choice the writer can explain.
- A genuine aside, parenthetical, or self-correction from the source.
