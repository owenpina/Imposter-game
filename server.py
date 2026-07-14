#!/usr/bin/env python3
"""Imposter Game server.

Zero-dependency backend (Python standard library only). The frontend polls
a JSON HTTP API roughly once a second, which is fine for a turn-based party
game. Run with: python3 server.py
"""

import json
import math
import os
import random
import re
import string
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs

PORT = int(os.environ.get("PORT", 8765))
PUBLIC_DIR = Path(__file__).parent / "public"
MAX_PLAYERS = 20
REVEAL_DELAY = 5.0  # seconds the reveal banner stays up before auto-advancing
CLUE_TURN_TIME_LIMIT = 30.0  # seconds each player gets on their clue turn
VOTING_TIME_LIMIT = 50.0  # seconds the whole voting phase gets
COUNTING_DELAY = 3.0  # seconds spent "counting the votes" before the result
TIE_DISPLAY_DELAY = 4.0  # seconds the TIE! graphic shows before the runoff
ONLINE_TIMEOUT = 6.0  # seconds without a poll before a player is shown offline

DEFAULT_CATEGORIES = {
    "Sports": ["Soccer", "Basketball", "Tennis", "Baseball", "Swimming", "Golf",
               "Boxing", "Cricket", "Hockey", "Volleyball", "Surfing", "Skiing",
               "Rugby", "Cycling", "Bowling", "Football", "Gymnastics",
               "Wrestling", "Archery", "Skateboarding"],
    "Movies": ["Titanic", "Inception", "Jaws", "Frozen", "Avatar", "Gladiator",
               "The Matrix", "Shrek", "Rocky", "Up", "Jurassic Park",
               "Star Wars", "Finding Nemo", "The Lion King", "Toy Story"],
    "Animals": ["Elephant", "Tiger", "Penguin", "Dolphin", "Kangaroo",
                "Giraffe", "Octopus", "Eagle", "Wolf", "Panda", "Crocodile",
                "Cheetah", "Owl", "Shark", "Koala"],
    "Food": ["Pizza", "Sushi", "Tacos", "Burger", "Pasta", "Curry",
             "Pancakes", "Ramen", "Sandwich", "Salad", "Ice Cream", "Burrito",
             "Waffles", "Dumplings", "Nachos"],
    "Occupations": ["Doctor", "Teacher", "Chef", "Pilot", "Firefighter",
                     "Plumber", "Lawyer", "Artist", "Farmer", "Nurse",
                     "Electrician", "Dentist", "Engineer", "Journalist",
                     "Librarian"],
    "Places": ["Beach", "Airport", "Library", "Hospital", "School",
               "Restaurant", "Museum", "Stadium", "Mountain", "Desert",
               "Castle", "Zoo", "Cinema", "Park", "Cruise Ship"],
    "Household Items": ["Toaster", "Vacuum", "Blender", "Pillow", "Umbrella",
                         "Mirror", "Candle", "Lamp", "Broom", "Kettle",
                         "Sponge", "Spatula", "Clock", "Fridge", "Stapler"],
    "Redapt (Sales)": ["Quota", "Pipeline", "Cold Call", "Elevator Pitch",
                        "Commission", "Upsell", "Forecast", "Closer",
                        "Territory", "Cloud Migration", "Managed Services",
                        "Data Center", "Prospecting", "Referral", "Bar Scene",
                        "System Integrator", "AI"],
}

