"""
╔══════════════════════════════════════════════════════════════╗
║              ULTRA ROULETTE PRO - VERSION COMMENTÉE          ║
║                                                              ║
║  Outil d'observation statistique pour la roulette européenne ║
║  ⚠ Rappel : la roulette est un jeu de hasard pur.           ║
║    Ce programme ne prédit rien, il observe des déséquilibres ║
╚══════════════════════════════════════════════════════════════╝

PRINCIPE MATHÉMATIQUE DE BASE :
────────────────────────────────
Sur 37 tirages (1 cycle complet de roulette européenne 0-36) :

  • Une DOUZAINE (12 numéros) devrait sortir : 12/37 ≈ 12 fois
  • Un SIXAIN    (6  numéros) devrait sortir :  6/37 ≈  6 fois
  • Un CARRÉ     (4  numéros) devrait sortir :  4/37 ≈  4 fois

Quand une zone sort MOINS que son espérance théorique
ET qu'elle est absente depuis N tours → signal d'anomalie.

ATTENTION : Ce déséquilibre ne garantit AUCUN résultat futur.
"""

import os
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Optional

# ═══════════════════════════════════════════════════════════════
#  SECTION 1 : CONFIGURATION VISUELLE (ANSI COLOR CODES)
# ═══════════════════════════════════════════════════════════════
# Les codes ANSI permettent de coloriser le terminal.
# Format : '\033[CODEm' où CODE est un entier.
# '\033[0m' (END) réinitialise toutes les couleurs.

class Color:
    GREEN   = '\033[32m'   # Signal GO   → zone froide prête
    YELLOW  = '\033[33m'   # Attente     → quelques tours manquants
    RED     = '\033[31m'   # Danger      → zone chaude anormalement absente
    CYAN    = '\033[36m'   # Surveiller  → sous-représentée mais gap insuffisant
    MAGENTA = '\033[35m'   # Catégorie Sixain
    BOLD    = '\033[1m'    # Texte en gras
    DIM     = '\033[2m'    # Texte atténué (infos secondaires)
    END     = '\033[0m'    # Reset couleur


def colorize(text: str, *codes: str) -> str:
    """
    Applique un ou plusieurs codes couleur ANSI à un texte.

    Args:
        text  : Le texte à coloriser.
        *codes: Codes couleur à concaténer (ex: Color.BOLD, Color.GREEN).

    Returns:
        Chaîne avec les codes couleur appliqués + reset final.

    Exemple:
        colorize("GO !", Color.BOLD, Color.GREEN)
        → '\033[1m\033[32mGO !\033[0m'
    """
    return "".join(codes) + text + Color.END


# ═══════════════════════════════════════════════════════════════
#  SECTION 2 : STRUCTURES DE DONNÉES (DATACLASSES)
# ═══════════════════════════════════════════════════════════════
# Les @dataclass génèrent automatiquement __init__, __repr__, etc.
# Avantage vs dict : typage, lisibilité, autocomplétion IDE.

@dataclass
class ZoneConfig:
    """
    Paramètres statistiques d'une CATÉGORIE de zone.
    Partagée par toutes les zones d'une même famille.

    Attributs:
        category   : Nom de la famille ('Tiers', 'Sixain', 'Carré').
        sigma_limit: Seuil MAX de sorties sur 37 pour déclencher un signal.
                     En dessous → zone sous-représentée (froide).
                     Ex: sigma_limit=6 pour Tiers signifie :
                         si hits ≤ 6 alors la zone est "froide".
        wait       : Nombre de tours de vide MINIMUM avant signal GO.
                     Évite les faux signaux trop précoces.
        size       : Nombre de numéros dans la zone (12, 6 ou 4).
                     Sert de référence pour l'espérance théorique.
    """
    category   : str
    sigma_limit: int
    wait       : int
    size       : int


