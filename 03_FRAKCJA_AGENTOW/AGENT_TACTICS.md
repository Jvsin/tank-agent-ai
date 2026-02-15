# Dokumentacja Agenta i Taktyki – Symulator Walk Czołgów

Dokument dla nowego agenta LLM kontynuującego prace nad agentem czołgów.

---

## 1. Przegląd projektu

**Projekt:** Symulator Walk Czołgów (tank battle simulator)  
**Lokalizacja agenta:** `03_FRAKCJA_AGENTOW/`  
**Silnik gry:** `02_FRAKCJA_SILNIKA/`  
**Mapa domyślna:** `advanced_road_trees.csv` (20×20 kafelków, 200×200 jednostek świata)

Agent to serwer HTTP (FastAPI), wywoływany co tick przez silnik. Każdy czołg ma własny proces agenta (port 8001, 8002, …).

---

## 2. Architektura agenta

```
SmartAgent (agent.py)
├── WorldModel          – model świata (siatka, zagrożenia, dead ends)
├── GoalSelector        – wybór celów (używany przy wyłączonych checkpointach)
├── AStarPlanner        – planowanie ścieżki A*
├── MotionDriver        – sterowanie ruchem (drive_path, drive_to_point, escape)
├── FuzzyTurretController – celowanie i strzelanie (logika rozmyta)
└── checkpoints         – generowanie checkpointów przez bezpieczną glebę
```

### Pliki w `agent_core/`

| Plik | Opis |
|------|------|
| `agent.py` | Główna logika – `get_action()` zwraca `ActionCommand` |
| `checkpoints.py` | Checkpointy, spawnpoint, bezpieczna ścieżka, zasięgi amunicji |
| `driver.py` | `drive_path`, `drive_to_point`, `escape_drive`, `update_stuck` |
| `world_model.py` | Siatka komórek, `CellState`, dead ends, `powerup_cells`, `checkpoint_cells` |
| `planner.py` | A* z kosztem ruchu uwzględniającym zagrożenia |
| `goal_selector.py` | Priorytety celów (attack, powerup, explore itd.) |
| `fuzzy_turret.py` | Celowanie, wybór celu, decyzja o strzale (skfuzzy) |
| `turret.py` | `SimpleTurretController` (nieużywany) |
| `geometry.py` | `to_xy`, `euclidean_distance`, `heading_to_angle_deg`, `normalize_angle_diff` |

---

## 3. Aktualna taktyka (checkpoint-based)

### 3.1 Przepływ co tick

1. **Aktualizacja modelu** – `_update_world()` z sensorów (przeszkody, teren)
2. **Sprawdzenie zagrożeń** – `standing_on_danger`, `stuck_triggered` (gdy escape włączony)
3. **Obliczenie unikania** – `_reactive_obstacle_avoidance()`
4. **Główna logika ruchu:**
   - Tryb ucieczki (gdy włączony) → ucieczka z zagrożenia
   - **Checkpointy** → jedź do aktualnego checkpointu
5. **Wieżyczka** – celowanie w wrogów lub zniszczalne przeszkody
6. **Strzelanie** – tylko gdy wróg w zasięgu amunicji LUB gdy niszczymy przeszkody
7. **Prędkość** – zawsze `top_speed` (maksymalna)

### 3.2 A* i preferencje ścieżki

- **Powerupy** – komórki z powerupami mają koszt 0.2 (zamiast ~1.9). Delikatny objazd 1–2 komórek jest opłacalny.
- **Checkpointy** – komórki aktualnego i następnych 2 checkpointów mają koszt ×0.75. Preferowana ścieżka przez korytarz.

### 3.3 Checkpointy

**Kolejność:**
1. **Checkpoint 0** – pierwszy punkt korytarza (bezpieczna gleba)
2. **Checkpointy 1+** – dalsza ścieżka przez glebę (korytarz z mapy CSV)

**Team 1 (lewa strona):** spawnpoint → wschód (prawo)  
**Team 2 (prawa strona):** spawnpoint → zachód (lewo), checkpointy odwrócone

**Checkpointy:**
- Lista ustalana na start per zespół (`checkpoints_by_team[team]`)
- Każdy czołg śledzi swój indeks (`checkpoint_index_by_tank[tank_id]`)
- Odhaczenie: gdy w promieniu 15 jednostek → przejście do następnego checkpointu

**Bezpieczna ścieżka:**
- Mapa CSV: `02_FRAKCJA_SILNIKA/backend/maps/advanced_road_trees.csv`
- Bezpieczne tereny: Grass, Road, Swamp, PotholeRoad
- Unikane: Water, Wall, Tree, AntiTankSpike
- Wybierany jest rząd z największą liczbą bezpiecznych kafelków
- Waypointy co ~3 kolumny na tym rzędzie

**Checkpoint 0 (mapa 200×200):**
- Obie drużyny: pierwszy punkt korytarza (bezpieczna gleba) – Team 1 ~(15, 95), Team 2 ~(185, 95)
- Unika blokowania na wodzie (Team 1) i przy ścianach (Team 2)

### 3.4 Niszczenie przeszkód

Gdy czołg jest zablokowany i **nie ma wrogów w zasięgu**:
- Szuka najbliższej zniszczalnej przeszkody (`is_destructible=True`, np. Tree)
- Celuje w nią i strzela, gdy błąd celowania ≤ 4°
- Warunki: `obstacle_avoid` LUB `stuck_triggered` LUB przeszkoda < 35 jednostek