# A loosely related word for each built-in word, used as an optional hint
# for imposters. Custom host-added words have no entry, so no hint shows.
WORD_HINTS = {
    "Soccer": "Goal", "Basketball": "Hoop", "Tennis": "Racket",
    "Baseball": "Diamond", "Swimming": "Pool", "Golf": "Putt",
    "Boxing": "Ring", "Cricket": "Wicket", "Hockey": "Puck",
    "Volleyball": "Net", "Surfing": "Wave", "Skiing": "Slope",
    "Rugby": "Scrum", "Cycling": "Pedal", "Bowling": "Pins",
    "Football": "Touchdown", "Gymnastics": "Balance Beam",
    "Wrestling": "Pin", "Archery": "Bullseye", "Skateboarding": "Ramp",
    "Titanic": "Iceberg", "Inception": "Dream", "Jaws": "Shark",
    "Frozen": "Snow", "Avatar": "Pandora", "Gladiator": "Colosseum",
    "The Matrix": "Simulation", "Shrek": "Ogre", "Rocky": "Boxer",
    "Up": "Balloons", "Jurassic Park": "Dinosaur", "Star Wars": "Lightsaber",
    "Finding Nemo": "Clownfish", "The Lion King": "Pride Rock",
    "Toy Story": "Cowboy",
    "Elephant": "Trunk", "Tiger": "Stripes", "Penguin": "Waddle",
    "Dolphin": "Fin", "Kangaroo": "Pouch", "Giraffe": "Neck",
    "Octopus": "Tentacle", "Eagle": "Talon", "Wolf": "Pack",
    "Panda": "Bamboo", "Crocodile": "Jaws", "Cheetah": "Sprint",
    "Owl": "Hoot", "Shark": "Fin", "Koala": "Eucalyptus",
    "Pizza": "Slice", "Sushi": "Roll", "Tacos": "Shell",
    "Burger": "Patty", "Pasta": "Noodle", "Curry": "Spice",
    "Pancakes": "Syrup", "Ramen": "Broth", "Sandwich": "Bread",
    "Salad": "Lettuce", "Ice Cream": "Scoop", "Burrito": "Wrap",
    "Waffles": "Syrup", "Dumplings": "Steamed", "Nachos": "Cheese",
    "Doctor": "Stethoscope", "Teacher": "Chalkboard", "Chef": "Apron",
    "Pilot": "Cockpit", "Firefighter": "Hose", "Plumber": "Wrench",
    "Lawyer": "Courtroom", "Artist": "Canvas", "Farmer": "Tractor",
    "Nurse": "Bandage", "Electrician": "Wire", "Dentist": "Cavity",
    "Engineer": "Blueprint", "Journalist": "Headline",
    "Librarian": "Bookshelf",
    "Beach": "Sand", "Airport": "Runway", "Library": "Bookshelf",
    "Hospital": "Ward", "School": "Classroom", "Restaurant": "Menu",
    "Museum": "Exhibit", "Stadium": "Bleachers", "Mountain": "Peak",
    "Desert": "Sand Dune", "Castle": "Moat", "Zoo": "Enclosure",
    "Cinema": "Screen", "Park": "Bench", "Cruise Ship": "Deck",
    "Toaster": "Bread", "Vacuum": "Suction", "Blender": "Puree",
    "Pillow": "Cushion", "Umbrella": "Rain", "Mirror": "Reflection",
    "Candle": "Wax", "Lamp": "Bulb", "Broom": "Sweep", "Kettle": "Boil",
    "Sponge": "Scrub", "Spatula": "Flip", "Clock": "Time",
    "Fridge": "Cold", "Stapler": "Bind",
    "Quota": "Target", "Pipeline": "Funnel", "Cold Call": "Outreach",
    "Elevator Pitch": "Tagline", "Commission": "Bonus", "Upsell": "Add-on",
    "Forecast": "Projection", "Closer": "Dealmaker", "Territory": "Region",
    "Cloud Migration": "AWS", "Managed Services": "Support",
    "Data Center": "Servers", "Prospecting": "Outreach",
    "Referral": "Introduction", "Bar Scene": "Drinks",
    "System Integrator": "Partner", "AI": "Automation",
}

ROOM_CODE_CHARS = "".join(c for c in string.ascii_uppercase if c not in "IO")

LOCK = threading.RLock()
ROOMS = {}


def new_id():
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=16))


def new_room_code():
    while True:
        code = "".join(random.choices(ROOM_CODE_CHARS, k=4))
        if code not in ROOMS:
            return code


class ApiError(Exception):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.message = message
        self.status = status


def make_player(name, is_bot=False):
    return {
        "id": new_id(),
        "token": new_id(),
        "name": name,
        "lastSeen": time.time(),
        "score": 0,
        "isBot": is_bot,
    }


