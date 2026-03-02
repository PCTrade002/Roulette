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
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Set

# ═══════════════════════════════════════════════════════════════
#  FLAG DEBUG
# ═══════════════════════════════════════════════════════════════

DEBUG = True

# ═══════════════════════════════════════════════════════════════
#  SECTION 0 : SIGMA CONFIG (NOMBRE D'OR)
# ═══════════════════════════════════════════════════════════════

SIGMA_BASE     = 1.618
SIGMA_REF_NUMS = 12

def compute_sigma_cfg(nb_numbers: int) -> float:
    """σ cfg = 1.618 × (12 / nb_numéros)"""
    return SIGMA_BASE * (SIGMA_REF_NUMS / nb_numbers)

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
    0, 32, 15, 19, 4, 21, 2, 25, 17, 34, 6, 27, 13,
    36, 11, 30, 8, 23, 10, 5, 24, 16, 33, 1, 20, 14,
    31, 9, 22, 18, 29, 7, 28, 12, 35, 3, 26
]

NEIGHBOR_DIST_MIN = 3
NEIGHBOR_DIST_MAX = 6

def cylinder_distance(n1: int, n2: int) -> int:
    idx1 = CYLINDER.index(n1)
    idx2 = CYLINDER.index(n2)
    size = len(CYLINDER)
    diff = abs(idx1 - idx2)
    return min(diff, size - diff)

def cylinder_neighbors(n: int, distance: int) -> List[int]:
    idx      = CYLINDER.index(n)
    size     = len(CYLINDER)
    neighbors = []
    for delta in range(-distance, distance + 1):
        if delta == 0:
            continue
        neighbors.append(CYLINDER[(idx + delta) % size])
    return neighbors

# ═══════════════════════════════════════════════════════════════
#  SECTION 3 : DATACLASSES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ZoneConfig:
    name      : str
    numbers   : Set[int]
    category  : str          # "Tiers" | "Sixain" | "Carré" | "Voisins"
    wait      : int          # seuil last_seen pour déclencher GO
    sigma_cfg : float        # seuil σ calculé via nombre d'or

@dataclass
class ZoneState:
    hits      : int   = 0
    last_seen : int   = 999
    signal    : str   = "STOP"   # "GO" | "ATTENTE" | "STOP"
    history   : List[str] = field(default_factory=list)

# ═══════════════════════════════════════════════════════════════
#  SECTION 4 : ZONES
# ═══════════════════════════════════════════════════════════════

def build_zones() -> Dict[str, ZoneConfig]:
    zones: Dict[str, ZoneConfig] = {}

    # ── Tiers du cylindre (12 numéros) ────────────────────────
    tiers_definitions = {
        "Tiers 0–9–22":   {5,24,16,33,1,20,14,31,9,22,18,29},
        "Tiers 10–23–8":  {10,23,8,30,11,36,13,27,6,34,17,25},
        "Tiers Orphelins": {1,20,14,31,9,17,34,6},
        "Tiers Voisins 0": {22,18,29,7,28,12,35,3,26,0,32,15},
    }
    for name, nums in tiers_definitions.items():
        zones[name] = ZoneConfig(
            name      = name,
            numbers   = nums,
            category  = "Tiers",
            wait      = 12,
            sigma_cfg = compute_sigma_cfg(len(nums)),
        )

    # ── Sixains (6 numéros) ────────────────────────────────────
    sixains = [
        ("Sixain 1-6",   {1,2,3,4,5,6}),
        ("Sixain 7-12",  {7,8,9,10,11,12}),
        ("Sixain 13-18", {13,14,15,16,17,18}),
        ("Sixain 19-24", {19,20,21,22,23,24}),
        ("Sixain 25-30", {25,26,27,28,29,30}),
        ("Sixain 31-36", {31,32,33,34,35,36}),
    ]
    for name, nums in sixains:
        zones[name] = ZoneConfig(
            name      = name,
            numbers   = nums,
            category  = "Sixain",
            wait      = 18,
            sigma_cfg = compute_sigma_cfg(len(nums)),
        )

    # ── Carrés (4 numéros) ────────────────────────────────────
    squares = [
        ("Carré 1-5",   {1,2,4,5}),
        ("Carré 2-6",   {2,3,5,6}),
        ("Carré 4-8",   {4,5,7,8}),
        ("Carré 5-9",   {5,6,8,9}),
        ("Carré 7-11",  {7,8,10,11}),
        ("Carré 8-12",  {8,9,11,12}),
        ("Carré 10-14", {10,11,13,14}),
        ("Carré 11-15", {11,12,14,15}),
        ("Carré 13-17", {13,14,16,17}),
        ("Carré 14-18", {14,15,17,18}),
        ("Carré 16-20", {16,17,19,20}),
        ("Carré 17-21", {17,18,20,21}),
        ("Carré 19-23", {19,20,22,23}),
        ("Carré 20-24", {20,21,23,24}),
        ("Carré 22-26", {22,23,25,26}),
        ("Carré 23-27", {23,24,26,27}),
        ("Carré 25-29", {25,26,28,29}),
        ("Carré 26-30", {26,27,29,30}),
        ("Carré 28-32", {28,29,31,32}),
        ("Carré 29-33", {29,30,32,33}),
        ("Carré 31-35", {31,32,34,35}),
        ("Carré 32-36", {32,33,35,36}),
    ]
    for name, nums in squares:
        zones[name] = ZoneConfig(
            name      = name,
            numbers   = nums,
            category  = "Carré",
            wait      = 25,
            sigma_cfg = compute_sigma_cfg(len(nums)),
        )

    return zones

