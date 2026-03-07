"""
+---+------------+----+----------------------+-------------------+---------------+---------------------------+
| k |       F_k (€/num) | M_k | Mise tour (M_k×F_k) | Mise cumulée (€) | Gain brut (36·F_k) | Gain net (36·F_k − mise cumulée) |
+---+------------+----+----------------------+-------------------+---------------+---------------------------+
| 1 |            1                 | 17 |         17           |        17         |      36       |            19             |
| 2 |           1                | 15 |         15           |        32         |      36       |             4             |
| 3 |           2             | 13 |         26           |        58         |      72       |            14             |
| 4 |           3                | 13 |         39           |        97         |     108       |            11             |
| 5 |           5               | 13 |         65           |       162         |     180       |            18             |
| 6 |           8               | 13 |        104           |       266         |     288       |            22             |
| 7 |           13      |  13 |        169           |       435         |     468       |            33             |
| 8 |           21      | 13 |        273           |       708         |     756       |            48             |

╔══════════════════════════════════════════════════════════════╗
║              ULTRA ROULETTE PRO - VERSION 3 SIGNAUX          ║
║                                                              ║
║  Outil d'observation statistique pour la roulette européenne ║
║  3 Signaux : ✅ GO  |  ⏳ ATTENTE  |  🔴 STOP              ║
║  ⚠ La roulette est un jeu de hasard pur.                    ║
╚══════════════════════════════════════════════════════════════╝
"""

import os
import math
import random
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set, Tuple
from collections import deque

# ═══════════════════════════════════════════════════════════════
#  FLAG DEBUG
# ═══════════════════════════════════════════════════════════════

DEBUG = False

# ═══════════════════════════════════════════════════════════════
#  SECTION 1 : COULEURS ANSI
# ═══════════════════════════════════════════════════════════════

class Color:
    GREEN   = '\033[32m'
    YELLOW  = '\033[33m'
    RED     = '\033[31m'
    CYAN    = '\033[36m'
    MAGENTA = '\033[35m'
    BOLD    = '\033[1m'
    DIM     = '\033[2m'
    END     = '\033[0m'

def colorize(*args) -> str:
    codes = "".join(a for a in args if a.startswith('\033'))
    text  = "".join(a for a in args if not a.startswith('\033'))
    return f"{codes}{text}{Color.END}"

# ═══════════════════════════════════════════════════════════════
#  SECTION 2 : CYLINDRE EUROPÉEN
# ═══════════════════════════════════════════════════════════════
CYLINDER = [
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35,
    3, 26, 0,
    32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30,
    8, 23, 10
]

TOP   = CYLINDER[0:16]
RIGHT = CYLINDER[16:19]
BOT   = CYLINDER[19:34]
LEFT  = CYLINDER[34:37]

WAIT_BEFORE_DECREMENT = 5
START_NEIGHBOR_DIST = 7
MIN_NEIGHBOR_DIST = 6

def cylinder_neighbors(n: int, distance: int) -> List[int]:
    idx       = CYLINDER.index(n)
    size      = len(CYLINDER)
    neighbors = []
    for delta in range(-distance, distance + 1):
        if delta == 0:
            continue
        neighbors.append(CYLINDER[(idx + delta) % size])
    return neighbors

def display_cylinder_full(
    last_number  : int,
    neighbor_dist: int,
    go_numbers   : Set[int],
    wait_numbers : Set[int]
) -> str:
    neighbors = set(cylinder_neighbors(last_number, neighbor_dist))

    def fmt(num):
        n_str = f"{num:02d}"
        if num == last_number:
            return colorize(f"[{n_str}]", Color.MAGENTA, Color.BOLD)
        elif num in neighbors:
            return colorize(f"<{n_str}>", Color.YELLOW, Color.BOLD)
        else:
            return colorize(f" {n_str} ", Color.DIM)

    top_line = " ".join(fmt(n) for n in TOP)
    bot_line = " ".join(fmt(n) for n in reversed(BOT))

    sides = []
    max_space = 120
    for i in range(3):
        l = fmt(LEFT[2 - i])
        r = fmt(RIGHT[i])
        sides.append(f"{l}{' ' * max_space}{r}")

    return (
        "  " + top_line + "\n" +
        "\n".join(sides) + "\n" +
        "  " + bot_line
    )

