"""
Fitness Evaluator
Ocenia parametry agenta przez uruchamianie sparingów.
"""

import json
import os
import tempfile
import subprocess
import time
from typing import Dict


class FitnessEvaluator:
    def __init__(self, agent_port: int = 8100, opponent_port: int = 8101, headless_runner_path: str = None):
        """
        Args:
            agent_port: Port dla testowanego agenta
            opponent_port: Port dla agenta przeciwnika
            headless_runner_path: Ścieżka do headless_runner.py
        """
        self.agent_port = agent_port
        self.opponent_port = opponent_port
        
        if headless_runner_path is None:
            # Domyślna ścieżka (względna)
            current_dir = os.path.dirname(os.path.dirname(__file__))
            self.headless_runner_path = os.path.join(
                os.path.dirname(current_dir), 
                '02_FRAKCJA_SILNIKA', 
                'headless_runner.py'
            )
        else:
            self.headless_runner_path = headless_runner_path
    
    def evaluate(self, params: Dict, num_games: int = 5) -> float:
        """
        Ocenia parametry przez uruchomienie gier.
        
        Args:
            params: Parametry TSK-C i TSK-D do testowania
            num_games: Liczba gier do przeprowadzenia
        
        Returns:
            float: Fitness score
        """
        # TODO: Implementacja uruchamiania agenta z parametrami
        # 1. Zapisz params do tymczasowego pliku config
        # 2. Uruchom agenta z tymi parametrami
        # 3. Uruchom agenta przeciwnika
        # 4. Uruchom silnik headless
        # 5. Zbierz wyniki
        
        # PLACEHOLDER - symulowana ocena
        print(f"    [Fitness] Running {num_games} games...")
        
        total_score = 0.0
        for game in range(num_games):
            # Symulacja gry
            damage_dealt = sum(abs(v) for v in params.values()) * 10  # Placeholder
            tanks_killed = min(int(damage_dealt / 200), 3)
            survival_time = min(damage_dealt * 5, 5000)
            
            # Funkcja fitness
            score = (
                damage_dealt * 0.5 +       # Zadane obrażenia
                tanks_killed * 100 +       # Liczba zniszczeń
                survival_time * 0.01       # Czas przetrwania
            )
            total_score += score
        
        avg_score = total_score / num_games
        return avg_score
    
    def run_game_headless(self, params: Dict) -> Dict:
        """
        Uruchamia pojedynczą grę w trybie headless.
        
        Args:
            params: Parametry agenta
        
        Returns:
            Dict z wynikami: {damage_dealt, tanks_killed, survival_time}
        """
        # TODO: Implementacja rzeczywistego uruchomienia
        
        # 1. Zapisz parametry do pliku tymczasowego
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump(params, f)
            params_file = f.name
        
        try:
            # 2. Uruchom agent z parametrami (TODO)
            # subprocess.Popen(['python', 'intelligent_agent.py', '--params', params_file, '--port', str(self.agent_port)])
            
            # 3. Uruchom silnik headless (TODO)
            # result = subprocess.run(['python', self.headless_runner_path, ...], capture_output=True)
            
            # 4. Parsuj wyniki
            results = {
                'damage_dealt': 0.0,
                'tanks_killed': 0,
                'survival_time': 0.0
            }
            
            return results
        
        finally:
            # Cleanup
            if os.path.exists(params_file):
                os.remove(params_file)
    
    def calculate_fitness(self, results: Dict) -> float:
        """
        Oblicza fitness na podstawie wyników gry.
        
        Args:
            results: {damage_dealt, tanks_killed, survival_time}
        
        Returns:
            float: Fitness score
        """
        return (
            results['damage_dealt'] * 0.5 +
            results['tanks_killed'] * 100 +
            results['survival_time'] * 0.01
        )


if __name__ == "__main__":
    print("Fitness Evaluator module")
    print("Import this module and use FitnessEvaluator class")