BOT_NAMES = ["Bot Rex 🤖", "Bot Ivy 🤖", "Bot Mo 🤖"]


def make_room(host_name, practice=False):
    code = new_room_code()
    host = make_player(host_name)
    room = {
        "code": code,
        "hostId": host["id"],
        "players": {host["id"]: host},
        "order": [host["id"]],
        "settings": {
            "categories": list(DEFAULT_CATEGORIES.keys()),
            "customCategories": {},
            "numImposters": 1,
            "clueRounds": 1,
            "hintsEnabled": True,
        },
        "phase": "lobby",
        "game": None,
        "isPractice": practice,
        "createdAt": time.time(),
    }
    if practice:
        for name in BOT_NAMES:
            bot = make_player(name, is_bot=True)
            room["players"][bot["id"]] = bot
            room["order"].append(bot["id"])
    ROOMS[code] = room
    return room, host


def get_room(code):
    room = ROOMS.get((code or "").upper())
    if not room:
        raise ApiError("Room not found.", 404)
    return room


def auth_player(room, player_id, token):
    player = room["players"].get(player_id)
    if not player or player["token"] != token:
        raise ApiError("Not authorized in this room.", 403)
    player["lastSeen"] = time.time()
    return player


def require_host(room, player):
    if player["id"] != room["hostId"]:
        raise ApiError("Only the host can do that.", 403)


def word_pool(settings):
    pool = []
    for cat in settings["categories"]:
        words = DEFAULT_CATEGORIES.get(cat)
        if words:
            pool.extend((cat, w) for w in words)
    for cat, words in settings.get("customCategories", {}).items():
        pool.extend((cat, w) for w in words)
    return pool


def active_player_ids(room):
    eliminated = set(room["game"]["eliminated"]) if room["game"] else set()
    return [pid for pid in room["order"] if pid in room["players"] and pid not in eliminated]


def check_win(room):
    game = room["game"]
    active = active_player_ids(room)
    active_imposters = [p for p in active if p in game["imposterIds"]]
    active_crew = [p for p in active if p not in game["imposterIds"]]
    if len(active_imposters) == 0:
        return "crew", "All the imposters were caught!"
    if len(active_imposters) >= len(active_crew):
        return "imposters", "The imposters equal or outnumber the crew!"
    return None, None


def start_clue_round(room, first_of_game=False):
    game = room["game"]
    room["phase"] = "clue"
    game["clues"] = []
    game["cluesSubmitted"] = []
    if first_of_game:
        game["round"] = 1
        game["maxRounds"] = room["settings"]["clueRounds"]
    else:
        game["round"] += 1
    game["turnOrder"] = active_player_ids(room)
    game["turnIndex"] = 0
    game["phase_started_at"] = time.time()


def current_turn_player_id(room):
    game = room["game"]
    if 0 <= game["turnIndex"] < len(game["turnOrder"]):
        return game["turnOrder"][game["turnIndex"]]
    return None


def advance_turn(room):
    game = room["game"]
    game["turnIndex"] += 1
    if game["turnIndex"] >= len(game["turnOrder"]):
        advance_past_clue(room)
    else:
        game["phase_started_at"] = time.time()


def start_voting(room, candidates=None):
    """candidates=None means everyone active is votable (normal round);
    a list restricts votable players (runoff after a tie)."""
    game = room["game"]
    room["phase"] = "voting"
    game["votes"] = {}
    game["voteCandidates"] = candidates
    game["phase_started_at"] = time.time()


def start_counting(room):
    game = room["game"]
    room["phase"] = "counting"
    game["phase_started_at"] = time.time()


