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
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional, List, Dict, Tuple

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
    """
    Applique une ou plusieurs couleurs ANSI à un texte.
    Usage : colorize("texte", Color.BOLD, Color.GREEN)
    """
    codes  = "".join(a for a in args if a.startswith('\033'))
    text   = "".join(a for a in args if not a.startswith('\033'))
    return f"{codes}{text}{Color.END}"

# ═══════════════════════════════════════════════════════════════
#  SECTION 2 : STRUCTURES DE DONNÉES
# ═══════════════════════════════════════════════════════════════

@dataclass
class ZoneConfig:
    """
    Configuration statique d'une zone de jeu.

    Attributs :
    ───────────
    name        : Nom affiché (ex: "Douzaine 1")
    category    : Famille (Tiers / Sixain / Carré)
    numbers     : Ensemble des numéros couverts (frozenset = immuable + O(1))
    sigma_limit : Seuil de sous-représentation (hits ≤ sigma_limit → froide)
    wait        : Gap minimum pour signal GO (tours d'absence consécutifs)
    pre_alert   : Marge avant GO pour signal ATTENTE (wait - pre_alert)
    """
    name        : str
    category    : str
    numbers     : frozenset
    sigma_limit : int
    wait        : int
    pre_alert   : int = 3   # Tours avant le seuil wait → déclenche ATTENTE


@dataclass
class ZoneResult:
    """
    Résultat d'analyse d'une zone pour un tour donné.

    Attributs :
    ───────────
    name     : Nom de la zone
    category : Famille de la zone
    hits     : Nombre de sorties dans les 37 derniers tirages
    gap      : Tours d'absence consécutifs
    signal   : Texte colorisé du signal (GO / ATTENTE / STOP)
    score    : Score de priorité pour le tri (plus haut = plus prioritaire)
    """
    name     : str
    category : str
    hits     : int
    gap      : int
    signal   : str
    score    : float

