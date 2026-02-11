"""
Skrypt do uruchomienia treningu algorytmem genetycznym
"""

import sys
import os
import argparse

# Dodaj ścieżki
current_dir = os.path.dirname(__file__)
parent_dir = os.path.dirname(current_dir)
sys.path.insert(0, parent_dir)

from genetic_algorithm import GeneticAlgorithm
from fitness_evaluator import FitnessEvaluator


def main():
    parser = argparse.ArgumentParser(description="Trening agenta algorytmem genetycznym")
    parser.add_argument("--generations", type=int, default=30, help="Liczba generacji")
    parser.add_argument("--population", type=int, default=20, help="Rozmiar populacji")
    parser.add_argument("--mutation-rate", type=float, default=0.15, help="Współczynnik mutacji")
    parser.add_argument("--crossover-rate", type=float, default=0.7, help="Współczynnik krzyżowania")
    parser.add_argument("--elite-size", type=int, default=2, help="Liczba elit")
    parser.add_argument("--output-dir", type=str, default="ga_results", help="Katalog wynikowy")
    parser.add_argument("--agent-port", type=int, default=8100, help="Port testowanego agenta")
    parser.add_argument("--opponent-port", type=int, default=8101, help="Port przeciwnika")
    args = parser.parse_args()
    
    print("="*70)
    print("TRENING ALGORYTMEM GENETYCZNYM")
    print("="*70)
    print(f"Generacje:        {args.generations}")
    print(f"Populacja:        {args.population}")
    print(f"Mutacja:          {args.mutation_rate}")
    print(f"Krzyżowanie:      {args.crossover_rate}")
    print(f"Elity:            {args.elite_size}")
    print(f"Katalog wynikowy: {args.output_dir}")
    print("="*70)
    print()
    
    # Inicjalizacja GA
    ga = GeneticAlgorithm(
        population_size=args.population,
        mutation_rate=args.mutation_rate,
        crossover_rate=args.crossover_rate,
        elite_size=args.elite_size
    )
    
    # Inicjalizacja evaluatora
    fitness_evaluator = FitnessEvaluator(
        agent_port=args.agent_port,
        opponent_port=args.opponent_port
    )
    
    # Uruchom ewolucję
    try:
        population, history = ga.evolve(
            generations=args.generations,
            fitness_evaluator=fitness_evaluator,
            output_dir=args.output_dir
        )
        
        print("\n" + "="*70)
        print("TRENING ZAKOŃCZONY POMYŚLNIE!")
        print("="*70)
        print(f"Najlepszy fitness końcowy: {history[-1]:.2f}")
        print(f"Poprawa: {history[-1] - history[0]:.2f}")
        print(f"Wyniki zapisane w: {args.output_dir}/")
        print("="*70)
        
    except KeyboardInterrupt:
        print("\n\nTrening przerwany przez użytkownika")
        print("Wyniki częściowe zapisane w:", args.output_dir)
    except Exception as e:
        print(f"\n\nBŁĄD podczas treningu: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
