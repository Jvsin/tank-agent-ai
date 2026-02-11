"""
Algorytm Genetyczny do optymalizacji parametrów TSK-C i TSK-D
"""

import numpy as np
import json
import os
from copy import deepcopy
from typing import List, Dict


class GeneticAlgorithm:
    def __init__(
        self, 
        population_size: int = 20, 
        mutation_rate: float = 0.1,
        crossover_rate: float = 0.7,
        elite_size: int = 2
    ):
        self.population_size = population_size
        self.mutation_rate = mutation_rate
        self.crossover_rate = crossover_rate
        self.elite_size = elite_size
        
        # Definicja przestrzeni parametrów
        self.param_ranges = {
            # TSK-C
            'dist_close': (5.0, 12.0),
            'dist_medium': (12.0, 20.0),
            'dist_far': (20.0, 35.0),
            'angle_small': (3.0, 10.0),
            'angle_medium': (10.0, 25.0),
            'angle_large': (25.0, 60.0),
            'fire_angle_threshold': (5.0, 15.0),
            'rotation_gain': (0.8, 2.0),
            'rotation_slow_gain': (0.3, 0.8),
            
            # TSK-D
            'angle_threshold_small': (5.0, 15.0),
            'angle_threshold_large': (30.0, 60.0),
            'distance_close': (10.0, 25.0),
            'distance_far': (35.0, 70.0),
            'speed_max_multiplier': (0.8, 1.0),
            'speed_min_multiplier': (0.2, 0.5),
        }
    
    def initialize_population(self) -> List[Dict]:
        """Tworzy losową populację parametrów."""
        population = []
        for _ in range(self.population_size):
            individual = {}
            for param, (min_val, max_val) in self.param_ranges.items():
                individual[param] = np.random.uniform(min_val, max_val)
            population.append(individual)
        return population
    
    def evaluate_fitness(self, individual: Dict, fitness_evaluator, num_games: int = 5) -> float:
        """
        Ocena osobnika przez sparingi.
        
        Args:
            individual: Parametry do oceny
            fitness_evaluator: Obiekt FitnessEvaluator
            num_games: Liczba gier do testów
        
        Returns:
            float: Fitness score (wyższy = lepszy)
        """
        return fitness_evaluator.evaluate(individual, num_games)
    
    def selection(self, population: List[Dict], fitness_scores: List[float]) -> List[Dict]:
        """Selekcja turniejowa."""
        selected = []
        
        # Elityźm - zachowaj najlepszych
        sorted_pop = [x for _, x in sorted(zip(fitness_scores, population), reverse=True)]
        selected.extend(sorted_pop[:self.elite_size])
        
        # Selekcja turniejowa dla reszty
        for _ in range(self.population_size - self.elite_size):
            tournament = np.random.choice(len(population), size=3, replace=False)
            tournament_fitness = [fitness_scores[i] for i in tournament]
            winner_idx = tournament[np.argmax(tournament_fitness)]
            selected.append(deepcopy(population[winner_idx]))
        
        return selected
    
    def crossover(self, parent1: Dict, parent2: Dict) -> Dict:
        """Krzyżowanie jednopunktowe."""
        if np.random.random() > self.crossover_rate:
            return deepcopy(parent1)
        
        child = {}
        for param in parent1.keys():
            if np.random.random() < 0.5:
                child[param] = parent1[param]
            else:
                child[param] = parent2[param]
        
        return child
    
    def mutate(self, individual: Dict) -> Dict:
        """Mutacja gaussowska."""
        mutated = deepcopy(individual)
        
        for param, value in mutated.items():
            if np.random.random() < self.mutation_rate:
                min_val, max_val = self.param_ranges[param]
                noise = np.random.normal(0, (max_val - min_val) * 0.1)
                mutated[param] = np.clip(value + noise, min_val, max_val)
        
        return mutated
    
    def evolve(self, generations: int, fitness_evaluator, output_dir: str = "ga_results"):
        """
        Główna pętla ewolucyjna.
        
        Args:
            generations: Liczba generacji
            fitness_evaluator: Obiekt FitnessEvaluator
            output_dir: Katalog wynikowy
        """
        os.makedirs(output_dir, exist_ok=True)
        
        population = self.initialize_population()
        
        best_fitness_history = []
        avg_fitness_history = []
        
        for gen in range(generations):
            print(f"\n{'='*60}")
            print(f"Generation {gen+1}/{generations}")
            print(f"{'='*60}")
            
            # Ocena fitness
            fitness_scores = []
            for i, individual in enumerate(population):
                print(f"\nEvaluating Individual {i+1}/{self.population_size}...")
                fitness = self.evaluate_fitness(individual, fitness_evaluator, num_games=3)
                fitness_scores.append(fitness)
                print(f"  Fitness: {fitness:.2f}")
            
            # Statystyki
            best_idx = np.argmax(fitness_scores)
            best_fitness = fitness_scores[best_idx]
            avg_fitness = np.mean(fitness_scores)
            best_individual = population[best_idx]
            
            best_fitness_history.append(best_fitness)
            avg_fitness_history.append(avg_fitness)
            
            print(f"\n{'='*60}")
            print(f"Generation {gen+1} Summary:")
            print(f"  Best Fitness:    {best_fitness:.2f}")
            print(f"  Average Fitness: {avg_fitness:.2f}")
            print(f"  Worst Fitness:   {min(fitness_scores):.2f}")
            print(f"{'='*60}")
            
            # Zapisz najlepszego
            best_file = os.path.join(output_dir, f'best_gen_{gen+1:03d}.json')
            with open(best_file, 'w') as f:
                json.dump({
                    'generation': gen + 1,
                    'fitness': best_fitness,
                    'params': best_individual
                }, f, indent=2)
            
            # Selekcja
            selected = self.selection(population, fitness_scores)
            
            # Krzyżowanie i mutacja
            new_population = selected[:self.elite_size]  # Elita przechodzi bez zmian
            
            while len(new_population) < self.population_size:
                parent1 = selected[np.random.randint(len(selected))]
                parent2 = selected[np.random.randint(len(selected))]
                child = self.crossover(parent1, parent2)
                child = self.mutate(child)
                new_population.append(child)
            
            population = new_population
        
        # Zapisz historię
        history_file = os.path.join(output_dir, 'training_history.json')
        with open(history_file, 'w') as f:
            json.dump({
                'best_fitness': best_fitness_history,
                'avg_fitness': avg_fitness_history
            }, f, indent=2)
        
        print(f"\n{'='*60}")
        print("Training Complete!")
        print(f"Results saved to: {output_dir}")
        print(f"{'='*60}")
        
        return population, best_fitness_history


if __name__ == "__main__":
    print("Genetic Algorithm module")
    print("Import this module and use GeneticAlgorithm class")
