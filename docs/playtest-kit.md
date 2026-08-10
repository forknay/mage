# Playtest kit

Masterplan tasks 8.4 and 8.6. Everything needed to run the blind playtest
prepared in advance, because the day of the test is the worst time to be
writing a feedback form.

**Nothing here is published.** The itch.io copy in §6 is a draft for a
human to review and post.

---

## 1. Who to recruit

Two strangers minimum. "Stranger" means:

- Has **never seen this game**, including screenshots
- Was **not in the room** while it was built
- Plays games, but is **not a developer** — developers debug instead of
  playing, and narrate what they think you want to hear

Do not use: teammates, anyone who has drawn a single glyph in the spikes,
or anyone who already knows the word "lattice." Their data is spent.

Recruit **before** the build is ready. Chasing testers with a finished
build is how 8.4 slips a week.

## 2. The rules for whoever is watching

The hardest and most important part.

- **Say nothing.** Not a hint, not a nudge, not "try holding right-click."
  Every word you say is data you have destroyed.
- **Do not touch the mouse.** Ever.
- **Let them be stuck.** Being stuck is the finding. Set a private
  three-minute limit before you intervene, and if you intervene, write down
  exactly what you had to say — that sentence is a missing feature.
- **Watch their hands and their face, not the screen.** You know what the
  screen says. You do not know that they hesitate before every cast.
- **Do not defend the game.** If they call something broken, ask what they
  expected instead.

## 3. Observation sheet

Print one per tester. Timestamps matter more than opinions.

```
Tester ____________  Date __________  Build __________

FIRST FIVE MINUTES
  Time to discover drawing at all           ______
  Time to first successful cast             ______
  Did they find the grimoire unprompted?    Y / N
  Did they read the teach-room prompt?      Y / N

STUCK POINTS  (time, room, what they tried, what you had to say)
  ______________________________________________________
  ______________________________________________________

PER ROOM
  Room 1 teach     entered ____  left ____  deaths ____
  Room 2 combat A  entered ____  left ____  deaths ____
  Room 3 combat B  entered ____  left ____  deaths ____
  Room 4 puzzle    entered ____  left ____  deaths ____
       solved by:  brazier / lever / gave up
  Room 5 combat C  entered ____  left ____  deaths ____
  Room 6 reward    did they notice the new pattern?  Y / N
  Room 7 arena     entered ____  left ____  deaths ____
  Room 8 exit      finished at ____

UNPROMPTED QUOTES  (write them down verbatim, they are the best data here)
  ______________________________________________________
  ______________________________________________________

DID THEY FINISH?   Y / N     Total time ______
```

## 4. The feedback form (5 questions)

Ask **after** they finish, never during. Keep it to five — a long form gets
short answers.

1. **In your own words, how do you cast a spell?**
   *Tests whether the mechanic is understood, not whether it was performed.
   A player can complete the game and still describe it wrongly.*

2. **Was there a moment you felt clever? What happened?**
   *Open-ended on purpose. If nobody names one, the game has no peak.*

3. **Was there a moment you felt cheated? What happened?**
   *"Cheated" specifically — not "frustrated." Frustration can be good
   design; feeling cheated never is.*

4. **How well did the game do what you told it to?**
   *1 (constantly misread me) – 5 (always did what I meant).*
   *This is the lattice bet in one number. Cross-check it against the
   telemetry hit rate — a gap between felt and actual accuracy is itself a
   finding.*

5. **Would you play a longer version? What would you want more of?**

## 5. Telemetry analysis

The 3.2.5 CSV is the point of the whole exercise — it turns 8.4 from
anecdote into arithmetic. Columns:
`pattern, matched_spell, draw_time_ms, edges, fumbles, power, fizzled`.

Run these, in this order:

| Question | Calculation | Threshold |
|---|---|---|
| Overall hit rate | `matched / total` | **≥ 70%** (exit criterion 2) |
| Per-pattern hit rate | group by intended pattern | any pattern < 60% is broken, not the player |
| Median draw time | `median(draw_time_ms)` for hits | compare to spike P1's number |
| Drift from P1 | in-game median vs P1 median | large gap means the 3D overlay costs more than the flat harness did |
| Fumbles per cast | `mean(fumbles)` | > 2 means snap radius is too small |
| Power distribution | histogram of `power` | clustering at the 0.4 floor means par times are too aggressive |

**If hit rate is below 70%,** apply the dials in this order — cheapest and
least destructive first:

1. Increase snap radius
2. Coarsen the lattice
3. Shorten patterns (re-run `find_pattern.js`, keep separation ≥ 2)
4. Promote the grimoire to permanent HUD hints

Change **one** thing, then re-test. Changing three at once means learning
nothing from a second playtest.

## 6. Draft itch.io page copy

*Draft for human review. Do not publish without reading it over — and set
the page to private/password-protected for an alpha.*

> ### Mage — alpha
>
> A first-person dungeon crawler where every spell is a sigil you trace by
> hand. Hold right-click, draw the pattern on the lattice, release. Draw it
> fast and clean and it hits harder.
>
> Four spells, one dungeon, one miniboss. About 15 minutes.
>
> This is an early alpha — greybox art, no music, rough edges everywhere.
> What we need to know is whether the drawing feels good. There is a
> five-question form on the way out; it genuinely helps.
>
> **Controls:** WASD move · Mouse look · Right-click hold to draw ·
> Left-click to release a charged spell · Tab for the grimoire · Esc pauses
>
> Windows and Linux. Requires no installation — unzip and run.

Include on the page: the feedback form link, a known-issues list (short and
honest), and a contact address.

## 7. Day-of checklist

- [ ] Build tested on a machine that has never had Godot installed
- [ ] Telemetry writing to a path that exists and is writable on a fresh machine
- [ ] Feedback form live and reachable
- [ ] Observation sheets printed, one per tester
- [ ] A quiet room, and their own mouse if they brought one
- [ ] Whoever is watching has read §2 and agreed to stay silent
- [ ] Someone assigned to take notes who is *not* the one watching hands
