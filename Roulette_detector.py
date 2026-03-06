"""
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
from typing import Optional, List, Dict, Set

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
    5, 24, 16, 33, 1, 20, 14, 31, 9, 22, 18, 29, 7, 28, 12, 35,  # TOP  index 0→15
    3, 26, 0,                                                       # RIGHT index 16,17,18
    32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13, 36, 11, 30,      # BOT  index 19→33
    8, 23, 10                                                        # LEFT index 34,35,36
]

TOP   = CYLINDER[0:16]   # 5→35
RIGHT = CYLINDER[16:19]  # 3,26,0
BOT   = CYLINDER[19:34]  # 32→30  (déjà dans le bon sens gauche→droite)
LEFT  = CYLINDER[34:37]  # 8,23,10

NEIGHBOR_DIST_MIN = 3
NEIGHBOR_DIST_MAX = 6

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
    line1, line2 = [], []

    for i, num in enumerate(CYLINDER):
        n_str = f"{num:02d}"

        if num == last_number:
            token = colorize(f"[{n_str}]", Color.MAGENTA, Color.BOLD)
        elif num in neighbors:
            token = colorize(f"<{n_str}>", Color.YELLOW, Color.BOLD)
        else:
            token = colorize(f" {n_str} ", Color.DIM)

        if i < 19:
            line1.append(token)
        else:
            line2.append(token)

    return (
        "  " + " ".join(line1) + "\n" +
        "  " + " ".join(line2)
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
    hits      : int       = 0
    last_seen : int       = 999
    signal    : str       = "STOP"
    history   : List[str] = field(default_factory=list)

# ═══════════════════════════════════════════════════════════════
#  SECTION 4 : ZONES
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

    add("Douzaine 1", range(1,  13), "Douzaine", 12, "1→12")
    add("Douzaine 2", range(13, 25), "Douzaine", 12, "13→24")
    add("Douzaine 3", range(25, 37), "Douzaine", 12, "25→36")

    add("Colonne 1",
        {1,4,7,10,13,16,19,22,25,28,31,34}, "Colonne", 12,
        "1 4 7 10 13 16 19 22 25 28 31 34")
    add("Colonne 2",
        {2,5,8,11,14,17,20,23,26,29,32,35}, "Colonne", 12,
        "2 5 8 11 14 17 20 23 26 29 32 35")
    add("Colonne 3",
        {3,6,9,12,15,18,21,24,27,30,33,36}, "Colonne", 12,
        "3 6 9 12 15 18 21 24 27 30 33 36")

    add("Sixain 1",  range(1,  7),  "Sixain", 18, "1→6")
    add("Sixain 2",  range(7,  13), "Sixain", 18, "7→12")
    add("Sixain 3",  range(13, 19), "Sixain", 18, "13→18")
    add("Sixain 4",  range(19, 25), "Sixain", 18, "19→24")
    add("Sixain 5",  range(25, 31), "Sixain", 18, "25→30")
    add("Sixain 6",  range(31, 37), "Sixain", 18, "31→36")

    squares = [
        ({1,2,4,5},    "1 2 4 5"),
        ({2,3,5,6},    "2 3 5 6"),
        ({4,5,7,8},    "4 5 7 8"),
        ({5,6,8,9},    "5 6 8 9"),
        ({7,8,10,11},  "7 8 10 11"),
        ({8,9,11,12},  "8 9 11 12"),
        ({10,11,13,14},"10 11 13 14"),
        ({11,12,14,15},"11 12 14 15"),
        ({13,14,16,17},"13 14 16 17"),
        ({14,15,17,18},"14 15 17 18"),
        ({16,17,19,20},"16 17 19 20"),
        ({17,18,20,21},"17 18 20 21"),
        ({19,20,22,23},"19 20 22 23"),
        ({20,21,23,24},"20 21 23 24"),
        ({22,23,25,26},"22 23 25 26"),
        ({23,24,26,27},"23 24 26 27"),
        ({25,26,28,29},"25 26 28 29"),
        ({26,27,29,30},"26 27 29 30"),
        ({28,29,31,32},"28 29 31 32"),
        ({29,30,32,33},"29 30 32 33"),
        ({31,32,34,35},"31 32 34 35"),
        ({32,33,35,36},"32 33 35 36"),
    ]
    for nums, defi in squares:
        name = "Carré " + defi
        add(name, nums, "Carré", 25, defi)

    return zones

# ═══════════════════════════════════════════════════════════════
#  SECTION 5 : SIGNAL
# ═══════════════════════════════════════════════════════════════

MARGE = 2

SEUILS = {
    "Douzaine": (10, 12),
    "Colonne":  (10, 12),
    "Sixain":   (3,  18),
    "Carré":    (0,  25),
}

def compute_signal(cfg: ZoneConfig, state: ZoneState, total: int) -> str:
    if total == 0 or cfg.category not in SEUILS:
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
#  SECTION 6 : TRACKER
# ═══════════════════════════════════════════════════════════════

class RouletteTracker:
    def __init__(self):
        self.zones               : Dict[str, ZoneConfig] = build_zones()
        self.states              : Dict[str, ZoneState]  = {
            n: ZoneState() for n in self.zones
        }
        self.history             : List[int] = []
        self.freq                : Dict[int, int] = {i: 0 for i in range(37)}
        self.neighbor_dist       : int = NEIGHBOR_DIST_MIN
        # ── NOUVEAU : compteur pertes cylindre ────────────────
        self.cylinder_loss_streak: int = 0

    # ── ajout d'un numéro ─────────────────────────────────────
    def add_number(self, n: int):
        self.history.append(n)
        self.freq[n] += 1
        total = len(self.history)

        # voisins cylindre — reset distance si voisin sort
        if len(self.history) >= 2:
            prev      = self.history[-2]
            neighbors = set(cylinder_neighbors(prev, self.neighbor_dist))
            neighbors.add(prev)   # ← le numéro lui-même compte
            if n in neighbors:
                self.neighbor_dist        = NEIGHBOR_DIST_MIN
                self.cylinder_loss_streak = 0        # ✅ dans les voisins → reset
            else:
                self.neighbor_dist        = min(
                    self.neighbor_dist + 1, NEIGHBOR_DIST_MAX
                )
                self.cylinder_loss_streak += 1       # ❌ hors voisins → +1


        # mise à jour zones
        for name, cfg in self.zones.items():
            st = self.states[name]
            if n in cfg.numbers:
                st.hits     += 1
                st.last_seen = 0
            else:
                st.last_seen += 1
            st.signal = compute_signal(cfg, st, total)

        os.system('cls' if os.name == 'nt' else 'clear')
        self._display(n, total)

    # ── prefill ───────────────────────────────────────────────
    def prefill(self, count: int):
        for _ in range(count):
            self.add_number(random.randint(0, 36))

    # ── stats ─────────────────────────────────────────────────
    def get_stats(self) -> Optional[Dict]:
        if not self.history:
            return None
        chaud = max(self.freq, key=self.freq.get)
        froid = min(self.freq, key=self.freq.get)
        return {
            "total_tirages": len(self.history),
            "numero_chaud" : chaud,
            "numero_froid" : froid,
        }

    # ── numéros GO / ATTENTE (pour cylindre coloré) ───────────
    def _signal_numbers(self) -> tuple[Set[int], Set[int]]:
        go_nums   : Set[int] = set()
        wait_nums : Set[int] = set()
        for name, cfg in self.zones.items():
            sig = self.states[name].signal
            if sig == "GO":
                go_nums   |= cfg.numbers
            elif sig == "ATTENTE":
                wait_nums |= cfg.numbers
        wait_nums -= go_nums
        return go_nums, wait_nums

    # ── affichage principal ───────────────────────────────────
    def _display(self, last: int, total: int):

        go_nums, wait_nums = self._signal_numbers()

        # ── En-tête ───────────────────────────────────────────
        print(colorize(
            "\n  ULTRA ROULETTE PRO — 3 Signaux\n",
            Color.BOLD, Color.CYAN
        ))
        print(colorize(
            f"  Dernier : {last:02d}   |   Total : {total}   "
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
            f"  [XX]=sorti  <XX>=voisin(±{self.neighbor_dist})  "
            f"{'XX':>3}=GO✅  {'XX':>3}=ATTENTE⏳",
            Color.DIM
        ))

        # ── Compteur pertes cylindre ──────────────────────────
        streak = self.cylinder_loss_streak
        if streak == 0:
            streak_str = colorize(
                f"  🟢 Voisins actifs — pertes consécutives : {streak}",
                Color.GREEN
            )
        elif streak <= 3:
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
        # ──────────────────────────────────────────────────────

        print()
        print(display_cylinder_full(last, self.neighbor_dist, go_nums, wait_nums))
        print()

        # ══════════════════════════════════════════════════════
        #  ZONES GO
        # ══════════════════════════════════════════════════════
        self._display_signal_block("GO")

        # ══════════════════════════════════════════════════════
        #  ZONES ATTENTE
        # ══════════════════════════════════════════════════════
        self._display_signal_block("ATTENTE")

        # ══════════════════════════════════════════════════════
        #  TABLEAU COMPLET — DEBUG
        # ══════════════════════════════════════════════════════
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
            f"{'Hits':>5}  {'Absent':>6}",
            Color.BOLD
        ))

        for name, cfg, st in entries:
            hits_str   = colorize(f"{st.hits:>5}", Color.CYAN)
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

        categories = ["Douzaine", "Colonne", "Sixain", "Carré"]

        for cat in categories:
            print(colorize(
                f"\n  ▸ {cat.upper()}",
                Color.BOLD, Color.DIM
            ))
            print(colorize(
                f"  {'Zone':<22} {'Définition':<36} "
                f"{'Hits':>5}  {'Absent':>8}  Signal",
                Color.DIM
            ))
            print(colorize(f"  {sep}", Color.DIM))

            for name, cfg in self.zones.items():
                if cfg.category != cat:
                    continue
                st = self.states[name]

                hits_str = colorize(f"{st.hits:>5}", Color.CYAN)

                if st.last_seen >= cfg.wait:
                    ac = Color.RED
                elif st.last_seen >= cfg.wait // 2:
                    ac = Color.YELLOW
                else:
                    ac = Color.DIM
                absent_str = colorize(f"abs:{st.last_seen:>3}", ac)

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
    print(colorize(f"""
  ┌────────────────────────────────────────────────────────────┐
  │  COMMANDES                                                 │
  │  0-36  → entrer un numéro sorti                           │
  │  s     → statistiques globales                            │
  │  d     → préfill 37 tirages aléatoires                    │
  │  h     → afficher cette aide                              │
  │  q     → quitter                                          │
  ├────────────────────────────────────────────────────────────┤
  │  SIGNAUX (marge d'approche : ±{MARGE})                         │
  │  Douzaine/Colonne : GO si hits ≤ 10 ET absent ≥ 12       │
  │  Sixain           : GO si hits ≤  3 ET absent ≥ 18       │
  │  Carré            : GO si hits ≤  0 ET absent ≥ 25       │
  │  ATTENTE : dans la marge de {MARGE} unités des seuils GO       │
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
                    "\n  Numéro (0-36) / s / d / h / q : ",
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
            elif val == 's':
                stats = tracker.get_stats()
                if stats:
                    print(colorize(
                        f"\n  Total : {stats['total_tirages']}"
                        f"  |  Chaud : {stats['numero_chaud']}"
                        f"  |  Froid : {stats['numero_froid']}\n",
                        Color.CYAN
                    ))
                else:
                    print(colorize("  Aucun tirage.\n", Color.DIM))
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