# ═══════════════════════════════════════════════════════════════
#  SECTION 3 : DATACLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ZoneConfig:
    name      : str
    numbers   : Set[int]
    category  : str
    wait      : int
    definition: str

@dataclass
class ZoneState:
    hits: int = 0                          # occurrences dans la fenêtre
    last_seen: int = 9999                  # tirages depuis dernière apparition (global)
    signal: str = "STOP"
    absent: int = 0

# ═══════════════════════════════════════════════════════════════
#  SECTION 5 : SIGNAL
# ═══════════════════════════════════════════════════════════════

MARGE = 4

# SEUILS : pour chaque catégorie on définit (h_go, a_go)
#  - h_go : nombre maximal d'occurrences (hits) dans la fenêtre glissante
#           (ici window_size, par défaut 37) pour que la zone puisse
#           potentiellement devenir GO.
#            Pourcentage de chance classique * 0.618 (ratio de la section dorée) :
#  - a_go : nombre minimum de tirages d'absence (last_seen) depuis la
#           dernière apparition dans l'historique GLOBAL pour déclencher GO.
#
SEUILS = {
    "Douzaine": (7, 7), # 12*0.618 = 7.4 → arrondi à 7 pour être plus sélectif sur ce signal plus fort
    "Colonne":  (7, 7), # 12*0.618 = 7.4 → arrondi à 7 pour être plus sélectif sur ce signal plus fort
    "Sixain":   (3,  18), # 6*0.618 = 3.7 → arrondi à 3 pour être plus sélectif sur ce signal plus fort
}

def compute_signal(cfg: ZoneConfig, state: ZoneState, total_window: int) -> str:
    # total_window sert juste à détecter fenêtre vide au départ
    if total_window == 0 or cfg.category not in SEUILS:
        return "STOP"
    h_go, a_go = SEUILS[cfg.category]
    hits   = state.hits
    absent = state.last_seen

    if hits <= h_go and absent >= a_go:
        return "GO"
    if hits <= h_go + MARGE and absent >= a_go - MARGE:
        return "ATTENTE"
    return "STOP"

# ═══════════════════════════════════════════════════════════════
#  SECTION 4 : ZONES (build_zones)
# ═══════════════════════════════════════════════════════════════

def build_zones() -> Dict[str, ZoneConfig]:
    zones: Dict[str, ZoneConfig] = {}

    def add(name, numbers, category, wait, definition):
        zones[name] = ZoneConfig(
            name       = name,
            numbers    = set(numbers),
            category   = category,
            wait       = wait,
            definition = definition,
        )

    # Douzaines
    add("Douzaine 1", range(1, 13), "Douzaine", SEUILS["Douzaine"][1], "1→12")
    add("Douzaine 2", range(13, 25), "Douzaine", SEUILS["Douzaine"][1], "13→24")
    add("Douzaine 3", range(25, 37), "Douzaine", SEUILS["Douzaine"][1], "25→36")

    # Colonnes
    add("Colonne 1", {1,4,7,10,13,16,19,22,25,28,31,34}, "Colonne", SEUILS["Colonne"][1],
        "1 4 7 10 13 16 19 22 25 28 31 34")
    add("Colonne 2", {2,5,8,11,14,17,20,23,26,29,32,35}, "Colonne", SEUILS["Colonne"][1],
        "2 5 8 11 14 17 20 23 26 29 32 35")
    add("Colonne 3", {3,6,9,12,15,18,21,24,27,30,33,36}, "Colonne", SEUILS["Colonne"][1],
        "3 6 9 12 15 18 21 24 27 30 33 36")

    # Sixains
    add("Sixain 1", range(1, 7), "Sixain", SEUILS["Sixain"][1], "1→6")
    add("Sixain 2", range(7, 13), "Sixain", SEUILS["Sixain"][1], "7→12")
    add("Sixain 3", range(13, 19), "Sixain", SEUILS["Sixain"][1], "13→18")
    add("Sixain 4", range(19, 25), "Sixain", SEUILS["Sixain"][1], "19→24")
    add("Sixain 5", range(25, 31), "Sixain", SEUILS["Sixain"][1], "25→30")
    add("Sixain 6", range(31, 37), "Sixain", SEUILS["Sixain"][1], "31→36")

    return zones