# ═══════════════════════════════════════════════════════════════
#  SECTION 3 : MOTEUR PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class UltraRoulettePro:
    """
    Moteur d'analyse statistique pour la roulette européenne.

    Fenêtre d'observation : 37 derniers tirages (1 cycle théorique).
    Zones analysées       : 21 (3 douzaines + 3 colonnes + 6 sixains + 9 carrés)
    Signaux               : 3 (GO / ATTENTE / STOP)
    """

    CYCLE = 37   # Taille de la fenêtre glissante (roulette 0-36)

    def __init__(self):
        # Historique complet de la session
        self.history : List[int] = []

        # Fenêtre glissante auto-rotative (maxlen=37 → O(1) append/pop)
        self._recent : deque = deque(maxlen=self.CYCLE)

        # Dictionnaire {nom_zone : ZoneConfig}
        self.zones : Dict[str, ZoneConfig] = {}

        # Construction des 21 zones au démarrage
        self._build_zones()

    # ───────────────────────────────────────────────────────────
    #  3.1 CONSTRUCTION DES ZONES
    # ───────────────────────────────────────────────────────────

    def _build_zones(self):
        """
        Construit les 21 zones de jeu et les stocke dans self.zones.

        Paramètres par catégorie :
        ──────────────────────────
        Tiers   (12 nums) : sigma=6, wait=10, pre_alert=3
        Sixain  ( 6 nums) : sigma=1, wait=22, pre_alert=3
        Carré   ( 4 nums) : sigma=0, wait=34, pre_alert=3
        """

        # ── DOUZAINES (3 zones × 12 numéros) ──────────────────
        douzaines = [
            ("Douzaine 1", range(1, 13)),    # 1→12
            ("Douzaine 2", range(13, 25)),   # 13→24
            ("Douzaine 3", range(25, 37)),   # 25→36
        ]
        for name, rng in douzaines:
            self.zones[name] = ZoneConfig(
                name        = name,
                category    = "Tiers",
                numbers     = frozenset(rng),
                sigma_limit = 6,
                wait        = 10,
                pre_alert   = 3
            )

        # ── COLONNES (3 zones × 12 numéros) ───────────────────
        colonnes = [
            ("Colonne 1", range(1, 37, 3)),   # 1,4,7,...,34
            ("Colonne 2", range(2, 37, 3)),   # 2,5,8,...,35
            ("Colonne 3", range(3, 37, 3)),   # 3,6,9,...,36
        ]
        for name, rng in colonnes:
            self.zones[name] = ZoneConfig(
                name        = name,
                category    = "Tiers",
                numbers     = frozenset(rng),
                sigma_limit = 6,
                wait        = 10,
                pre_alert   = 3
            )

        # ── SIXAINS (6 zones × 6 numéros) ─────────────────────
        for i in range(6):
            start = i * 6 + 1              # 1, 7, 13, 19, 25, 31
            end   = start + 6              # 7, 13, 19, 25, 31, 37
            name  = f"Sixain {i+1}"
            self.zones[name] = ZoneConfig(
                name        = name,
                category    = "Sixain",
                numbers     = frozenset(range(start, end)),
                sigma_limit = 1,
                wait        = 22,
                pre_alert   = 3
            )

        # ── CARRÉS (9 zones × 4 numéros) ──────────────────────
        # Un carré couvre 4 numéros adjacents sur le tableau :
        # n, n+1, n+3, n+4  (disposition tableau roulette 3 colonnes)
        carres_base = [1,2,3,4,5,6,7,8,9,
                       10,11,12,13,14,15,
                       16,17,18,19,20,21,
                       22,23,24,25,26,27]
        carre_idx = 0
        for n in [1, 4, 7, 10, 13, 16, 19, 22, 25]:
            carre_idx += 1
            name = f"Carré {carre_idx}"
            self.zones[name] = ZoneConfig(
                name        = name,
                category    = "Carré",
                numbers     = frozenset([n, n+1, n+3, n+4]),
                sigma_limit = 0,
                wait        = 34,
                pre_alert   = 3
            )

    # ───────────────────────────────────────────────────────────
    #  3.2 ENREGISTREMENT D'UN TIRAGE
    # ───────────────────────────────────────────────────────────

    def add_number(self, n: int):
        """
        Enregistre un nouveau numéro tiré.

        Paramètre :
        ───────────
        n : int → numéro tiré (0-36)

        Actions :
        ─────────
        1. Ajout dans history[]    (liste complète session)
        2. Ajout dans _recent      (fenêtre glissante 37 tours)
        3. Rafraîchissement du dashboard
        """
        self.history.append(n)
        self._recent.append(n)
        self._display_dashboard()

    # ───────────────────────────────────────────────────────────
    #  3.3 CALCUL DU GAP (ABSENCE CONSÉCUTIVE)
    # ───────────────────────────────────────────────────────────

    def _compute_gap(self, numbers: frozenset) -> int:
        """
        Calcule le nombre de tours consécutifs depuis la dernière
        sortie d'un numéro de la zone, en remontant l'historique.

        Paramètre :
        ───────────
        numbers : frozenset → numéros de la zone

        Retour :
        ────────
        int → tours d'absence (0 = sorti au dernier tirage)

        Algorithme :
        ────────────
        Parcourt history[] à l'envers.
        Dès qu'un numéro de la zone est trouvé → arrêt.
        Limité à CYCLE (37) tours max pour cohérence fenêtre.
        """
        gap   = 0
        limit = min(len(self.history), self.CYCLE)

        for i in range(1, limit + 1):
            if self.history[-i] in numbers:
                break
            gap += 1

        return gap

    # ───────────────────────────────────────────────────────────
    #  3.4 GÉNÉRATION DU SIGNAL (3 SIGNAUX)
    # ───────────────────────────────────────────────────────────

    def _get_signal(self, hits: int, gap: int, cfg: ZoneConfig) -> Optional[ZoneResult]:
        """
        Génère le signal pour une zone selon hits et gap.

        Paramètres :
        ────────────
        hits : int       → sorties dans les 37 derniers tours
        gap  : int       → tours d'absence consécutifs
        cfg  : ZoneConfig → configuration de la zone

        Logique des 3 signaux :
        ───────────────────────
        ┌──────────┬───────────────────────────────────────────────┐
        │ Signal   │ Condition                                     │
        ├──────────┼───────────────────────────────────────────────┤
        │ ✅ GO    │ hits ≤ sigma  ET  gap ≥ wait                 │
        │ ⏳ ATTEND│ hits ≤ sigma  ET  gap ≥ (wait - pre_alert)   │
        │ 🔴 STOP  │ hits ≤ sigma  ET  gap < (wait - pre_alert)   │
        │          │ OU  gap ≥ wait  ET  hits > sigma (chaud/abs) │
        │ ✖ None   │ Zone normale → ignorée                       │
        └──────────┴───────────────────────────────────────────────┘

        Score de priorité (tri décroissant) :
        ──────────────────────────────────────
        GO      → score élevé  (affiché en premier)
        ATTENTE → score moyen
        STOP    → score négatif (affiché en dernier)
        """

        is_cold     = hits <= cfg.sigma_limit                    # Zone froide
        is_ready    = gap  >= cfg.wait                           # Gap suffisant pour GO
        pre_ready   = gap  >= (cfg.wait - cfg.pre_alert)         # Gap presque suffisant
        is_hot_risk = (not is_cold) and is_ready                 # Chaude mais absente

        # ── ✅ GO ──────────────────────────────────────────────
        if is_cold and is_ready:
            score = float((cfg.sigma_limit - hits + 1) * 10 + gap)
            label = colorize(
                f"[ ✅ GO      +{gap}t vide ]",
                Color.BOLD, Color.GREEN
            )
            return ZoneResult(cfg.name, cfg.category, hits, gap, label, score)

        # ── ⏳ ATTENTE ─────────────────────────────────────────
        elif is_cold and pre_ready:
            manque = cfg.wait - gap                              # Tours restants
            score  = float((cfg.sigma_limit - hits + 1) * 5 + gap)
            label  = colorize(
                f"[ ⏳ ATTENTE -{manque}t restants ]",
                Color.BOLD, Color.YELLOW
            )
            return ZoneResult(cfg.name, cfg.category, hits, gap, label, score)

        # ── 🔴 STOP ───────────────────────────────────────────
        elif is_cold or is_hot_risk:
            raison = "PRÉCOCE" if is_cold else "CHAUD/RISQUE"
            score  = float(hits * -1)
            label  = colorize(
                f"[ 🔴 STOP    {raison:<12} ]",
                Color.BOLD, Color.RED
            )
            return ZoneResult(cfg.name, cfg.category, hits, gap, label, score)

        # ── ✖ Zone normale → pas de signal ────────────────────
        return None

    # ───────────────────────────────────────────────────────────
    #  3.5 ANALYSE DE TOUTES LES ZONES
    # ───────────────────────────────────────────────────────────

    def _analyze_zones(self) -> List[ZoneResult]:
        """
        Analyse les 21 zones et retourne les résultats triés par score.

        Retour :
        ────────
        List[ZoneResult] → zones avec signal, triées score décroissant.
        Les zones sans signal (normales) sont exclues.
        """
        results = []
        recent_list = list(self._recent)   # Conversion pour comptage

        for cfg in self.zones.values():
            # Hits : occurrences dans la fenêtre des 37 derniers tours
            hits = sum(1 for n in recent_list if n in cfg.numbers)

            # Gap : tours d'absence consécutifs
            gap  = self._compute_gap(cfg.numbers)

            # Génération du signal
            result = self._get_signal(hits, gap, cfg)

            if result is not None:
                results.append(result)

        # Tri décroissant par score → GO en premier, STOP en dernier
        results.sort(key=lambda r: r.score, reverse=True)
        return results

    # ───────────────────────────────────────────────────────────
    #  3.6 STATISTIQUES GLOBALES
    # ───────────────────────────────────────────────────────────

    def get_stats(self) -> Optional[Dict]:
        """
        Calcule les statistiques globales de la session.

        Retour :
        ────────
        Dict avec :
          - total_tirages : nombre total de numéros saisis
          - frequences    : {numéro: nb_sorties} pour tous les numéros
          - numero_chaud  : numéro sorti le plus souvent
          - numero_froid  : numéro sorti le moins souvent (parmi sortis)
        Retourne None si aucun tirage enregistré.
        """
        if not self.history:
            return None

        freq = {}
        for n in range(37):
            freq[n] = self.history.count(n)

        sortis = {k: v for k, v in freq.items() if v > 0}

        return {
            "total_tirages" : len(self.history),
            "frequences"    : freq,
            "numero_chaud"  : max(sortis, key=sortis.get) if sortis else "N/A",
            "numero_froid"  : min(sortis, key=sortis.get) if sortis else "N/A",
        }

    # ───────────────────────────────────────────────────────────
    #  3.7 PRÉ-REMPLISSAGE (MODE DÉMO)
    # ───────────────────────────────────────────────────────────

    def prefill(self, n: int = 20):
        """
        Pré-remplit l'historique avec n tirages aléatoires.
        Utile pour démarrer avec un historique non-vide.

        Paramètre :
        ───────────
        n : int → nombre de tirages à générer (défaut: 20)
        """
        for _ in range(n):
            num = random.randint(0, 36)
            self.history.append(num)
            self._recent.append(num)

    # ───────────────────────────────────────────────────────────
    #  3.8 AFFICHAGE DU DASHBOARD
    # ───────────────────────────────────────────────────────────

    def _display_dashboard(self):
        """
        Rafraîchit et affiche le dashboard complet dans le terminal.

        Structure :
        ───────────
        1. Header       (titre + numéro du tour + dernier tirage)
        2. Historique   (15 derniers numéros)
        3. Tableau zones(nom | catégorie | hits | gap | signal)
        4. Footer       (compteur des 3 types de signaux)
        """
        os.system('cls' if os.name == 'nt' else 'clear')

        total   = len(self.history)
        dernier = self.history[-1] if self.history else "–"

        # ── HEADER ────────────────────────────────────────────
        print(colorize(
            f"\n  ╔══════════════════════════════════════════════════╗",
            Color.CYAN, Color.BOLD
        ))
        print(colorize(
            f"  ║       ULTRA ROULETTE PRO  ·  3 SIGNAUX          ║",
            Color.CYAN, Color.BOLD
        ))
        print(colorize(
            f"  ╚══════════════════════════════════════════════════╝",
            Color.CYAN, Color.BOLD
        ))
        print(colorize(
            f"\n  Tour : {total:>4}  |  Dernier numéro : {dernier}",
            Color.BOLD
        ))

        # ── HISTORIQUE (15 derniers) ───────────────────────────
        recents_display = list(self.history[-15:])
        hist_str = "  ".join(f"{n:>2}" for n in recents_display)
        print(colorize(f"\n  Historique (15) :  {hist_str}", Color.DIM))
        print(colorize("  " + "─" * 60, Color.DIM))

        # ── ANALYSE DES ZONES ─────────────────────────────────
        if len(self.history) < 5:
            print(colorize(
                "\n  ⏳ En attente de données (minimum 5 tirages)...\n",
                Color.DIM
            ))
            return

        results = self._analyze_zones()

        if not results:
            print(colorize(
                "\n  ✔ Aucune anomalie détectée. Zones équilibrées.\n",
                Color.GREEN
            ))
            return

        # ── TABLEAU ───────────────────────────────────────────
        header = colorize(
            f"\n  {'ZONE':<14} {'CAT':<8} {'SORT/37':>7}  {'VIDE':>5}    SIGNAL",
            Color.BOLD
        )
        print(header)
        print(colorize("  " + "─" * 60, Color.DIM))

        # Compteurs pour le footer
        count_go      = 0
        count_attente = 0
        count_stop    = 0

        for r in results:
            # Détection du type de signal pour le compteur
            if "GO"      in r.signal: count_go      += 1
            elif "ATTENTE" in r.signal: count_attente += 1
            elif "STOP"  in r.signal: count_stop    += 1

            ligne = (
                f"  {r.name:<14} "
                f"{r.category:<8} "
                f"{r.hits:>6}/37  "
                f"{r.gap:>4}t    "
                f"{r.signal}"
            )
            print(ligne)

        # ── FOOTER ────────────────────────────────────────────
        print(colorize("\n  " + "─" * 60, Color.DIM))
        print(
            colorize(f"  ✅ GO : {count_go}", Color.GREEN, Color.BOLD) +
            colorize(f"   |   ⏳ ATTENTE : {count_attente}", Color.YELLOW, Color.BOLD) +
            colorize(f"   |   🔴 STOP : {count_stop}\n", Color.RED, Color.BOLD)
        )

