import os
import random


# --- CONFIGURATION VISUELLE SIMPLIFIÉE ---
class Color:
    GREEN = '\033[32m'
    YELLOW = '\033[33m'
    RED = '\033[31m'
    CYAN = '\033[36m'
    BOLD = '\033[1m'
    END = '\033[0m'


class UltraRoulettePro:
    def __init__(self):
        self.history = []
        # 'wait' = tours de vide avant signal / 'sigma_limit' = max sorties sur 37
        self.config = {
            'Tiers': {'sigma_limit': 6, 'wait': 10},
            'Sixain': {'sigma_limit': 1, 'wait': 22},
            'Carré': {'sigma_limit': 0, 'wait': 34}
        }
        self.zones = self._generate_zones()

    def _generate_zones(self):
        z = {}
        z['Douz 1'] = (list(range(1, 13)), 'Tiers')
        z['Douz 2'] = (list(range(13, 25)), 'Tiers')
        z['Douz 3'] = (list(range(25, 37)), 'Tiers')
        z['Col 1'] = ([n for n in range(1, 37) if n % 3 == 1], 'Tiers')
        z['Col 2'] = ([n for n in range(1, 37) if n % 3 == 2], 'Tiers')
        z['Col 3'] = ([n for n in range(1, 37) if n % 3 == 0], 'Tiers')
        for i in range(6):
            start = i * 6 + 1
            z[f'Sixain {i + 1}'] = (list(range(start, start + 6)), 'Sixain')
        return z

    def add_number(self, num):
        self.history.append(num)
        self.display_dashboard(num)

    def get_signal(self, hits, gap, cfg):
        is_under_represented = hits <= cfg['sigma_limit']
        is_safe_gap = gap >= cfg['wait']
        pre_alert = gap >= (cfg['wait'] - 3)

        if is_under_represented and is_safe_gap:
            return f"{Color.GREEN}[ JOUEZ : GO ]{Color.END}"
        elif is_under_represented and pre_alert:
            return f"{Color.YELLOW}[ ATTENTE : {cfg['wait'] - gap} ]{Color.END}"
        elif is_under_represented:
            return f"{Color.CYAN}[ SURVEILLER ]{Color.END}"
        elif is_safe_gap:
            return f"{Color.RED}[ DANGER : CHAUD ]{Color.END}"
        return None

    def display_dashboard(self, last_num):
        # Nettoyage console pour un affichage fixe
        os.system('cls' if os.name == 'nt' else 'clear')

        print(f"{Color.BOLD}TOUR N°{len(self.history)} | DERNIER NUMÉRO : {Color.YELLOW}{last_num}{Color.END}")

        if len(self.history) < 37:
            print(f"Initialisation : {len(self.history)}/37 numéros...")
            return

        print(f"{'-' * 55}")
        print(f"{'ZONE':<12} | {'SORTIES':<8} | {'VIDE':<5} | {'SIGNAL'}")
        print(f"{'-' * 55}")

        recent_37 = self.history[-37:]
        found = False

        for name, (nums, cat) in self.zones.items():
            cfg = self.config[cat]
            hits = sum(1 for n in recent_37 if n in nums)

            gap = 0
            for n in reversed(self.history):
                if n in nums: break
                gap += 1

            signal = self.get_signal(hits, gap, cfg)

            if signal:
                print(f"{name:<12} | {hits:<8} | {gap:<5} | {signal}")
                found = True

        if not found:
            print("Aucune anomalie. Attendez un déséquilibre.")
        print(f"{'-' * 55}")


# --- LANCEMENT ---
if __name__ == "__main__":
    tracker = UltraRoulettePro()

    print("Voulez-vous pré-remplir avec 36 numéros aléatoires ? (o/n)")
    if input("> ").lower() == 'o':
        for _ in range(36):
            tracker.history.append(random.randint(0, 36))

    while True:
        try:
            val = input(f"\nNuméro sorti (ou 'q') : ")
            if val.lower() == 'q': break
            n = int(val)
            if 0 <= n <= 36:
                tracker.add_number(n)
        except ValueError:
            print("Entrez un chiffre valide.")