# ═══════════════════════════════════════════════════════════════
#  SECTION 5 : TRACKER
# ═══════════════════════════════════════════════════════════════

class RouletteTracker:

    WINDOW = 37

    def __init__(self):
        self.history : List[int]             = []
        self.zones   : Dict[str, ZoneConfig] = build_zones()
        self.states  : Dict[str, ZoneState]  = {
            name: ZoneState() for name in self.zones
        }
        # Voisins cylindre
        self.neighbor_dist    : int = NEIGHBOR_DIST_MIN
        self.neighbor_last    : int = 999
        self.neighbor_numbers : Set[int] = set()

    # ── Sigma théorique binomial ───────────────────────────────
    @staticmethod
    def compute_sigma_theo(nb_numbers: int, n: int = 37) -> float:
        p = nb_numbers / 37
        return math.sqrt(n * p * (1 - p))

    # ── Mise à jour d'une zone après tirage ───────────────────
    def _update_zone(self, name: str, number: int):
        cfg   = self.zones[name]
        state = self.states[name]

        # Fenêtre glissante
        window = self.history[-self.WINDOW:]
        state.hits = sum(1 for x in window if x in cfg.numbers)

        # last_seen
        state.last_seen = 999
        for i, x in enumerate(reversed(self.history)):
            if x in cfg.numbers:
                state.last_seen = i
                break

        # σ mesuré
        sigma_theo   = self.compute_sigma_theo(len(cfg.numbers))
        hits_attendus = len(cfg.numbers)
        sigma_mesure  = (hits_attendus - state.hits) / sigma_theo if sigma_theo > 0 else 0.0

        # Signal
        if sigma_mesure >= cfg.sigma_cfg:
            state.signal = "GO"
        elif sigma_mesure >= cfg.sigma_cfg * 0.5:
            state.signal = "ATTENTE"
        else:
            state.signal = "STOP"

        state.history.append(state.signal)

    # ── Mise à jour voisins cylindre ──────────────────────────
    def _update_neighbors(self, number: int):
        # Reset distance si un voisin sort
        if number in self.neighbor_numbers:
            self.neighbor_dist = NEIGHBOR_DIST_MIN
            self.neighbor_last = 0
        else:
            if self.neighbor_last < 999:
                self.neighbor_last += 1
            if self.neighbor_last > NEIGHBOR_DIST_MAX:
                self.neighbor_dist = min(
                    self.neighbor_dist + 1, NEIGHBOR_DIST_MAX
                )

        self.neighbor_numbers = set(
            cylinder_neighbors(number, self.neighbor_dist)
        )

    # ── Ajout d'un numéro ─────────────────────────────────────
    def add_number(self, number: int):
        self.history.append(number)
        self._update_neighbors(number)
        for name in self.zones:
            self._update_zone(name, number)
        self._print_result(number)
        if DEBUG:
            self._print_debug_stats()

    # ── Préfill aléatoire ─────────────────────────────────────
    def prefill(self, n: int = 37):
        print(colorize(f"\n  Préfill de {n} tirages aléatoires...\n", Color.DIM))
        for _ in range(n):
            self.add_number(random.randint(0, 36))

    # ── Statistiques globales ─────────────────────────────────
    def get_stats(self) -> Optional[Dict]:
        if not self.history:
            return None
        freq = {}
        for n in self.history:
            freq[n] = freq.get(n, 0) + 1
        return {
            "total_tirages" : len(self.history),
            "numero_chaud"  : max(freq, key=freq.get),
            "numero_froid"  : min(freq, key=freq.get),
        }

    # ── Affichage résultat principal ──────────────────────────
    def _print_result(self, number: int):
        os.system('cls' if os.name == 'nt' else 'clear')
        print(colorize(
            f"\n  ▶ Numéro sorti : {number}   "
            f"(tour {len(self.history)})\n",
            Color.BOLD, Color.MAGENTA
        ))

        # Meilleures zones GO
        go_zones = [
            (name, self.states[name])
            for name, cfg in self.zones.items()
            if self.states[name].signal == "GO"
        ]
        if go_zones:
            print(colorize("  ✅ ZONES GO :", Color.GREEN, Color.BOLD))
            for name, st in go_zones:
                cfg = self.zones[name]
                nums = sorted(cfg.numbers)
                print(colorize(
                    f"     {name:<22}  hits {st.hits}/37  "
                    f"last/wait {st.last_seen}/{cfg.wait}  "
                    f"[{' '.join(str(x) for x in nums)}]",
                    Color.GREEN
                ))
        else:
            print(colorize("  Aucune zone GO pour ce tour.\n", Color.DIM))

        # Voisins cylindre
        print(colorize(
            f"\n  🎯 Voisins cylindre (±{self.neighbor_dist}) : "
            f"{sorted(self.neighbor_numbers)}",
            Color.CYAN
        ))
        print()

    # ── Affichage DEBUG ───────────────────────────────────────
    def _print_debug_stats(self):
        sep     = "─" * 82
        sep_cat = "╌" * 82

        print(colorize(
            f"\n  🐛  DEBUG — Stats détaillées toutes zones "
            f"(tour {len(self.history)})\n",
            Color.BOLD, Color.YELLOW
        ))
        print(colorize(
            f"  {'ZONE':<22} {'DÉFINITION':<30} {'hits/37':>8}  "
            f"{'σ mes':>7}  {'last/wait':>10}  SIGNAL",
            Color.BOLD
        ))
        print(f"  {sep}")

        current_cat = None

        for name, cfg in self.zones.items():
            state = self.states[name]

            # ── Séparateur + titre de catégorie ───────────────
            if cfg.category != current_cat:
                if current_cat is not None:
                    print(colorize(f"  {sep_cat}", Color.DIM))
                current_cat = cfg.category
                print(colorize(
                    f"  ▸ {cfg.category.upper()}",
                    Color.BOLD, Color.CYAN
                ))

            # ── Calculs σ ─────────────────────────────────────
            sigma_theo    = self.compute_sigma_theo(len(cfg.numbers))
            hits_attendus = len(cfg.numbers)
            sigma_mesure  = (
                (hits_attendus - state.hits) / sigma_theo
                if sigma_theo > 0 else 0.0
            )

            # ── Couleur selon σ ───────────────────────────────
            if sigma_mesure >= cfg.sigma_cfg:
                hit_color = Color.GREEN
            elif sigma_mesure >= cfg.sigma_cfg * 0.5:
                hit_color = Color.YELLOW
            else:
                hit_color = Color.RED

            # ── Signal ────────────────────────────────────────
            sig = state.signal
            if sig == "GO":
                sig_color = Color.GREEN
                sig_label = "✅ GO"
            elif sig == "ATTENTE":
                sig_color = Color.YELLOW
                sig_label = "⏳ ATTENTE"
            else:
                sig_color = Color.RED
                sig_label = "🔴 STOP"

            # ── Définition lisible ────────────────────────────
            nums_sorted = sorted(cfg.numbers)
            if cfg.category in ("Carré", "Sixain"):
                definition = "[" + " ".join(str(x) for x in nums_sorted) + "]"
            elif cfg.category == "Tiers":
                definition = (
                    "sect. " +
                    " ".join(str(x) for x in nums_sorted[:4]) + "…"
                )
            else:
                definition = " ".join(str(x) for x in nums_sorted[:6])
                if len(nums_sorted) > 6:
                    definition += "…"

            # ── last / wait ───────────────────────────────────
            ls = state.last_seen if state.last_seen < 999 else "—"

            hits_str     = colorize(f"{state.hits:>3}/37",         hit_color)
            smes_str     = colorize(f"{sigma_mesure:>+7.2f}",      hit_color)
            lastwait_str = colorize(f"{str(ls):>3}/{cfg.wait:<3}", Color.DIM)
            sig_str      = colorize(sig_label, sig_color, Color.BOLD)

            print(
                f"  {name:<22} {definition:<30} "
                f"{hits_str:>14}  {smes_str}  "
                f"{lastwait_str:>16}  {sig_str}"
            )

        print(f"  {sep}")
        print(colorize(
            f"  σ mes = (hits_attendus - hits_obs) / σ théo  |  "
            f"GO si σ mes ≥ {SIGMA_BASE} × 12/nb_nums  |  "
            f"last/wait = tours depuis dernier hit / seuil",
            Color.DIM
        ))

