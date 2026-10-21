# The task
I would like to add a new set of controls. One of my testers asked this:

```Hello! Big fan of the game over here! You all have no idea how exciting this is for me, I've been dreaming for a port like this for YEARS now

Though I have a couple of requests, and I can teach how to play the game a bit more if this helps to anyone interested (I participated in EVO Japan Tournaments for this game if it helps promote anything haha)

The control layout is a bit weird in my sincere opinion, my usual layout on gamepads could be:
A = Main
B = Sub
X = Barrage
Y = Action (Sequels use one more macro, so can be used as Act button here)
L = Overdrive
R = Action

You all are going to press the Action button a lot since it's the way you dash and cancel out of stuff. I also recommend very sincerely to use the "OLD" Dash Type, no one uses New for how clunky it felt, they ended up even ditching it for the sequel

THOUGH, I have a very, very sincere request if it's possible.

Would it be possible to have a GDI to use with Arcade Sticks? Using the actual game layout
X = Main
Y = Sub
Z (L?) = Barrage
A = Action
B = none
C (R?) = OverDrive

Since I would like to use it with my dreamcast that has 2 Sticks permanently attached.

This was my biggest issue with the Atomiswave titles that were ported, could never use proper Arcade Sticks with them.

I don't have any CDs to burn atm, but I will immediately have some feedback as soon as I get it, would like to make comparisons of slowdown, framerate and such to the Naomi version I own.

Sincere cheers to everyone, this made my morning so happy
```

# Round 2 (2026-10-15) — B.O.S.S. macro + a reference 360 layout

Same tester, relayed by the operator. Verbatim:

```I might bring some ideas based on players that use pad, that's my personal layout, but there is a player I highly regard that uses a Virtual-On Inspired layout on the 360 port```

(attached `Senkoro-Rev-X-Till-Gamepad.png` — a Twitch stream screenshot of
the Xbox 360 *Senko no Ronde Rev.X* "Controller Setting" screen, two players'
configs side by side; kept out of git, transcribed below)

```Though this layout seems to be better at 4 triggers, but you get the idea, we can work something from here```

```I also wanted to ask if it's possible to have a "macro" for that Boss (Main+Sub+Action) because on pads it might seem a bit wonky to do so otherwise?```

Transcription of the screenshot's LEFT config (the "Virtual-On inspired" one
— Main/Sub on the analog triggers like Virtual-On's left/right weapon
triggers): LT MAIN, RT SUB, LB OverDrive, RB B.O.S.S., Y BARRAGE, X BARRAGE,
B DASH, A BARRIER; Sensitivity Low, Vibration Off. RIGHT config (the other
player): LT B.O.S.S., RT BARRIER, LB OverDrive, RB NO USE, Y SUB, X BARRAGE,
B DASH, A MAIN; Sensitivity Medium.

Two things in it cannot transfer, both limits of the Naomi ROM rather than
the port: Rev.X splits Dash and Barrier into two assignable functions, but
the measured senkosp JVS word has a single Action bit (`docs/kb/input-map.md`
§Input map), so both are Action here; and the DC pad has six inputs (A B X Y
L R) for Rev.X's eight slots, so the doubled Barrage goes. What DOES transfer
is the one concrete ask — a single-button B.O.S.S. — and the fact that the
360 port treats B.O.S.S. as an ordinary assignable function.

Outcome: no concrete DC placement was proposed by anyone, so instead of
guessing a preset the menu gained a per-port CUSTOM layout with B.O.S.S. as a
selectable function (`docs/kb/input-map.md` §Custom pad layout). The tester's
eventual layout can be baked as a preset.