def resolve_voting(room):
    game = room["game"]
    active = active_player_ids(room)
    candidates = game.get("voteCandidates") or active
    tally = {}
    for voter, target in game["votes"].items():
        if voter in active and target in candidates:
            tally[target] = tally.get(target, 0) + 1

    eliminated_id = None
    if tally:
        top = max(tally.values())
        top_targets = [pid for pid, v in tally.items() if v == top]
        if len(top_targets) > 1:
            # Tie: show the TIE! graphic, then a runoff between tied players.
            game["tieCandidates"] = top_targets
            game["phase_started_at"] = time.time()
            room["phase"] = "tie"
            return
        eliminated_id = top_targets[0]

    if eliminated_id:
        game["eliminated"].append(eliminated_id)

    winner, reason = check_win(room)
    game["reveal"] = {
        "eliminatedId": eliminated_id,
        "eliminatedName": room["players"][eliminated_id]["name"] if eliminated_id else None,
        "eliminatedWasImposter": (eliminated_id in game["imposterIds"]) if eliminated_id else None,
        "tally": tally,
        "winner": winner,
        "reason": reason,
    }
    game["phase_started_at"] = time.time()
    room["phase"] = "reveal"
    if winner:
        game["winner"] = winner
        game["winReason"] = reason


BOT_CLUE_DELAY = 2.5  # seconds a bot "thinks" before submitting its clue
BOT_VOTE_DELAY = 3.0  # seconds into voting before bots start voting

BOT_CREW_FILLER = ["classic", "popular", "common", "well-known", "everyday"]
BOT_IMPOSTER_FILLER = ["interesting", "tricky", "familiar", "typical", "notable"]


def bot_take_clue_turn(room, bot_id):
    game = room["game"]
    bot = room["players"][bot_id]
    if bot_id in game["imposterIds"]:
        clue = random.choice(BOT_IMPOSTER_FILLER)
    else:
        # Crew bots know the word: half the time use the related hint word.
        hint = WORD_HINTS.get(game["word"])
        clue = hint if hint and random.random() < 0.5 else random.choice(BOT_CREW_FILLER)
    game["clues"].append({"round": game["round"], "playerId": bot_id, "name": bot["name"], "clue": clue})
    game["cluesSubmitted"].append(bot_id)
    advance_turn(room)


def tick_bots(room):
    game = room["game"]
    if not room.get("isPractice") or not game or game.get("winner"):
        return
    now = time.time()
    if room["phase"] == "clue":
        turn_id = current_turn_player_id(room)
        if turn_id and room["players"].get(turn_id, {}).get("isBot"):
            if now - game["phase_started_at"] >= BOT_CLUE_DELAY:
                bot_take_clue_turn(room, turn_id)
    elif room["phase"] == "voting":
        active = active_player_ids(room)
        bots_pending = [pid for pid in active
                        if room["players"][pid].get("isBot") and pid not in game["votes"]]
        for i, bot_id in enumerate(bots_pending):
            if now - game["phase_started_at"] >= BOT_VOTE_DELAY + i * 1.5:
                candidates = game.get("voteCandidates") or active
                targets = [pid for pid in candidates if pid != bot_id]
                if targets:
                    game["votes"][bot_id] = random.choice(targets)
                    maybe_advance_voting(room)
                    if room["phase"] != "voting":
                        return


def tick_room(room):
    """Lazily process time-based auto-transitions."""
    game = room["game"]
    if not game:
        return
    tick_bots(room)
    game = room["game"]
    if not game:
        return
    if room["phase"] == "reveal":
        elapsed = time.time() - game["phase_started_at"]
        if elapsed >= REVEAL_DELAY:
            if game.get("winner"):
                room["phase"] = "gameover"
            else:
                active = active_player_ids(room)
                if len(active) < 2:
                    game["winner"] = "crew"
                    game["winReason"] = "Not enough players remain."
                    room["phase"] = "gameover"
                else:
                    game["maxRounds"] = 1
                    start_clue_round(room, first_of_game=False)
    elif room["phase"] == "clue":
        while room["phase"] == "clue":
            elapsed = time.time() - game["phase_started_at"]
            if elapsed < CLUE_TURN_TIME_LIMIT:
                break
            advance_turn(room)
    elif room["phase"] == "voting":
        elapsed = time.time() - game["phase_started_at"]
        if elapsed >= VOTING_TIME_LIMIT:
            start_counting(room)
    elif room["phase"] == "counting":
        elapsed = time.time() - game["phase_started_at"]
        if elapsed >= COUNTING_DELAY:
            resolve_voting(room)
    elif room["phase"] == "tie":
        elapsed = time.time() - game["phase_started_at"]
        if elapsed >= TIE_DISPLAY_DELAY:
            start_voting(room, candidates=game.get("tieCandidates"))


