from game.scene import Check, Scene

scenes: dict[str, Scene] = {
    "tavern_entrance": Scene(
        description=(
            "You push open the heavy oak door of The Rusty Flagon. Smoke and the smell "
            "of ale hit you at once. A few patrons glance your way before returning to "
            "their drinks. Behind the bar stands a stout woman who moves with practiced "
            "efficiency. In the far corner, a hooded figure sits alone, untouched drink "
            "in front of them."
        ),
        options={
            "approach the bar": "barkeep_chat",
            "sit at a table": "table_sit",
            "approach the hooded figure": "figure_approach",
            "leave": "tavern_leave_early",
        }
    ),
    "barkeep_chat": Scene(
        description=(
            "The barkeep slides a mug across the counter before you even sit down. "
            "'Name's Hilda. You look like you've been on the road.' She lowers her "
            "voice. 'There's coin to be made if you're the type. Old tomb opened up "
            "north of town. Mayor's paying fifty gold to whoever clears it out. "
            "Undead walking, strange lights — the usual sort of trouble.'"
        ),
        options={
            "ask about the tomb": "tomb_info",
            "ask about the hooded figure": "figure_info",
            "order another drink and call it a night": "rest_ending",
        }
    ),
    "tomb_info": Scene(
        description=(
            "Hilda wipes down the bar. 'Belonged to some war-priest, century back. "
            "Sealed the place himself before he died. Nobody knows why it opened now.' "
            "She slides a rough hand-drawn map across the counter. 'North road, half a "
            "mile past the mill. You can't miss the smell.' She taps the map. "
            "'Fifty gold on completion. Don't go in drunk.'"
        ),
        options={
            "take the quest and head out": "tomb_entrance",
            "ask about the hooded figure first": "figure_info",
            "decline and get some rest": "rest_ending",
        }
    ),
    "figure_info": Scene(
        description=(
            "Hilda's expression doesn't change, but her eyes flick toward the corner. "
            "'Three nights now. Orders water, tips in silver, says nothing. Whatever "
            "they're waiting for, I haven't figured it out.' She refills your mug "
            "without asking. 'Go say hello if you're curious. Worst they do is ignore you.'"
        ),
        options={
            "approach the hooded figure": "figure_approach",
            "head to the tomb instead": "tomb_entrance",
            "get some rest": "rest_ending",
        }
    ),
    "table_sit": Scene(
        description=(
            "You find a corner table and order stew. It's cheap and filling. From here "
            "you can watch the whole room — Hilda behind the bar working steadily, a "
            "pair of merchants arguing quietly near the fire, and the hooded figure in "
            "the far corner who hasn't moved since you walked in."
        ),
        options={
            "go speak to the barkeep": "barkeep_chat",
            "approach the hooded figure": "figure_approach",
            "just rest here for the night": "rest_ending",
        }
    ),
    "figure_approach": Scene(
        description=(
            "You push back from your seat and start across the room toward the hooded "
            "figure. The old floorboards shift under your feet..."
        ),
        options={},
        check=Check(
            stat="dexterity",
            dc=10,
            success_scene="figure_success",
            fail_scene="figure_fail",
            description="Move quietly across the room — DEX check, DC 10",
        )
    ),
    "figure_success": Scene(
        description=(
            "You reach the table without a sound. The figure lowers their hood to reveal "
            "a weathered face and silver eyes — the kind of stillness that comes from long "
            "practice. 'I've been waiting for someone with your particular discretion,' "
            "they say quietly. 'There's something in that tomb that cannot fall into the "
            "wrong hands. Find it. Bring it to me. I will make it worth your time.'"
        ),
        options={
            "agree to help": "tomb_entrance",
            "ask what it is": "figure_demand",
            "decline and go to the bar": "barkeep_chat",
        }
    ),
    "figure_fail": Scene(
        description=(
            "A floorboard explodes under your foot with a sound like a pistol shot. "
            "Every head in the tavern swings your way. The hooded figure glances up, "
            "utterly unsurprised. 'Sit down,' they say, with the faintest trace of "
            "amusement. 'You'll do anyway.'"
        ),
        options={
            "sit and listen": "figure_success",
            "laugh it off and go to the bar instead": "barkeep_chat",
        }
    ),
    "figure_demand": Scene(
        description=(
            "The figure folds their hands on the table. 'The war-priest who built that "
            "tomb was my grandfather. He sealed something inside — a relic that binds "
            "the dead to service. In the wrong hands, you'd have an army.' They set a "
            "coin purse on the table without counting it. 'Fifty gold now. Fifty more "
            "when you return with it. Don't open it.'"
        ),
        options={
            "accept": "tomb_entrance",
            "refuse": "barkeep_chat",
        }
    ),
    "tomb_entrance": Scene(
        description=(
            "The tomb sits at the end of a dirt track north of town, half-swallowed by "
            "old growth. Torchlight spills from the open entrance. Two skeletal guards "
            "turn their hollow gaze toward you the moment you clear the treeline. "
            "They move fast."
        ),
        options={},
        check=Check(
            stat="strength",
            dc=12,
            success_scene="tomb_fight_win",
            fail_scene="tomb_fight_lose",
            description="Fight the skeleton guards — STR check, DC 12",
            combat=True,
        )
    ),
    "tomb_fight_win": Scene(
        description=(
            "The first skeleton rushes you and you meet it head-on, driving through its "
            "guard and shattering its ribcage. The second lunges from the side — you "
            "sidestep and bring your weapon down hard. Both crumble to dust. The "
            "entrance is clear. Somewhere below, something pulses with a cold, slow light."
        ),
        options={
            "descend into the tomb": "tomb_deep",
            "think twice and return to town": "barkeep_chat",
        }
    ),
    "tomb_fight_lose": Scene(
        description=(
            "The skeleton's first swing clips your shoulder and staggers you. You "
            "scramble back and break their pursuit at the treeline, but not without "
            "cost. You've taken a hit. The skeletons wait at the entrance, patient "
            "as only the dead can be."
        ),
        options={
            "return to the tavern and recover": "barkeep_chat",
            "grit your teeth and try again": "tomb_entrance",
        }
    ),
    "tomb_deep": Scene(
        description=(
            "The staircase leads down into a great stone chamber. Braziers light "
            "themselves as you enter, one by one. At the center, on a stone plinth, "
            "rests a dark iron medallion pulsing with cold light in a slow, irregular "
            "rhythm — like breathing. A voice rises from everywhere at once. "
            "'Leave now. Or join my collection.'"
        ),
        options={
            "take the medallion and run": "tomb_victory",
            "try to reason with the voice": "tomb_parley",
            "back out of the tomb": "tomb_entrance",
        }
    ),
    "tomb_parley": Scene(
        description=(
            "You call out that you want to talk. Silence. Then a translucent figure "
            "rises from the plinth — the war-priest, ancient and hollow-eyed, wearing "
            "the expression of someone who has had a very long time to be disappointed "
            "by the living. 'You speak when you could act.' He regards you. "
            "'Unusual. Say what you came to say.'"
        ),
        options={
            "hear him out": "tomb_deal",
            "grab the medallion while he's distracted": "tomb_victory",
            "back away slowly": "tomb_entrance",
        }
    ),
    "tomb_deal": Scene(
        description=(
            "The war-priest speaks slowly, as if translating from a language he barely "
            "remembers. The medallion was never meant to be wielded — it costs exactly "
            "what it grants. Control over the dead, paid for in years of your own life. "
            "'Tell whoever sent you that it is gone,' he says. 'That is the kinder truth.' "
            "You believe him."
        ),
        options={
            "agree to the deal and leave empty-handed": "peaceful_ending",
            "take the medallion anyway": "tomb_victory",
        }
    ),
    "tomb_victory": Scene(
        description=(
            "You close your hand around the medallion. The chamber shakes. The "
            "war-priest's form tears apart with a sound like paper, and the braziers "
            "go dark all at once. You run. Outside, the tomb doors grind shut behind "
            "you, and the night is suddenly very quiet."
        ),
        options={
            "bring the medallion to the hooded figure": "victory_figure_ending",
            "keep it and disappear": "victory_keep_ending",
        }
    ),

    # --- Endings ---

    "peaceful_ending": Scene(
        description=(
            "You walk out of the tomb with nothing but information. Back at The Rusty "
            "Flagon, the hooded figure listens in silence, then places fifty gold on the "
            "table. 'That's more than I hoped for,' they say, and mean it. They're gone "
            "before you finish your drink. You sit alone with coin in your pocket and no "
            "idea what any of it meant. It's enough."
        ),
        options={"play again": "restart"},
        is_terminal=True
    ),
    "victory_figure_ending": Scene(
        description=(
            "The figure takes the wrapped medallion and sets it in a lead-lined box they "
            "already had waiting. They count out a hundred gold and push it across the "
            "table. 'You did well.' They're gone within the hour. You sit for a long time "
            "afterward, wondering what exactly you handed over, and to whom."
        ),
        options={"play again": "restart"},
        is_terminal=True
    ),
    "victory_keep_ending": Scene(
        description=(
            "Three days out of town, the medallion starts humming at night. On the fourth "
            "night, a voice — the war-priest — speaks from the dark beside your bedroll. "
            "'You didn't listen.' You're not sure if that's a curse, a warning, or just "
            "company. Either way, you're not sleeping again tonight. Possibly not ever."
        ),
        options={"play again": "restart"},
        is_terminal=True
    ),
    "rest_ending": Scene(
        description=(
            "You rent a room upstairs and sleep in a real bed for the first time in weeks. "
            "Whatever the tomb holds, and whatever the hooded figure wanted, it can wait. "
            "The dead aren't going anywhere. Probably. You sleep well, which feels like "
            "a victory of its own."
        ),
        options={"play again": "restart"},
        is_terminal=True
    ),
    "tavern_leave_early": Scene(
        description=(
            "You step back out into the cold night. The town is quiet. Inside, someone was "
            "willing to pay for your help, and someone else was waiting to offer a quest. "
            "You'll never know which would have been worth more. Some stories don't start "
            "because the hero walks past the door."
        ),
        options={"play again": "restart"},
        is_terminal=True
    ),
}
