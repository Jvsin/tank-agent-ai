"""
Training Package
Zawiera moduły do treningu agenta algorytmem genetycznym.
"""

from .genetic_algorithm import GeneticAlgorithm
from .fitness_evaluator import FitnessEvaluator

__all__ = ['GeneticAlgorithm', 'FitnessEvaluator']