@dataclass
class ZoneResult:
    """
    Résultat d'analyse pour UNE zone à UN instant T.
    Créé à chaque appel de _analyze_zones().

    Attributs:
        name  : Nom de la zone (ex: 'Douz 1', 'Sixain 3').
        hits  : Nombre de sorties dans les 37 DERNIERS tirages.
        gap   : Tours consécutifs depuis la dernière sortie de la zone.
        config: Référence à la ZoneConfig parente.
        signal: Texte colorisé du signal (None si pas de signal).
        score : Priorité du signal. Plus élevé = plus urgent.
                Permet de trier les zones par urgence décroissante.
    """
    name  : str
    hits  : int
    gap   : int
    config: ZoneConfig
    signal: Optional[str] = None    # None = pas de signal à afficher
    score : float         = 0.0     # Score de tri (calculé dans _get_signal)


# ═══════════════════════════════════════════════════════════════
#  SECTION 3 : MOTEUR PRINCIPAL
# ═══════════════════════════════════════════════════════════════

class UltraRoulettePro:
    """
    Moteur d'analyse statistique pour la roulette européenne (0-36).

    Fonctionnement global :
    1. L'utilisateur saisit les numéros sortis un à un.
    2. Le moteur maintient une fenêtre glissante de 37 tirages.
    3. Pour chaque zone, il calcule hits (fréquence) et gap (absence).
    4. Les déséquilibres statistiques déclenchent des signaux visuels.
    """

    # Constante de classe : taille de la fenêtre d'analyse.
    # 37 = nombre total de cases (0 à 36) = 1 cycle théorique complet.
    WINDOW: int = 37

    def __init__(self):
        # Liste complète de tous les tirages depuis le début de la session.
        # Conservée pour les statistiques globales et l'historique affiché.
        self.history: list[int] = []

        # deque avec maxlen : file circulaire de taille fixe.
        # Quand elle est pleine, l'ajout d'un élément supprime automatiquement
        # le plus ancien. Accès aux N derniers en O(1) sans slicing.
        # C'est notre "fenêtre glissante" de WINDOW tirages.
        self._recent: deque[int] = deque(maxlen=self.WINDOW)

        # Dictionnaire principal des zones.
        # Structure : { nom_zone: (frozenset_numéros, ZoneConfig) }
        # frozenset pour les lookups O(1) : "n in nums" est instantané.
        self.zones: dict[str, tuple[frozenset[int], ZoneConfig]] = {}

        # Construction de toutes les zones au démarrage.
        self._build_zones()

    # ───────────────────────────────────────────────────────────
    #  3.1  CONSTRUCTION DES ZONES
    # ───────────────────────────────────────────────────────────

    def _build_zones(self) -> None:
        """
        Construit le dictionnaire self.zones avec toutes les zones de jeu.

        Zones créées :
          - 3 Douzaines  (Tiers  : 12 numéros chacune)
          - 3 Colonnes   (Tiers  : 12 numéros chacune)
          - 6 Sixains    (Sixain :  6 numéros chacun)
          - 9 Carrés     (Carré  :  4 numéros chacun)

        Les configs sont centralisées dans cfg_map pour éviter la duplication.
        Modifier sigma_limit ou wait ici affecte toutes les zones de la famille.
        """

        # ── Configurations par catégorie ──────────────────────
        # sigma_limit : calibré empiriquement.
        #   Tiers  : espérance = 12 tirages/37 → seuil à 6 (50% sous espérance)
        #   Sixain : espérance =  6 tirages/37 → seuil à 1 (très sous-représenté)
        #   Carré  : espérance =  4 tirages/37 → seuil à 0 (jamais sorti)
        # wait : nombre de tours de vide requis avant signal GO.
        #   Plus la zone est petite, plus le wait est long (absences normales +
        #   fréquentes pour une petite zone).
        cfg_map = {
            'Tiers' : ZoneConfig('Tiers',  sigma_limit=6, wait=10, size=12),
            'Sixain': ZoneConfig('Sixain', sigma_limit=1, wait=22, size=6),
            'Carré' : ZoneConfig('Carré',  sigma_limit=0, wait=34, size=4),
        }

        # ── Douzaines ─────────────────────────────────────────
        # Le plateau est divisé en 3 douzaines de 12 numéros consécutifs.
        # Douz 1 : 1-12  |  Douz 2 : 13-24  |  Douz 3 : 25-36
        for label, rng in [
            ('Douz 1', range(1, 13)),
            ('Douz 2', range(13, 25)),
            ('Douz 3', range(25, 37)),
        ]:
            # frozenset() pour immutabilité et lookup O(1).
            self.zones[label] = (frozenset(rng), cfg_map['Tiers'])

        # ── Colonnes ──────────────────────────────────────────
        # Sur le plateau, les colonnes regroupent les numéros par résidu mod 3.
        # Col 1 : 1,4,7,10,...,34  (n%3 == 1)
        # Col 2 : 2,5,8,11,...,35  (n%3 == 2)
        # Col 3 : 3,6,9,12,...,36  (n%3 == 0)
        for remainder, label in [(1, 'Col 1'), (2, 'Col 2'), (0, 'Col 3')]:
            nums = frozenset(n for n in range(1, 37) if n % 3 == remainder)
            self.zones[label] = (nums, cfg_map['Tiers'])

        # ── Sixains ───────────────────────────────────────────
        # 6 groupes de 6 numéros consécutifs couvrant 1-36 (sans le 0).
        # Sixain 1 : 1-6  |  Sixain 2 : 7-12  | ... |  Sixain 6 : 31-36
        for i in range(6):
            start = i * 6 + 1                          # 1, 7, 13, 19, 25, 31
            nums  = frozenset(range(start, start + 6)) # 6 numéros consécutifs
            self.zones[f'Sixain {i+1}'] = (nums, cfg_map['Sixain'])

        # ── Carrés ────────────────────────────────────────────
        # Un carré regroupe 4 numéros formant un carré sur le plateau physique.
        # Seuls les carrés "internes" sont listés (pas de bord gauche/droit).
        # Chaque tuple = (n, n+1, n+3, n+4) selon la grille 3 colonnes.
        squares = [
            (1,  2,  4,  5),   # Carré 1  : ligne 1-2, col 1-2
            (2,  3,  5,  6),   # Carré 2  : ligne 1-2, col 2-3
            (4,  5,  7,  8),   # Carré 3  : ligne 2-3, col 1-2
            (5,  6,  8,  9),   # Carré 4  : ligne 2-3, col 2-3
            (7,  8, 10, 11),   # Carré 5  : ligne 3-4, col 1-2
            (10, 11, 13, 14),  # Carré 6  : ligne 4-5, col 1-2
            (13, 14, 16, 17),  # Carré 7  : ligne 5-6, col 1-2
            (16, 17, 19, 20),  # Carré 8  : ligne 6-7, col 1-2
            (31, 32, 34, 35),  # Carré 9  : ligne 11-12, col 1-2
        ]
        for i, sq in enumerate(squares):
            self.zones[f'Carré {i+1}'] = (frozenset(sq), cfg_map['Carré'])

    # ───────────────────────────────────────────────────────────
    #  3.2  AJOUT D'UN NUMÉRO
    # ───────────────────────────────────────────────────────────

    def add_number(self, num: int) -> None:
        """
        Point d'entrée principal : enregistre un nouveau tirage et
        rafraîchit le dashboard.

        Args:
            num: Numéro sorti (0-36).

        Flow :
            1. Ajoute num à self.history (historique complet).
            2. Ajoute num à self._recent (fenêtre glissante WINDOW).
               → La deque supprime automatiquement le plus vieux si pleine.
            3. Déclenche l'affichage du dashboard mis à jour.
        """
        self.history.append(num)
        self._recent.append(num)
        self._display_dashboard(num)

    # ───────────────────────────────────────────────────────────
    #  3.3  CALCUL DU GAP
    # ───────────────────────────────────────────────────────────

    def _compute_gap(self, nums: frozenset[int]) -> int:
        """
        Calcule le nombre de tirages consécutifs depuis la DERNIÈRE sortie
        d'un numéro appartenant à la zone 'nums'.

        Itère à rebours sur self._recent (max WINDOW éléments).
        Dès qu'un numéro de la zone est trouvé, retourne le compteur.
        Si aucun numéro de la zone n'est sorti dans la fenêtre,
        retourne len(window) (= gap maximum observable).

        CORRECTION vs version originale :
        L'ancienne version itérait sur self.history ENTIER, ce qui pouvait
        retourner des gaps de plusieurs centaines de tours → signaux erronés.
        On limite ici à WINDOW pour rester cohérent avec la fenêtre d'analyse.

        Args:
            nums: frozenset des numéros composant la zone.

        Returns:
            Entier ≥ 0 représentant le nombre de tours d'absence.
            0 = le dernier tirage était dans la zone.
        """
        # Conversion en list pour itération inversée (deque ne supporte pas
        # reversed() dans toutes les versions Python < 3.8).
        window = list(self._recent)

        gap = 0
        for n in reversed(window):   # Du plus récent au plus ancien
            if n in nums:             # Lookup O(1) grâce au frozenset
                return gap            # Trouvé → gap = nb de tours depuis
            gap += 1

        return gap  # Jamais sorti dans la fenêtre → gap = taille fenêtre

    # ───────────────────────────────────────────────────────────
    #  3.4  LOGIQUE DE SIGNAL
    # ───────────────────────────────────────────────────────────

    def _get_signal(self, result: ZoneResult) -> tuple[Optional[str], float]:
        """
        Détermine le signal à afficher pour une zone et son score de priorité.

        LOGIQUE DE DÉCISION (4 cas) :
        ┌─────────────────────────────────────────────────────────┐
        │  Cas 1 : GO  (vert)                                     │
        │    → Zone froide (hits ≤ sigma_limit)                   │
        │    → Gap suffisant (gap ≥ wait)                         │
        │    → Score élevé : urgence de jouer                     │
        ├─────────────────────────────────────────────────────────┤
        │  Cas 2 : ATTENTE  (jaune)                               │
        │    → Zone froide                                         │
        │    → Gap proche (wait-3 ≤ gap < wait)                   │
        │    → Préparer la mise, pas encore le moment             │
        ├─────────────────────────────────────────────────────────┤
        │  Cas 3 : SURVEILLER  (cyan)                             │
        │    → Zone froide                                         │
        │    → Gap encore trop faible (< wait-3)                  │
        │    → Observer, ne pas agir                              │
        ├─────────────────────────────────────────────────────────┤
        │  Cas 4 : DANGER  (rouge)                                │
        │    → Zone chaude (hits > sigma_limit + 2)               │
        │    → Gap suffisant malgré la chaleur                    │
        │    → Anomalie : zone sur-représentée et de nouveau       │
        │      absente → risque de correction inverse             │
        └─────────────────────────────────────────────────────────┘

        Args:
            result: ZoneResult contenant hits, gap et config.

        Returns:
            Tuple (signal_text, score).
            signal_text : chaîne colorisée ou None si pas de signal.
            score       : float pour tri par priorité décroissante.
        """
        cfg  = result.config
        hits = result.hits
        gap  = result.gap

        # ── Flags booléens (séparation logique/affichage) ─────
        # Zone "froide" : sorties inférieures ou égales au seuil configuré.
        under     = hits <= cfg.sigma_limit

        # Zone "brûlante" : largement sur-représentée (+2 au-dessus du seuil).
        # Le +2 évite de flaguer des zones légèrement au-dessus du seuil.
        hot       = hits > cfg.sigma_limit + 2

        # Gap suffisant pour considérer un signal GO.
        gap_ok    = gap >= cfg.wait

        # Gap "proche" du seuil : dans les 3 tours avant le wait.
        # Fenêtre d'alerte précoce pour préparer la mise.
        gap_close = gap >= cfg.wait - 3

        # ── Cas 1 : GO ────────────────────────────────────────
        if under and gap_ok:
            # Score = intensité du froid × 10 + dépassement du wait.
            # Ex: hits=0, sigma_limit=6, gap=15, wait=10
            # → score = (6-0+1)*10 + (15-10) = 70 + 5 = 75
            score = (cfg.sigma_limit - hits + 1) * 10 + (gap - cfg.wait)
            signal = colorize(f"[ GO ! +{gap}t vide ]", Color.BOLD, Color.GREEN)
            return signal, score

        # ── Cas 2 : ATTENTE ───────────────────────────────────
        if under and gap_close:
            manque = cfg.wait - gap   # Tours restants avant GO
            # Score réduit (×5) : signal moins urgent qu'un GO.
            score  = (cfg.sigma_limit - hits + 1) * 5
            signal = colorize(f"[ ATTENTE -{manque}t ]", Color.YELLOW)
            return signal, score

        # ── Cas 3 : SURVEILLER ────────────────────────────────
        if under:
            # Zone froide mais pas encore proche du seuil.
            # Score minimal (×2) : simple surveillance.
            score  = (cfg.sigma_limit - hits + 1) * 2
            signal = colorize("[ SURVEILLER ]", Color.CYAN)
            return signal, score

        # ── Cas 4 : DANGER ────────────────────────────────────
        if hot and gap_ok:
            # Zone chaude mais absente depuis longtemps.
            # Score négatif : affiché en dernier dans le tableau.
            signal = colorize("[ DANGER/CHAUD ]", Color.RED)
            return signal, -1.0

        # ── Aucun signal ──────────────────────────────────────
        # Zone dans les paramètres normaux → pas d'affichage.
        return None, 0.0

    # ───────────────────────────────────────────────────────────
    #  3.5  ANALYSE DE TOUTES LES ZONES
    # ───────────────────────────────────────────────────────────

    def _analyze_zones(self) -> list[ZoneResult]:
        """
        Parcourt toutes les zones, calcule hits/gap, génère les signaux
        et retourne la liste des zones ayant un signal actif,
        triée par score décroissant (urgence décroissante).

        Complexité : O(Z × W) où Z = nb zones (~21), W = WINDOW (37).
        Très rapide pour des valeurs aussi faibles.

        Returns:
            Liste de ZoneResult filtrée (signal != None) et triée.
        """
        results      = []
        # Snapshot de la fenêtre courante pour éviter plusieurs conversions.
        recent_list  = list(self._recent)

        for name, (nums, cfg) in self.zones.items():

            # ── Calcul des hits ───────────────────────────────
            # Compte combien de tirages dans la fenêtre appartiennent à la zone.
            # 'n in nums' est O(1) car nums est un frozenset.
            hits = sum(1 for n in recent_list if n in nums)

            # ── Calcul du gap ─────────────────────────────────
            # Tours consécutifs depuis la dernière sortie de la zone.
            gap  = self._compute_gap(nums)

            # ── Création du résultat ──────────────────────────
            result        = ZoneResult(name=name, hits=hits, gap=gap, config=cfg)
            signal, score = self._get_signal(result)
            result.signal = signal
            result.score  = score
            results.append(result)

        # ── Filtrage et tri ───────────────────────────────────
        # On ne garde que les zones avec un signal actif.
        # Tri par score décroissant : les GO (score élevé) en premier.
        return sorted(
            (r for r in results if r.signal is not None),
            key=lambda r: r.score,
            reverse=True
        )

    # ───────────────────────────────────────────────────────────
    #  3.6  AFFICHAGE DU DASHBOARD
    # ───────────────────────────────────────────────────────────

    def _display_dashboard(self, last_num: int) -> None:
        """
        Efface le terminal et affiche le dashboard complet mis à jour.

        Structure de l'affichage :
        ┌──────────────────────────────────────┐
        │  Header : tour N°, dernier numéro    │
        │  Historique : 20 derniers numéros    │
        │  ── si < WINDOW tirages ──           │
        │    Message d'initialisation          │
        │  ── sinon ──                         │
        │  Tableau des signaux actifs          │
        │  Footer : stats globales             │
        └──────────────────────────────────────┘

        Args:
            last_num: Le numéro qui vient d'être ajouté (mis en évidence).
        """
        # Efface le terminal (Windows : 'cls', Unix/Mac : 'clear').
        # Crée l'effet "écran fixe" qui se rafraîchit à chaque tirage.
        os.system('cls' if os.name == 'nt' else 'clear')

        # ── Header ────────────────────────────────────────────
        print(colorize(
            f" ULTRA ROULETTE PRO  |  Tour #{len(self.history):>4}"
            f"  |  Dernier : {last_num:>2} ",
            Color.BOLD
        ))
        print("─" * 60)

        # ── Historique compact ────────────────────────────────
        # Affiche les 20 derniers numéros.
        # Le dernier tirage est mis en jaune pour le repérer visuellement.
        last_20  = self.history[-20:]
        hist_str = "  ".join(
            colorize(f"{n:>2}", Color.YELLOW) if n == last_num else f"{n:>2}"
            for n in last_20
        )
        print(f" Historique : {hist_str}")
        print("─" * 60)

        # ── Vérification du seuil d'initialisation ────────────
        # On ne peut pas analyser 37 tirages si on en a moins de 37.
        # Affiche un message d'attente pendant la phase de chargement.
        if len(self.history) < self.WINDOW:
            remaining = self.WINDOW - len(self.history)
            print(colorize(
                f"  Initialisation : {len(self.history)}/{self.WINDOW} "
                f"({remaining} numéros manquants avant analyse)",
                Color.DIM
            ))
            return  # Sortie anticipée : pas d'analyse possible

        # ── Analyse et affichage du tableau ───────────────────
        active = self._analyze_zones()

        if not active:
            # Aucune zone ne présente de déséquilibre notable.
            print(colorize(
                "  Aucune anomalie détectée. Patientez...",
                Color.DIM
            ))
        else:
            # En-tête du tableau avec alignement fixe.
            # :<12 = aligné à gauche sur 12 caractères.
            print(f"  {'ZONE':<12} {'CAT':<8} {'SORT/37':<9} {'VIDE':<7} SIGNAL")
            print("  " + "─" * 56)

            for r in active:
                # Couleur spécifique par catégorie pour identification rapide.
                cat_color = {
                    'Tiers' : Color.CYAN,
                    'Sixain': Color.MAGENTA,
                    'Carré' : Color.YELLOW,
                }.get(r.config.category, '')

                cat_str = colorize(f"{r.config.category:<8}", cat_color)

                print(
                    f"  {r.name:<12} {cat_str} "
                    f"{r.hits:<9} {r.gap:<7} {r.signal}"
                )

        # ── Footer ────────────────────────────────────────────
        # Informations globales : fréquence du zéro et nb de signaux actifs.
        print("─" * 60)
        zeros = self.history.count(0)
        print(
            colorize(f"  Zéros : {zeros}", Color.DIM) +
            colorize(f"  |  Signaux actifs : {len(active)}", Color.DIM)
        )

    # ───────────────────────────────────────────────────────────
    #  3.7  UTILITAIRES
    # ───────────────────────────────────────────────────────────

    def prefill(self, n: int = 36) -> None:
        """
        Pré-remplit l'historique avec n numéros aléatoires (0-36).
        Utile pour démarrer rapidement sans saisir manuellement les
        premiers tirages nécessaires à l'initialisation.

        Args:
            n: Nombre de tirages à générer (défaut = 36 = WINDOW - 1).
               On génère WINDOW-1 pour que le premier vrai tirage
               complète la fenêtre et déclenche la première analyse.
        """
        for _ in range(n):
            num = random.randint(0, 36)
            self.history.append(num)    # Historique complet
            self._recent.append(num)    # Fenêtre glissante
        print(colorize(f"  {n} numéros générés aléatoirement.", Color.DIM))

    def get_stats(self) -> dict:
        """
        Retourne un dictionnaire de statistiques globales sur la session.

        Calculs :
          - Fréquence de chaque numéro (0-36) sur tout l'historique.
          - Identification du numéro le plus sorti (chaud) et moins sorti (froid).

        Returns:
            Dict avec clés : total_tirages, numero_chaud, numero_froid, frequences.
            Dict vide si historique vide.

        Note : O(37 × N) avec N = len(history). Acceptable pour usage interactif.
        """
        if not self.history:
            return {}

        # Fréquence de chaque numéro sur l'historique complet.
        freq = {n: self.history.count(n) for n in range(37)}

        return {
            'total_tirages': len(self.history),
            'numero_chaud' : max(freq, key=freq.get),   # Numéro le + fréquent
            'numero_froid' : min(freq, key=freq.get),   # Numéro le - fréquent
            'frequences'   : freq,
        }