# ═══════════════════════════════════════════════════════════════
#  SECTION 6 : TRACKER
# ═══════════════════════════════════════════════════════════════

class RouletteTracker:
    def __init__(self, window_size: int = 37):
        self.window_size = window_size
        self.window_history = deque(maxlen=self.window_size)  # 37 derniers tirages
        self.history: List[int] = []                         # historique global (non limité)
        self.zones = build_zones()
        self.states: Dict[str, ZoneState] = {name: ZoneState() for name in self.zones.keys()}
        self.total_tirages = 0
        # voisins / cylindre
        self.neighbor_dist = START_NEIGHBOR_DIST
        self.wait_losses = 0
        # streak hors voisins (utilisé pour légende)
        self.cylinder_loss_streak = 0

    # ── ajout d'un numéro ─────────────────────────────────────
    def add_number(self, n: int):
        # append to global history (non limité)
        self.history.append(n)
        self.total_tirages += 1

        # append to sliding window (maxlen=window_size)
        self.window_history.append(n)
        total_window = len(self.window_history)

        # Mettre à jour streak hors voisins (détection sur voisins du précédent tirage)
        if len(self.history) >= 2:
            prev = self.history[-2]

            # construire les voisins en utilisant la distance courante
            neigh = set(cylinder_neighbors(prev, self.neighbor_dist))
            neigh.add(prev)  # considérer aussi le numéro central comme "voisin actif"

            if n in neigh:
                # Un voisin (ou le même numéro) vient de sortir -> reset complet
                self.cylinder_loss_streak = 0
                self.neighbor_dist = START_NEIGHBOR_DIST
            else:
                # Perte hors voisins : incrément du streak
                self.cylinder_loss_streak += 1

                # Règle demandée : on attend WAIT_BEFORE_DECREMENT pertes avant de commencer à décrémenter.
                if self.cylinder_loss_streak < WAIT_BEFORE_DECREMENT:
                    # Tant que le palier n'est pas atteint, on conserve la valeur de départ.
                    self.neighbor_dist = START_NEIGHBOR_DIST
                else:
                    # Nombre de décréments effectués depuis le palier (1 au premier palier).
                    decrements_since_threshold = self.cylinder_loss_streak - WAIT_BEFORE_DECREMENT + 1
                    # nouvelle distance = START - décréments, mais pas en dessous de MIN_NEIGHBOR_DIST
                    self.neighbor_dist = max(START_NEIGHBOR_DIST - decrements_since_threshold, MIN_NEIGHBOR_DIST)

        # Update each zone:
        for name, cfg in self.zones.items():
            st = self.states[name]

            # Hits = occurrences inside the sliding window (fenêtre de window_size)
            st.hits = sum(1 for x in self.window_history if x in cfg.numbers)

            # last_seen : tirages depuis dernière apparition dans l'historique GLOBAL
            try:
                rev_index = next(i for i, val in enumerate(reversed(self.history)) if val in cfg.numbers)
                # rev_index = 0 => le dernier tirage est dans la zone
                st.last_seen = rev_index
            except StopIteration:
                st.last_seen = 9999

            # compute signal (on passe la taille de la fenêtre)
            st.signal = compute_signal(cfg, st, total_window)

        # redraw / display
        os.system('cls' if os.name == 'nt' else 'clear')
        self._display(n, total_window)

    # ── prefill ───────────────────────────────────────────────
    def prefill(self, count: int):
        for _ in range(count):
            self.add_number(random.randint(0, 36))

    # ── numéros GO / ATTENTE (pour cylindre coloré) ───────────
    def _signal_numbers(self) -> Tuple[Set[int], Set[int]]:
        go_nums: Set[int] = set()
        wait_nums: Set[int] = set()
        for name, cfg in self.zones.items():
            sig = self.states[name].signal
            if sig == "GO":
                go_nums |= cfg.numbers
            elif sig == "ATTENTE":
                wait_nums |= cfg.numbers
        wait_nums -= go_nums
        return go_nums, wait_nums

    # ── affichage principal ───────────────────────────────────
    def _display(self, last: int, total: int):

        go_nums, wait_nums = self._signal_numbers()

        # ── En-tête ───────────────────────────────────────────
        print("#" * 60)
        print(colorize(
            f"  Dernier : {last:02d}   |   Total fenêtre : {total}   "
            f"|   Dist voisins : ±{self.neighbor_dist}",
            Color.BOLD, Color.GREEN if last != 0 else Color.CYAN
        ))

        # ══════════════════════════════════════════════════════
        #  CYLINDRE
        # ══════════════════════════════════════════════════════
        print()
        print(colorize(
            "  ── CYLINDRE ──────────────────────────────────────────"
            "──────────────────────────────",
            Color.BOLD, Color.CYAN
        ))
        print(colorize(
            f"  [XX]=sorti  <XX>=voisin(±{self.neighbor_dist})  ",
            Color.DIM))

        # ── Compteur pertes cylindre ──────────────────────────
        streak = self.cylinder_loss_streak
        if streak == 0:
            streak_str = colorize(
                f"  🟢 Voisins actifs — pertes consécutives : {streak}",
                Color.GREEN
            )
        elif streak <= WAIT_BEFORE_DECREMENT-2:
            streak_str = colorize(
                f"  ⏳ Pertes hors voisins : {streak}",
                Color.YELLOW
            )
        else:
            streak_str = colorize(
                f"  🔴 Pertes hors voisins : {streak}",
                Color.RED
            )
        print(streak_str)
        print()
        print(display_cylinder_full(last, self.neighbor_dist, go_nums, wait_nums))
        print()

        # ══════════════════════════════════════════════════════
        #  ZONES GO
        # ══════════════════════════════════════════════════════
        self._display_signal_block("GO")

        # ══════════════════════════════════════════════════════════════
        #  ZONES ATTENTE
        # ══════════════════════════════════════════════════════════════
        self._display_signal_block("ATTENTE")

        # ══════════════════════════════════════════════════════════════
        #  TABLEAU COMPLET — DEBUG
        # ══════════════════════════════════════════════════════════════
        if DEBUG:
            self._display_debug_table()

    # ── bloc GO ou ATTENTE ────────────────────────────────────
    def _display_signal_block(self, signal: str):
        if signal == "GO":
            color  = Color.GREEN
            icon   = "✅ GO"
            border = "═"
        else:
            color  = Color.YELLOW
            icon   = "⏳ ATTENTE"
            border = "─"

        entries = [
            (name, cfg, self.states[name])
            for name, cfg in self.zones.items()
            if self.states[name].signal == signal
        ]

        print(colorize(
            f"  {border*2} {icon} ({len(entries)} zone(s)) "
            f"{border * max(0, 60 - len(icon) - len(str(len(entries))))}",
            Color.BOLD, color
        ))

        if not entries:
            print(colorize(
                f"  Aucune zone en {signal}.\n",
                Color.DIM
            ))
            return

        print(colorize(
            f"  {'Zone':<22} {'Définition':<30} "
            f"{'Hits':>8}  {'Absent':>6}",
            Color.BOLD
        ))

        for name, cfg, st in entries:
            hits_str   = colorize(f"{st.hits:>5}/{self.window_size}", Color.CYAN)
            absent_str = colorize(f"{st.last_seen:>6}", color)
            print(
                f"  {name:<22} {cfg.definition:<30} "
                f"{hits_str}  {absent_str}"
            )
        print()

    # ── tableau debug complet ─────────────────────────────────
    def _display_debug_table(self):
        sep = "─" * 112
        print(colorize(
            "\n  ── DEBUG : TOUTES LES ZONES ───────────────────────────"
            "───────────────────────────────",
            Color.BOLD, Color.DIM
        ))

        categories = ["Douzaine", "Colonne", "Sixain"]

        for cat in categories:
            print(colorize(
                f"\n  ▸ {cat.upper()}",
                Color.BOLD, Color.DIM
            ))
            print(colorize(
                f"  {'Zone':<22} {'Définition':<36} "
                f"{'Hits':>8}  {'Absent':>8}  Signal",
                Color.DIM
            ))
            print(colorize(f"  {sep}", Color.DIM))

            for name, cfg in self.zones.items():
                if cfg.category != cat:
                    continue
                st = self.states[name]

                hits_str = colorize(f"{st.hits:>5}/{self.window_size}", Color.CYAN)

                # couleur suivant last_seen vs wait
                if st.last_seen >= cfg.wait:
                    ac = Color.RED
                elif st.last_seen >= cfg.wait // 2:
                    ac = Color.YELLOW
                else:
                    ac = Color.DIM
                absent_str = colorize(f"{st.last_seen:>3}", ac)

                if st.signal == "GO":
                    sig_str = colorize("✅ GO     ", Color.GREEN, Color.BOLD)
                elif st.signal == "ATTENTE":
                    sig_str = colorize("⏳ ATTENTE", Color.YELLOW, Color.BOLD)
                else:
                    sig_str = colorize("🔴 STOP   ", Color.DIM)

                print(colorize(
                    f"  {name:<22} {cfg.definition:<36} "
                    f"{hits_str}  {absent_str}  ",
                    Color.DIM
                ) + sig_str)

            print(colorize(f"  {sep}", Color.DIM))