def advance_past_clue(room):
    game = room["game"]
    if game["round"] < game["maxRounds"]:
        start_clue_round(room, first_of_game=False)
    else:
        start_voting(room)


def maybe_advance_voting(room):
    game = room["game"]
    active = set(active_player_ids(room))
    if active and active.issubset(set(game["votes"].keys())):
        start_counting(room)


def public_room_state(room, viewer_id):
    tick_room(room)
    now = time.time()
    game = room["game"]

    players = []
    for pid in room["order"]:
        p = room["players"].get(pid)
        if not p:
            continue
        players.append({
            "id": p["id"],
            "name": p["name"],
            "isHost": pid == room["hostId"],
            "online": p.get("isBot") or (now - p["lastSeen"]) < ONLINE_TIMEOUT,
            "eliminated": bool(game and pid in game["eliminated"]),
            "isYou": pid == viewer_id,
        })

    state = {
        "code": room["code"],
        "phase": room["phase"],
        "hostId": room["hostId"],
        "you": viewer_id,
        "isPractice": room.get("isPractice", False),
        "players": players,
        "settings": {
            "categories": room["settings"]["categories"],
            "customCategories": room["settings"]["customCategories"],
            "numImposters": room["settings"]["numImposters"],
            "clueRounds": room["settings"]["clueRounds"],
            "hintsEnabled": room["settings"].get("hintsEnabled", False),
            "availableCategories": {k: len(v) for k, v in DEFAULT_CATEGORIES.items()},
        },
    }

    if game:
        me_is_imposter = viewer_id in game["imposterIds"]
        active_ids = active_player_ids(room)
        you_eliminated = viewer_id in game["eliminated"]

        turn_seconds_left = None
        current_turn_id = None
        if room["phase"] == "clue":
            turn_seconds_left = max(0, math.ceil(CLUE_TURN_TIME_LIMIT - (now - game["phase_started_at"])))
            current_turn_id = current_turn_player_id(room)

        voting_seconds_left = None
        vote_map = {}
        if room["phase"] == "voting":
            voting_seconds_left = max(0, math.ceil(VOTING_TIME_LIMIT - (now - game["phase_started_at"])))
            vote_map = {v: t for v, t in game.get("votes", {}).items() if v in active_ids}

        counting_seconds_left = None
        if room["phase"] == "counting":
            counting_seconds_left = max(0, math.ceil(COUNTING_DELAY - (now - game["phase_started_at"])))

        vote_candidates = game.get("voteCandidates")
        tie_names = []
        if room["phase"] == "tie":
            tie_names = [room["players"][pid]["name"]
                         for pid in game.get("tieCandidates", []) if pid in room["players"]]

        state["game"] = {
            "round": game["round"],
            "maxRounds": game["maxRounds"],
            "category": game["category"],
            "yourWord": None if me_is_imposter else game["word"],
            "youAreImposter": me_is_imposter,
            "youAreEliminated": you_eliminated,
            "clues": game["clues"],
            "cluesSubmittedCount": len(set(game["cluesSubmitted"]) & set(active_ids)),
            "activeCount": len(active_ids),
            "youSubmittedClue": viewer_id in game["cluesSubmitted"],
            "turnTimeLimit": CLUE_TURN_TIME_LIMIT,
            "turnSecondsLeft": turn_seconds_left,
            "currentTurnPlayerId": current_turn_id,
            "currentTurnPlayerName": room["players"][current_turn_id]["name"] if current_turn_id in room["players"] else None,
            "isYourTurn": current_turn_id == viewer_id,
            "votingTimeLimit": VOTING_TIME_LIMIT,
            "votingSecondsLeft": voting_seconds_left,
            "countingSecondsLeft": counting_seconds_left,
            "voteCandidates": vote_candidates,
            "isRunoff": bool(vote_candidates),
            "tieCandidateNames": tie_names,
            "votesCount": len(vote_map) if room["phase"] == "voting" else 0,
            "votes": vote_map,
            "youVoted": viewer_id in game.get("votes", {}),
            "yourVoteTargetId": game.get("votes", {}).get(viewer_id),
            "reveal": game.get("reveal"),
            "winner": game.get("winner"),
            "winReason": game.get("winReason"),
            "lastGuess": game.get("lastGuessPublic"),
            "hintsEnabled": game.get("hintsEnabled", False),
            "imposterHint": (
                f"Similar word: {WORD_HINTS[game['word']]}"
                if me_is_imposter and game.get("hintsEnabled") and game["word"] in WORD_HINTS
                else None
            ),
        }
        if room["phase"] == "gameover":
            state["game"]["roles"] = [
                {
                    "id": pid,
                    "name": room["players"][pid]["name"],
                    "isImposter": pid in game["imposterIds"],
                }
                for pid in room["order"] if pid in room["players"]
            ]
            state["game"]["secretWord"] = game["word"]
    return state