# ═══════════════════════════════════════════════════════════════
#  SECTION 6 : AIDE
# ═══════════════════════════════════════════════════════════════

def print_help():
    print(colorize("""
  ┌────────────────────────────────────────────────────────────┐
  │  COMMANDES                                                 │
  │  0-36  → entrer un numéro sorti                           │
  │  s     → statistiques globales                            │
  │  d     → préfill 37 tirages aléatoires                    │
  │  h     → afficher cette aide                              │
  │  q     → quitter                                          │
  ├────────────────────────────────────────────────────────────┤
  │  SIGNAUX                                                   │
  │  ✅ GO      σ mesuré ≥ σ cfg  → zone en retard marqué    │
  │  ⏳ ATTENTE σ mesuré ≥ σ/2   → zone légèrement en retard │
  │  🔴 STOP    σ mesuré < σ/2   → zone dans la norme        │
  ├────────────────────────────────────────────────────────────┤
  │  VOISINS CYLINDRE                                          │
  │  Démarre à ±3, monte jusqu'à ±6 sans hit                  │
  │  Reset à ±3 dès qu'un voisin sort                         │
  ├────────────────────────────────────────────────────────────┤
  │  DEBUG                                                     │
  │  Mettre DEBUG = True pour voir σ mesuré et toutes zones   │
  └────────────────────────────────────────────────────────────┘
""", Color.DIM))

# ═══════════════════════════════════════════════════════════════
#  SECTION 7 : BOUCLE PRINCIPALE
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
                    "  Numéro (0-36) / s / d / h / q : ",
                    Color.BOLD
                )
            ).strip().lower()

            if val == 'q':
                print(colorize(
                    "\n  Session terminée. Bonne chance !\n",
                    Color.BOLD
                ))
                break
            elif val == 'h':
                print_help()
            elif val == 's':
                stats = tracker.get_stats()
                if stats:
                    print(colorize(
                        f"\n  Total tirages : {stats['total_tirages']}"
                        f"  |  Chaud : {stats['numero_chaud']}"
                        f"  |  Froid : {stats['numero_froid']}\n",
                        Color.CYAN
                    ))
                else:
                    print(colorize(
                        "  Aucun tirage enregistré.\n", Color.DIM
                    ))
            elif val == 'd':
                tracker.prefill(37)
            else:
                n = int(val)
                if 0 <= n <= 36:
                    tracker.add_number(n)
                else:
                    print(colorize(
                        "  ⚠ Numéro entre 0 et 36 uniquement.\n",
                        Color.RED
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

# ═══════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