# ═══════════════════════════════════════════════════════════════
#  SECTION 7 : AIDE
# ═══════════════════════════════════════════════════════════════

def print_help():
    print(colorize("""
      ┌────────────────────────────────────────────────────────────┐
      │  COMMANDES                                                 │
      │  0-36  → entrer un numéro sorti                           │
      │  d     → préfill 37 tirages aléatoires                    │
      │  h     → afficher cette aide                              │
      │  q     → quitter                                          │
      ├────────────────────────────────────────────────────────────┤
      │  SIGNAUX (marge d'approche : ±4)                         │
      │  Douzaine/Colonne : GO si hits ≤ 10 ET absent ≥ 12       │
      │  Sixain           : GO si hits ≤  3 ET absent ≥ 18       │
      │  ATTENTE : dans la marge de 4 unités des seuils GO       │
      ├────────────────────────────────────────────────────────────┤
      │  CYLINDRE                                                  │
      │  [XX]=sorti  <XX>=voisin  vert=GO  cyan=ATTENTE           │
      │  Distance voisins : ±3 → ±6 (reset si voisin sort)       │
      │  🟢=voisin actif  ⏳=1-3 pertes  🔴=4+ pertes            │
      └────────────────────────────────────────────────────────────┘
    """, Color.DIM))