**Uwaga:** W silniku tylko **Tree** jest zniszczalne. Wall i AntiTankSpike – nie.

### 3.5 Strzelanie

- **Wróg w zasięgu** (HEAVY=25, LIGHT=50, LONG_DISTANCE=100) → strzelaj
- **Zniszczalna przeszkoda blokująca** → strzelaj
- W przeciwnym razie → nie strzelaj

---

## 4. Flagi konfiguracyjne (agent.py)

```python
DISABLE_ESCAPE_MODE = True   # True = wyłącz ucieczkę (test samo chodzenia)
```

---

## 5. API – wejście i wyjście

### Wejście (`get_action`)

```python
def get_action(
    current_tick: int,
    my_tank_status: Dict[str, Any],  # position, heading, hp, _top_speed, ammo_loaded, ...
    sensor_data: Dict[str, Any],     # seen_tanks, seen_obstacles, seen_terrains, seen_powerups
    enemies_remaining: int,
) -> ActionCommand
```

### Wyjście (`ActionCommand`)

```python
class ActionCommand(BaseModel):
    barrel_rotation_angle: float = 0.0   # obrót lufy (stopnie/tick)
    heading_rotation_angle: float = 0.0 # obrót kadłuba (stopnie/tick)
    move_speed: float = 0.0             # prędkość (obecnie zawsze top_speed)
    ammo_to_load: Optional[str] = None
    should_fire: bool = False
```

### Sensor – struktura

- `seen_tanks`: lista wrogów (position, team, tank_type, is_damaged, …)
- `seen_obstacles`: position, type, **is_destructible**
- `seen_terrains`: position, type, dmg (deal_damage)
- `seen_powerups`: position, powerup_type

---

## 6. Uruchomienie

**Silnik z grafiką:**
```bash
cd 02_FRAKCJA_SILNIKA
python engine_v1_beta.py
```

**Testy agenta:**
```bash
uv run pytest 03_FRAKCJA_AGENTOW/tests/ -v
```

**Ważne testy:**
- `test_agent_stable_drive.py` – stabilność jazdy checkpointami (tank na (50,95), heading 0)
- `test_agent_explore_no_fire.py` – brak strzału gdy wróg poza zasięgiem amunicji (LIGHT=50)
- `test_agent_hazard_escape.py` – ucieczka z zagrożeń (gdy escape włączony)
- `test_agent_combat_behavior.py` – zachowanie w walce

**Serwer agenta (pojedynczy):**
```bash
cd 03_FRAKCJA_AGENTOW
python final_agent.py --port 8001 --name Bot_1
```

**Silnik uruchamia wiele agentów:** każdy czołg ma własny proces na portach 8001–8010. Silnik wysyła POST `/agent/action` z payloadem:
```json
{
  "current_tick": 945,
  "my_tank_status": { "position": {"x": 50, "y": 95}, "heading": 0, "hp": 80, "_top_speed": 3, "ammo_loaded": "LIGHT", ... },
  "sensor_data": { "seen_tanks": [...], "seen_obstacles": [...], "seen_terrains": [...], "seen_powerups": [...] },
  "enemies_remaining": 5
}
```

---

## 7. Silnik – kolizje i fizyka

**Kolizje czołg–czołg:**
- Tak, **czołgi tego samego zespołu mogą ze sobą kolidować** – silnik nie rozróżnia drużyn
- Przy kolizji: cofnięcie do poprzedniej pozycji (rollback), brak obrażeń
- Skutek: sojusznicy mogą się blokować i „zlepiać” na wąskich ścieżkach

**Kolizje czołg–przeszkoda:** obrażenia (Tree −5 HP, Wall −10 HP, AntiTankSpike −5 HP)

---

## 8. Znane problemy i TODO

1. ~~**Czołgi na wodzie przy spawnie**~~ – obie drużyny używają pierwszego punktu korytarza (bezpieczna gleba)
2. ~~**Oscylacja przy środku mapy**~~ – planowanie A* + więcej waypointów omija Tree i ściany
3. **Kolizje sojuszników** – czołgi tego samego zespołu mogą się blokować (silnik nie ignoruje kolizji friendly)
4. **DISABLE_ESCAPE_MODE** – przy włączonej ucieczce czołgi na wodzie próbują uciec
5. **AntiTankSpike** – niezniszczalne; czołgi mogą się blokować
6. **Mapa 200×200** – `advanced_road_trees.csv` ma 20×20 kafelków; inne mapy mogą mieć inny rozmiar
7. **Koordynaty** – (0,0) lewy dolny róg, X w prawo, Y w górę

---

## 9. Zależności

- `pydantic` – ActionCommand
- `numpy`, `skfuzzy` – FuzzyTurretController
- `uv` – menedżer pakietów Pythona

---

## 10. Przydatne ścieżki

- Mapy: `02_FRAKCJA_SILNIKA/backend/maps/`
- Konfiguracja czołgów: `02_FRAKCJA_SILNIKA/backend/utils/config.py`
- Amunicja (zasięgi): `02_FRAKCJA_SILNIKA/backend/structures/ammo.py`
- Spawn: `02_FRAKCJA_SILNIKA/backend/engine/game_loop.py` – `_get_spawn_position`
- Fizyka/kolizje: `02_FRAKCJA_SILNIKA/backend/engine/physics.py` – `check_tank_tank_collision`
- Silnik graficzny: `02_FRAKCJA_SILNIKA/engine_v1_beta.py` – `TARGET_FPS`, `TICKS_PER_FRAME`