# ---------------------------------------------------------------------------
# API action handlers
# ---------------------------------------------------------------------------

def parse_custom_categories(raw):
    """raw: {"Category Name": "word1, word2, word3"} -> {"Category Name": [words]}"""
    result = {}
    if not isinstance(raw, dict):
        return result
    for name, words_str in raw.items():
        name = str(name).strip()[:30]
        if not name:
            continue
        words = [w.strip() for w in re.split(r"[,\n]", str(words_str)) if w.strip()]
        words = [w[:30] for w in words][:40]
        if words:
            result[name] = words
    return result


def action_create_room(body):
    name = str(body.get("name", "")).strip()[:20] or "Host"
    practice = bool(body.get("practice"))
    room, host = make_room(name, practice=practice)
    return {"roomCode": room["code"], "playerId": host["id"], "token": host["token"]}


def action_join_room(code, body):
    room = get_room(code)
    with LOCK:
        if room["phase"] != "lobby":
            raise ApiError("This game has already started.", 409)
        if len(room["players"]) >= MAX_PLAYERS:
            raise ApiError("Room is full.", 409)
        name = str(body.get("name", "")).strip()[:20]
        if not name:
            raise ApiError("Enter a name.")
        existing = {p["name"].lower() for p in room["players"].values()}
        if name.lower() in existing:
            raise ApiError("That name is already taken in this room.")
        player = make_player(name)
        room["players"][player["id"]] = player
        room["order"].append(player["id"])
        return {"roomCode": room["code"], "playerId": player["id"], "token": player["token"]}