# ═══════════════════════════════════════════════════════════════
#  SECTION 8 : BOUCLE PRINCIPALE
# ═══════════════════════════════════════════════════════════════

def main():
    tracker = RouletteTracker()
    os.system('cls' if os.name == 'nt' else 'clear')
    print(colorize(
        "\n  ULTRA ROULETTE PRO — 3 Signaux\n",
        Color.BOLD, Color.CYAN
    ))
    print(colorize(
        "  ⚠ Outil statistique uniquement. "
        "La roulette est un jeu de hasard.\n",
        Color.YELLOW
    ))
    print_help()

    while True:
        try:
            val = input(
                colorize(
                    "\n  Numéro (0-36) / d / h / q : ",
                    Color.BOLD
                )
            ).strip().lower()

            if val == 'q':
                print(colorize(
                    "\n  Session terminée. Bonne chance !\n", Color.BOLD
                ))
                break
            elif val == 'h':
                print_help()
            elif val == 'd':
                tracker.prefill(37)
            else:
                n = int(val)
                if 0 <= n <= 36:
                    tracker.add_number(n)
                else:
                    print(colorize(
                        "  ⚠ Numéro entre 0 et 36.\n", Color.RED
                    ))

        except ValueError:
            print(colorize(
                "  ⚠ Entrez un chiffre (0-36) ou une commande.\n",
                Color.RED
            ))
        except KeyboardInterrupt:
            print(colorize(
                "\n\n  Interruption. Au revoir !\n", Color.BOLD
            ))
            break

if __name__ == "__main__":
    main()
