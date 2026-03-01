"""
╔══════════════════════════════════════════════════════════════╗
║              ULTRA ROULETTE PRO - VERSION 3 SIGNAUX          ║
║                                                              ║
║  Outil d'observation statistique pour la roulette européenne ║
║  3 Signaux : ✅ GO  |  ⏳ ATTENTE  |  🔴 STOP              ║
║  ⚠ La roulette est un jeu de hasard pur.                    ║
╚══════════════════════════════════════════════════════════════╝

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 LOGIQUE DES 3 SIGNAUX
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

 Deux dimensions d'analyse :
 ─────────────────────────────
  • HITS : Combien de fois la zone est sortie dans les 37 derniers tours
  • GAP  : Depuis combien de tours la zone est ABSENTE consécutivement

 Deux états thermiques :
 ──────────────────────
  • Zone FROIDE : hits ≤ sigma_limit  → peu sortie, statistiquement attendue
  • Zone CHAUDE : hits >  sigma_limit  → trop sortie, statistiquement saturée

 Les 3 signaux :
 ───────────────
  ✅ GO      → Zone FROIDE  +  gap ≥ wait
               Conditions réunies : la zone est absente depuis assez longtemps
               ET elle est statistiquement froide → Moment optimal pour jouer

  ⏳ ATTENTE → Zone FROIDE  +  gap ≥ (wait - pre_alert)
               Zone froide MAIS pas encore au seuil minimum d'absence
               → Elle approche du GO, à surveiller de près

  🔴 STOP    → Zone FROIDE  +  gap trop faible  (trop tôt, vient de sortir)
               OU Zone CHAUDE + gap ≥ wait       (piège : absente mais saturée)
               → Dans les deux cas, ne pas jouer

 Résumé visuel :
 ───────────────
              FROIDE ❄️              CHAUDE 🔥
            ┌──────────────────┬───────────────┐
  gap grand │    ✅ GO         │  🔴 STOP      │
            │                  │  (piège chaud)│
            ├──────────────────┤               │
  gap moyen │    ⏳ ATTENTE    │               │
            ├──────────────────┤               │
  gap faible│    🔴 STOP       │               │
            │  (trop tôt)      │               │
            └──────────────────┴───────────────┘

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
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
                  → Plus sigma_limit est bas, plus la zone doit être RARE pour déclencher
    wait        : Gap minimum pour signal GO (tours d'absence consécutifs)
                  → Adapté à la taille de la zone : grande zone = wait court, petite = wait long
    pre_alert   : Marge avant GO pour signal ATTENTE (wait - pre_alert)
                  → Fenêtre d'anticipation : signal ⏳ déclenché X tours avant le GO
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
               → Mesure la "chaleur" de la zone sur le cycle actuel
    gap      : Tours d'absence consécutifs
               → Mesure depuis combien de temps la zone n'est pas sortie
    signal   : Texte colorisé du signal (GO / ATTENTE / STOP)
    score    : Score de priorité pour le tri (plus haut = plus prioritaire)
               → GO en haut, STOP en bas dans le tableau
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
          → Grande zone : sort souvent → seuil GO atteint vite (wait=10)
          → Froide si ≤ 6 hits sur 37 (attendu théorique ≈ 12)

        Sixain  ( 6 nums) : sigma=1, wait=22, pre_alert=3
          → Zone moyenne : doit être très froide (≤1 hit) et absente 22 tours
          → Attendu théorique ≈ 6 hits → on attend une grosse sous-repr.

        Carré   ( 4 nums) : sigma=0, wait=34, pre_alert=3
          → Petite zone : doit être à 0 hits ET absente 34 tours sur 37
          → Condition la plus stricte = signal le plus rare et le plus fort
        """

        # ── DOUZAINES (3 zones × 12 numéros) ──────────────────
        # Couvrent 1/3 du tableau chacune (hors zéro)
        # wait=10 : après 10 tours sans sortie, une douzaine est considérée en retard
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
                sigma_limit = 6,    # Froide si ≤ 6 sorties sur 37 (théorique ≈ 12)
                wait        = 10,   # GO si absente ≥ 10 tours consécutifs
                pre_alert   = 3     # ATTENTE si absente ≥ 7 tours (10-3)
            )

        # ── COLONNES (3 zones × 12 numéros) ───────────────────
        # Mêmes paramètres que les douzaines (même taille = même logique)
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
                sigma_limit = 6,    # Froide si ≤ 6 sorties sur 37 (théorique ≈ 12)
                wait        = 10,   # GO si absente ≥ 10 tours consécutifs
                pre_alert   = 3     # ATTENTE si absente ≥ 7 tours (10-3)
            )

        # ── SIXAINS (6 zones × 6 numéros) ─────────────────────
        # Zone plus petite → doit être plus absente pour signaler
        # wait=22 : absente sur 60% du cycle avant GO
        for i in range(6):
            start = i * 6 + 1              # 1, 7, 13, 19, 25, 31
            end   = start + 6              # 7, 13, 19, 25, 31, 37
            name  = f"Sixain {i+1}"
            self.zones[name] = ZoneConfig(
                name        = name,
                category    = "Sixain",
                numbers     = frozenset(range(start, end)),
                sigma_limit = 1,    # Froide si ≤ 1 sortie sur 37 (théorique ≈ 6)
                wait        = 22,   # GO si absente ≥ 22 tours consécutifs
                pre_alert   = 3     # ATTENTE si absente ≥ 19 tours (22-3)
            )

        # ── CARRÉS (9 zones × 4 numéros) ──────────────────────
        # Plus petite zone → signal le plus exigeant et le plus rare
        # wait=34 : quasi-absent sur tout le cycle (34/37 tours)
        # sigma=0 : doit n'avoir fait AUCUNE sortie dans les 37 derniers tours
        #
        # Disposition tableau (3 colonnes) :
        #   n   | n+1
        #   n+3 | n+4
        for carre_idx, n in enumerate([1, 4, 7, 10, 13, 16, 19, 22, 25], start=1):
            name = f"Carré {carre_idx}"
            self.zones[name] = ZoneConfig(
                name        = name,
                category    = "Carré",
                numbers     = frozenset([n, n+1, n+3, n+4]),
                sigma_limit = 0,    # Froide si 0 sortie sur 37 (théorique ≈ 4)
                wait        = 34,   # GO si absente ≥ 34 tours consécutifs
                pre_alert   = 3     # ATTENTE si absente ≥ 31 tours (34-3)
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

        Le GAP mesure l'absence de la zone :
          → gap = 0  : la zone est sortie au dernier tirage
          → gap = 10 : la zone n'est pas sortie depuis 10 tours
          → gap = 34 : condition maximale pour un Carré (signal GO possible)

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
        hits : int        → sorties dans les 37 derniers tours (mesure la chaleur)
        gap  : int        → tours d'absence consécutifs (mesure le retard)
        cfg  : ZoneConfig → configuration de la zone (seuils sigma, wait, pre_alert)

        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
         LOGIQUE DES 3 SIGNAUX
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

         is_cold     = hits ≤ sigma_limit
                       → La zone est FROIDE (sous-représentée)
                       → Elle sort moins que sa fréquence théorique

         is_ready    = gap ≥ wait
                       → Le GAP est suffisant pour un signal GO
                       → La zone est absente depuis assez longtemps

         pre_ready   = gap ≥ (wait - pre_alert)
                       → Le GAP approche du seuil GO
                       → Zone à surveiller → signal ATTENTE

         is_hot_risk = (not is_cold) AND is_ready
                       → Zone CHAUDE (trop sortie) mais absente depuis longtemps
                       → Piège statistique : ne pas confondre avec un GO

         ┌──────────────┬──────────────────────────────────────────┐
         │ Signal       │ Condition                                │
         ├──────────────┼──────────────────────────────────────────┤
         │ ✅ GO        │ FROIDE  ET  gap ≥ wait                  │
         │              │ → Jouer : zone froide + absente assez    │
         ├──────────────┼──────────────────────────────────────────┤
         │ ⏳ ATTENTE   │ FROIDE  ET  gap ≥ (wait - pre_alert)    │
         │              │ → Surveiller : GO dans quelques tours    │
         ├──────────────┼──────────────────────────────────────────┤
         │ 🔴 STOP      │ FROIDE  ET  gap < (wait - pre_alert)    │
         │              │ → Trop tôt : zone vient de sortir        │
         │              │                                          │
         │              │ OU CHAUDE  ET  gap ≥ wait               │
         │              │ → Piège : absente mais statistiquement   │
         │              │   saturée, risque de rebond trompeur     │
         ├──────────────┼──────────────────────────────────────────┤
         │ ✖ None       │ Zone normale → ignorée (équilibrée)     │
         └──────────────┴──────────────────────────────────────────┘

         Score de priorité (tri décroissant dans le tableau) :
         ───────────────────────────────────────────────────────
         GO      → score élevé   (affiché en premier)
         ATTENTE → score moyen   (affiché au milieu)
         STOP    → score négatif (affiché en dernier)
        ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
        """

        is_cold     = hits <= cfg.sigma_limit       # Zone froide (sous-représentée)
        is_ready    = gap  >= cfg.wait              # Gap suffisant pour GO
        pre_ready   = gap  >= (cfg.wait - cfg.pre_alert)  # Gap proche du seuil GO
        is_hot_risk = (not is_cold) and is_ready    # Chaude mais absente = piège

        # ── ✅ GO ──────────────────────────────────────────────
        # Conditions : zone froide + absente depuis ≥ wait tours
        # C'est le signal le plus fort : les deux critères sont réunis
        if is_cold and is_ready:
            score = float((cfg.sigma_limit - hits + 1) * 10 + gap)
            label = colorize(
                f"[ ✅ GO      +{gap}t vide ]",
                Color.BOLD, Color.GREEN
            )
            return ZoneResult(cfg.name, cfg.category, hits, gap, label, score)

        # ── ⏳ ATTENTE ─────────────────────────────────────────
        # Conditions : zone froide + gap proche du seuil GO (dans la fenêtre pre_alert)
        # Signal d'anticipation : dans 1 à pre_alert tours, ce sera un GO
        elif is_cold and pre_ready:
            manque = cfg.wait - gap     # Nombre de tours avant le GO
            score  = float((cfg.sigma_limit - hits + 1) * 5 + gap)
            label  = colorize(
                f"[ ⏳ ATTENTE -{manque}t restants ]",
                Color.BOLD, Color.YELLOW
            )
            return ZoneResult(cfg.name, cfg.category, hits, gap, label, score)

        # ── 🔴 STOP ───────────────────────────────────────────
        # Deux cas distincts :
        #   1. PRÉCOCE   : zone froide mais gap trop faible → trop tôt pour jouer
        #   2. CHAUD/RISQUE : zone chaude (trop de hits) mais absente → piège statistique
        elif is_cold or is_hot_risk:
            raison = "PRÉCOCE" if is_cold else "CHAUD/RISQUE"
            score  = float(hits * -1)
            label  = colorize(
                f"[ 🔴 STOP    {raison:<12} ]",
                Color.BOLD, Color.RED
            )
            return ZoneResult(cfg.name, cfg.category, hits, gap, label, score)

        # ── ✖ Zone normale → pas de signal ────────────────────
        # Zone ni froide ni en situation de risque → équilibrée → ignorée
        return None

    # ───────────────────────────────────────────────────────────
    #  3.5 ANALYSE DE TOUTES LES ZONES
    # ───────────────────────────────────────────────────────────

    def _analyze_zones(self) -> List[ZoneResult]:
        """
        Analyse les 21 zones et retourne les résultats triés par score.

        Pour chaque zone :
          1. Calcul des HITS (fréquence dans la fenêtre 37 tours)
          2. Calcul du GAP  (absence consécutive)
          3. Génération du signal via _get_signal()

        Retour :
        ────────
        List[ZoneResult] → zones avec signal, triées score décroissant.
        Les zones sans signal (normales) sont exclues.
        Tri : GO en haut → ATTENTE au milieu → STOP en bas
        """
        results = []
        recent_list = list(self._recent)   # Conversion pour comptage

        for cfg in self.zones.values():
            # HITS : nombre de sorties de la zone dans les 37 derniers tours
            # Compare à la fréquence théorique via sigma_limit pour détecter le froid
            hits = sum(1 for n in recent_list if n in cfg.numbers)

            # GAP : tours d'absence consécutifs
            # Compare à wait pour détecter si la zone est "en retard"
            gap  = self._compute_gap(cfg.numbers)

            # Signal : combinaison hits + gap → GO / ATTENTE / STOP / None
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

    def prefill(self, n: int = 37):
        """
        Pré-remplit l'historique avec n tirages aléatoires.
        Utile pour démarrer avec un historique non-vide.

        Paramètre :
        ───────────
        n : int → nombre de tirages à générer (défaut: 37 = 1 cycle complet)

        Note : simule un cycle entier pour avoir des hits et gaps significatifs
        dès le premier affichage du dashboard.
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
           → Lecture : SORT/37 = hits sur 37 tours | VIDE = gap actuel
           → Signal  : GO (jouer) / ATTENTE (surveiller) / STOP (éviter)
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
        # Minimum 5 tirages pour avoir des données exploitables
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
        # Colonnes : ZONE | CAT | SORT/37 (hits) | VIDE (gap) | SIGNAL
        # Tri      : GO en haut → ATTENTE → STOP en bas
        header = colorize(
            f"\n  {'ZONE':<14} {'CAT':<8} {'SORT/37':>7}  {'VIDE':>5}    SIGNAL",
            Color.BOLD
        )
        print(header)
        print(colorize("  " + "─" * 60, Color.DIM))

        # Compteurs pour le footer (résumé rapide des 3 types de signaux)
        count_go      = 0
        count_attente = 0
        count_stop    = 0

        for r in results:
            # Détection du type de signal pour incrémenter le bon compteur
            if "GO"        in r.signal: count_go      += 1
            elif "ATTENTE" in r.signal: count_attente += 1
            elif "STOP"    in r.signal: count_stop    += 1

            ligne = (
                f"  {r.name:<14} "
                f"{r.category:<8} "
                f"{r.hits:>6}/37  "   # hits : sorties sur les 37 derniers tours
                f"{r.gap:>4}t    "    # gap  : tours d'absence consécutifs
                f"{r.signal}"         # signal : GO / ATTENTE / STOP
            )
            print(ligne)

        # ── FOOTER ────────────────────────────────────────────
        # Résumé rapide : combien de zones en GO, ATTENTE, STOP
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
    print(colorize("  │  d      → Mode démo (37 tirages auto)    │", Color.CYAN))
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

    Commandes :
    ───────────
    0-36 → add_number()  : enregistre le tirage + rafraîchit le dashboard
    s    → get_stats()   : affiche chaud/froid de la session complète
    d    → prefill(37)   : injecte 37 tirages aléatoires (1 cycle démo)
    h    → print_help()  : réaffiche le menu des commandes
    q    → break         : quitte proprement
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
            # Affiche : total tirages + numéro le plus sorti + le moins sorti
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
            # Injecte 37 tirages aléatoires = 1 cycle complet
            # Permet de voir immédiatement des signaux sans saisie manuelle
            elif val == 'd':
                tracker.prefill(37)
                print(colorize(
                    "  ✔ 37 tirages aléatoires injectés.\n",
                    Color.GREEN
                ))
                tracker._display_dashboard()

            # ── Saisie d'un numéro ────────────────────────────
            # Enregistre le tirage → met à jour hits et gap de toutes les zones
            # → rafraîchit automatiquement le dashboard via add_number()
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
            # Saisie non numérique (ex: "abc") → on redemande
            print(colorize("  ⚠ Entrez un chiffre (0-36) ou une commande.\n", Color.RED))

        except KeyboardInterrupt:
            # Ctrl+C : sortie propre sans message d'erreur Python
            print(colorize("\n\n  Interruption. Au revoir !\n", Color.BOLD))
            break

# ═══════════════════════════════════════════════════════════════
#  POINT D'ENTRÉE
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    main()