# ═══════════════════════════════════════════════════════════════
#  SECTION 4 : POINT D'ENTRÉE ET BOUCLE INTERACTIVE
# ═══════════════════════════════════════════════════════════════

def main() -> None:
    """
    Boucle principale d'interaction avec l'utilisateur.

    Commandes disponibles :
      - Entier 0-36 : saisie d'un nouveau numéro tiré.
      - 's'         : affichage des statistiques globales.
      - 'q'         : quitter proprement.

    Gestion des erreurs :
      - ValueError       : saisie non numérique.
      - KeyboardInterrupt: Ctrl+C pour quitter sans message d'erreur.
    """
    tracker = UltraRoulettePro()

    print(colorize("\n  === ULTRA ROULETTE PRO ===\n", Color.BOLD))
    print("  Pré-remplir avec 36 numéros aléatoires ? (o/n)")

    if input("  > ").strip().lower() == 'o':
        tracker.prefill(36)
        # Affichage immédiat du dashboard après pré-remplissage.
        if tracker.history:
            tracker._display_dashboard(tracker.history[-1])

    print(colorize(
        "\n  Commandes : numéro (0-36) | 's' stats | 'q' quitter\n",
        Color.DIM
    ))

    # ── Boucle principale ─────────────────────────────────────
    while True:
        try:
            val = input("  Numéro sorti : ").strip().lower()

            # ── Quitter ───────────────────────────────────────
            if val == 'q':
                print(colorize(
                    "\n  Session terminée. Bonne chance !\n",
                    Color.BOLD
                ))
                break

            # ── Statistiques ──────────────────────────────────
            if val == 's':
                stats = tracker.get_stats()
                if stats:
                    print(colorize(
                        f"\n  Total : {stats['total_tirages']} tirages"
                        f"  |  Chaud : {stats['numero_chaud']}"
                        f"  |  Froid : {stats['numero_froid']}\n",
                        Color.CYAN
                    ))
                else:
                    print(colorize("  Aucun tirage enregistré.", Color.DIM))
                continue

            # ── Saisie d'un numéro ────────────────────────────
            n = int(val)   # Peut lever ValueError si non numérique.

            if 0 <= n <= 36:
                tracker.add_number(n)
            else:
                # Numéro hors plage valide (roulette européenne : 0-36).
                print(colorize(
                    "  ⚠ Numéro entre 0 et 36 uniquement.",
                    Color.RED
                ))

        except ValueError:
            # Saisie non convertible en entier (ex: lettres, symboles).
            print(colorize("  ⚠ Entrez un chiffre valide (0-36).", Color.RED))

        except KeyboardInterrupt:
            # Ctrl+C : sortie propre sans traceback.
            print(colorize("\n\n  Interruption. Au revoir !\n", Color.BOLD))
            break


# Point d'entrée standard Python.
# Le bloc if __name__ == "__main__" garantit que main() n'est appelé
# que si le script est exécuté directement (pas importé comme module).
if __name__ == "__main__":
    main()