def action_settings(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        require_host(room, player)
        if room["phase"] != "lobby":
            raise ApiError("Can't change settings after the game has started.")
        categories = body.get("categories")
        if isinstance(categories, list):
            valid = [c for c in categories if c in DEFAULT_CATEGORIES][:20]
            room["settings"]["categories"] = valid
        if "customCategories" in body:
            room["settings"]["customCategories"] = parse_custom_categories(body.get("customCategories"))
        if "numImposters" in body:
            try:
                n = int(body["numImposters"])
            except (TypeError, ValueError):
                n = room["settings"]["numImposters"]
            room["settings"]["numImposters"] = max(1, min(6, n))
        if "clueRounds" in body:
            try:
                n = int(body["clueRounds"])
            except (TypeError, ValueError):
                n = room["settings"]["clueRounds"]
            room["settings"]["clueRounds"] = max(1, min(6, n))
        if "hintsEnabled" in body:
            room["settings"]["hintsEnabled"] = bool(body.get("hintsEnabled"))
        return {"ok": True}


def action_start(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        require_host(room, player)
        if room["phase"] != "lobby":
            raise ApiError("Game already started.")
        total = len(room["order"])
        if total < 3:
            raise ApiError("Need at least 3 players to start.")
        n_imposters = room["settings"]["numImposters"]
        if n_imposters >= total - 1:
            raise ApiError("Too many imposters for this many players.")
        pool = word_pool(room["settings"])
        if not pool:
            raise ApiError("Select at least one category with words.")

        category, word = random.choice(pool)
        imposters = set(random.sample(room["order"], n_imposters))

        room["game"] = {
            "category": category,
            "word": word,
            "imposterIds": imposters,
            "round": 0,
            "maxRounds": room["settings"]["clueRounds"],
            "clues": [],
            "cluesSubmitted": [],
            "turnOrder": [],
            "turnIndex": 0,
            "votes": {},
            "eliminated": [],
            "winner": None,
            "winReason": None,
            "reveal": None,
            "lastGuessPublic": None,
            "hintsEnabled": room["settings"].get("hintsEnabled", False),
            "phase_started_at": time.time(),
        }
        start_clue_round(room, first_of_game=True)
        return {"ok": True}


def action_clue(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        tick_room(room)
        game = room["game"]
        if not game or room["phase"] != "clue":
            raise ApiError("Not in a clue round right now.")
        if player["id"] in game["eliminated"]:
            raise ApiError("You've been eliminated and can only spectate.")
        if current_turn_player_id(room) != player["id"]:
            raise ApiError("It's not your turn yet.")
        clue = str(body.get("clue", "")).strip()[:40]
        if not clue:
            raise ApiError("Clue can't be empty.")
        if player["id"] not in game["imposterIds"] and clue.lower() == game["word"].lower():
            raise ApiError("You can't use the secret word itself!")
        game["clues"].append({"round": game["round"], "playerId": player["id"], "name": player["name"], "clue": clue})
        game["cluesSubmitted"].append(player["id"])
        advance_turn(room)
        return {"ok": True}


def action_vote(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        tick_room(room)
        game = room["game"]
        if not game or room["phase"] != "voting":
            raise ApiError("Not in a voting round right now.")
        if player["id"] in game["eliminated"]:
            raise ApiError("You've been eliminated and can only spectate.")
        target = body.get("targetId")
        active = active_player_ids(room)
        candidates = game.get("voteCandidates") or active
        if target == player["id"] or target not in active or target not in candidates:
            raise ApiError("Invalid vote target.")
        game["votes"][player["id"]] = target
        maybe_advance_voting(room)
        return {"ok": True}


def action_guess(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        game = room["game"]
        if not game or room["phase"] not in ("clue", "voting", "counting", "tie"):
            raise ApiError("Can't guess right now.")
        if player["id"] not in game["imposterIds"]:
            raise ApiError("Only imposters can guess the word.")
        if player["id"] in game["eliminated"]:
            raise ApiError("You've been eliminated.")
        guess = str(body.get("guess", "")).strip()
        correct = guess.lower() == game["word"].lower()
        if correct:
            game["winner"] = "imposters"
            game["winReason"] = f"{player['name']} correctly guessed the word “{game['word']}”!"
            game["reveal"] = {
                "eliminatedId": None, "eliminatedName": None, "eliminatedWasImposter": None,
                "tally": {}, "winner": "imposters", "reason": game["winReason"],
            }
            game["phase_started_at"] = time.time()
            room["phase"] = "reveal"
        else:
            game["lastGuessPublic"] = f"An imposter attempted a guess... and got it wrong."
        return {"ok": True, "correct": correct}


def action_toggle_hints(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        require_host(room, player)
        game = room["game"]
        if not game:
            raise ApiError("Game hasn't started.")
        game["hintsEnabled"] = not game.get("hintsEnabled", False)
        # Keep the room setting in sync so it carries into the next round too.
        room["settings"]["hintsEnabled"] = game["hintsEnabled"]
        return {"ok": True, "hintsEnabled": game["hintsEnabled"]}


def action_advance(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        require_host(room, player)
        game = room["game"]
        if not game:
            raise ApiError("Game hasn't started.")
        if room["phase"] == "clue":
            advance_turn(room)  # skip whoever's turn it currently is
        elif room["phase"] == "voting":
            start_counting(room)
        elif room["phase"] == "counting":
            resolve_voting(room)
        elif room["phase"] == "tie":
            start_voting(room, candidates=game.get("tieCandidates"))
        elif room["phase"] == "reveal":
            game["phase_started_at"] = 0  # force tick_room to fire immediately
        return {"ok": True}


def action_play_again(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        require_host(room, player)
        if room["phase"] != "gameover":
            raise ApiError("Game isn't over yet.")
        room["phase"] = "lobby"
        room["game"] = None
        return {"ok": True}


def action_leave(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        del room["players"][player["id"]]
        room["order"] = [pid for pid in room["order"] if pid != player["id"]]
        if not room["players"]:
            ROOMS.pop(room["code"], None)
            return {"ok": True}
        if room["hostId"] == player["id"]:
            room["hostId"] = room["order"][0]
        if room["game"] and room["phase"] not in ("lobby", "gameover"):
            winner, reason = check_win(room)
            if winner:
                room["game"]["winner"] = winner
                room["game"]["winReason"] = reason
                room["phase"] = "gameover"
        return {"ok": True}


def action_kick(code, body):
    room = get_room(code)
    with LOCK:
        player = auth_player(room, body.get("playerId"), body.get("token"))
        require_host(room, player)
        if room["phase"] != "lobby":
            raise ApiError("Can only remove players before the game starts.")
        target = body.get("targetId")
        if target == player["id"] or target not in room["players"]:
            raise ApiError("Invalid target.")
        del room["players"][target]
        room["order"] = [pid for pid in room["order"] if pid != target]
        return {"ok": True}


def action_state(code, query):
    room = get_room(code)
    with LOCK:
        player_id = query.get("playerId", [None])[0]
        token = query.get("token", [None])[0]
        auth_player(room, player_id, token)
        return public_room_state(room, player_id)


ROUTES = {
    ("POST", "/join"): action_join_room,
    ("POST", "/settings"): action_settings,
    ("POST", "/start"): action_start,
    ("POST", "/clue"): action_clue,
    ("POST", "/vote"): action_vote,
    ("POST", "/guess"): action_guess,
    ("POST", "/toggle-hints"): action_toggle_hints,
    ("POST", "/advance"): action_advance,
    ("POST", "/play-again"): action_play_again,
    ("POST", "/leave"): action_leave,
    ("POST", "/kick"): action_kick,
}

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
}


class Handler(BaseHTTPRequestHandler):
    server_version = "ImposterGame/1.0"

    def log_message(self, fmt, *args):
        pass

    def _send_json(self, obj, status=200):
        payload = json.dumps(obj).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(payload)

    def _send_static(self, rel_path):
        if rel_path == "" or rel_path == "/":
            rel_path = "index.html"
        rel_path = rel_path.lstrip("/")
        file_path = (PUBLIC_DIR / rel_path).resolve()
        if PUBLIC_DIR.resolve() not in file_path.parents and file_path != PUBLIC_DIR.resolve():
            self.send_error(404)
            return
        if not file_path.exists() or not file_path.is_file():
            self.send_error(404)
            return
        data = file_path.read_bytes()
        ctype = CONTENT_TYPES.get(file_path.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/rooms/state":
            query = parse_qs(parsed.query)
            code = query.get("code", [None])[0]
            try:
                self._send_json(action_state(code, query))
            except ApiError as e:
                self._send_json({"error": e.message}, e.status)
            return
        if parsed.path.startswith("/api/"):
            self.send_error(404)
            return
        self._send_static(parsed.path)

    def do_POST(self):
        parsed = urlparse(self.path)
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b"{}"
        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            body = {}

        try:
            if parsed.path == "/api/rooms":
                result = action_create_room(body)
                self._send_json(result)
                return
            m = re.match(r"^/api/rooms/([A-Za-z0-9]+)/([a-z\-]+)$", parsed.path)
            if not m:
                self.send_error(404)
                return
            code, action = m.groups()
            fn = ROUTES.get(("POST", "/" + action))
            if not fn:
                self.send_error(404)
                return
            result = fn(code, body)
            self._send_json(result)
        except ApiError as e:
            self._send_json({"error": e.message}, e.status)
        except Exception as e:  # noqa: BLE001
            self._send_json({"error": f"Server error: {e}"}, 500)


def main():
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"Imposter Game running at http://localhost:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.shutdown()


if __name__ == "__main__":
    main()
