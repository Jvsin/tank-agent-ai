"""
Przykładowy skrypt do sparingu agenta z random_agent
Uruchamia oba agenty i silnik gry.
"""

import subprocess
import time
import sys
import os

def start_process(command, name):
    """Uruchamia proces w tle."""
    print(f"[*] Uruchamianie {name}...")
    process = subprocess.Popen(
        command,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    return process

def main():
    print("="*70)
    print("AUTOMATYCZNY SPARING")
    print("="*70)
    print()
    
    processes = []
    
    try:
        # 1. Uruchom inteligentnego agenta
        intelligent_cmd = "python intelligent_agent.py --port 8001 --name SmartBot"
        p1 = start_process(intelligent_cmd, "Intelligent Agent (port 8001)")
        processes.append(p1)
        time.sleep(2)
        
        # 2. Uruchom random agenta
        random_cmd = "python random_agent.py --port 8002 --name RandomBot"
        p2 = start_process(random_cmd, "Random Agent (port 8002)")
        processes.append(p2)
        time.sleep(2)
        
        # 3. Uruchom grę
        print("\n[*] Agenci gotowi! Uruchamianie gry...")
        print("[*] Naciśnij Ctrl+C aby zatrzymać\n")
        
        game_dir = os.path.join(os.path.dirname(__file__), '..', '02_FRAKCJA_SILNIKA')
        game_cmd = f"cd {game_dir} && python run_game.py"
        
        # Ta komenda zablokuje wykonanie
        subprocess.run(game_cmd, shell=True)
        
    except KeyboardInterrupt:
        print("\n\n[!] Przerwano przez użytkownika")
    
    finally:
        print("\n[*] Zatrzymywanie procesów...")
        for p in processes:
            p.terminate()
        
        print("[✓] Gotowe!")


if __name__ == "__main__":
    main()