# ═══════════════════════════════════════════════════════════════
#  SECTION 4 : INTERFACE UTILISATEUR
# ═══════════════════════════════════════════════════════════════

def print_help():
    """Affiche le menu d'aide des commandes disponibles."""
    print(colorize("\n  ┌─ COMMANDES ─────────────────────────────┐", Color.CYAN))
    print(colorize("  │  0-36   → Saisir le numéro tiré         │", Color.CYAN))
    print(colorize("  │  s      → Statistiques globales          │", Color.CYAN))
    print(colorize("  │  d      → Mode démo (20 tirages auto)    │", Color.CYAN))
    print(colorize("  │  h      → Afficher cette aide            │", Color.CYAN))
    print(colorize("  │  q      → Quitter                        │", Color.CYAN))
    print(colorize("  └─────────────────────────────────────────┘\n", Color.CYAN))


def main():
    """
    Boucle principale de l'interface utilisateur.

    Flux :
    ──────
    1. Initialisation du tracker
    2. Affichage du menu d'accueil
    3. Boucle de saisie infinie jusqu'à 'q' ou Ctrl+C
    4. Dispatch selon la commande saisie
    """
    tracker = UltraRoulettePro()

    # ── Écran d'accueil ───────────────────────────────────────
    os.system('cls' if os.name == 'nt' else 'clear')
    print(colorize("\n  ULTRA ROULETTE PRO — 3 Signaux\n", Color.BOLD, Color.CYAN))
    print(colorize(
        "  ⚠ Outil statistique uniquement. La roulette est un jeu de hasard.\n",
        Color.YELLOW
    ))
    print_help()

    # ── Boucle principale ─────────────────────────────────────
    while True:
        try:
            val = input(
                colorize("  Numéro (0-36) / s / d / h / q : ", Color.BOLD)
            ).strip().lower()

            # ── Quitter ───────────────────────────────────────
            if val == 'q':
                print(colorize("\n  Session terminée. Bonne chance !\n", Color.BOLD))
                break

            # ── Aide ──────────────────────────────────────────
            elif val == 'h':
                print_help()

            # ── Statistiques ──────────────────────────────────
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
                    print(colorize("  Aucun tirage enregistré.\n", Color.DIM))

            # ── Mode Démo ─────────────────────────────────────
            elif val == 'd':
                tracker.prefill(20)
                print(colorize(
                    "  ✔ 20 tirages aléatoires injectés.\n",
                    Color.GREEN
                ))
                tracker._display_dashboard()

            # ── Saisie d'un numéro ────────────────────────────
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
            # Saisie non numérique
            print(colorize("  ⚠ Entrez un chiffre (0-36) ou une commande.\n", Color.RED))

        except KeyboardInterrupt:
            # Ctrl+C : sortie propre
            print(colorize("\n\n  Interruption. Au revoir !\n", Color.BOLD))
            break


# ═══════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
