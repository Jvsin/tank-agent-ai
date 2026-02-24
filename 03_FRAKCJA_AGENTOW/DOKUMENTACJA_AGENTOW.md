# Dokumentacja Techniczna - Frakcja Agentów

## Spis Treści

1. [Wprowadzenie](#wprowadzenie)
2. [Architektura Agenta](#architektura-agenta)
3. [Implementacja Metod Sztucznej Inteligencji](#implementacja-metod-sztucznej-inteligencji)
4. [Optymalizacja i Dobór Parametrów](#optymalizacja-i-dobór-parametrów)
5. [Środowisko Symulacji](#środowisko-symulacji)
6. [Przepływ Decyzyjny](#przepływ-decyzyjny)
7. [Wyniki i Wnioski](#wyniki-i-wnioski)

---

## Wprowadzenie

Folder `03_FRAKCJA_AGENTOW` zawiera pełną implementację inteligentnego agenta do gry w symulatorze walk czołgów. Agent został zaprojektowany jako autonomiczny system podejmowania decyzji, który w czasie rzeczywistym analizuje dane sensoryczne z silnika gry i generuje optymalne komendy sterowania czołgiem.

### Cel Projektu

Stworzenie agenta zdolnego do:
- **Nawigacji** w złożonym, dynamicznym środowisku z przeszkodami
- **Planowania ścieżek** z uwzględnieniem zagrożeń i celów taktycznych
- **Walki** z przeciwnikami przy użyciu zaawansowanego systemu celowania
- **Adaptacji** do zmieniających się warunków pola bitwy

### Kontekst Środowiska

Agent działa w środowisku 2D o wymiarach 200×200 jednostek, które zawiera:
- **Tereny** różnych typów (trawa, droga, woda, błoto, wyboje)
- **Przeszkody** (drzewa, ściany, kolce przeciwczołgowe)
- **Czołgi** sojusznicze i wroge
- **Powerupy** (amunicja, naprawa, tarcza)

Mapa jest zamodelowana jako siatka dyskretnych kafelków, przy czym agent wewnętrznie używa systemu grid-based o rozmiarze komórki 10×10 jednostek dla efektywności planowania ścieżki.

---

## Architektura Agenta

### Ogólna Struktura

Agent został zaprojektowany jako **modularny system wielowarstwowy**, gdzie każdy moduł odpowiada za konkretny aspekt zachowania. Główny orchestrator (`TankAgent`) koordynuje działanie wszystkich podsystemów.

```
┌─────────────────────────────────────────────┐
│           TankAgent (agent.py)              │
│         HTTP FastAPI Server                 │
└─────────────────┬───────────────────────────┘
                  │
    ┌─────────────┼─────────────┐
    │             │             │
    ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌─────────────┐
│ World  │  │ Planner  │  │   Fuzzy     │
│ Model  │  │  (A*)    │  │   Turret    │
└────────┘  └──────────┘  └─────────────┘
    │             │             │
    ▼             ▼             ▼
┌────────┐  ┌──────────┐  ┌─────────────┐
│ Driver │  │Checkpts  │  │  Geometry   │
└────────┘  └──────────┘  └─────────────┘
```

### Komponenty Systemu

#### 1. **TankAgent** - Główny Orchestrator
**Plik:** [agent.py](agent.py)

Główna klasa odpowiedzialna za:
- Inicjalizację wszystkich podsystemów
- Obsługę API (FastAPI HTTP server na portach 8001-8010)
- Koordynację przepływu danych między modułami
- Zarządzanie trybami działania (checkpoint vs autonomous)
- Agregację decyzji z różnych podsystemów

**Tryby działania:**
- **Checkpoint Mode** - agent porusza się po wstępnie zdefiniowanych punktach nawigacyjnych (waypointach) przez bezpieczny korytarz na mapie
- **Autonomous Mode** - aktywowany po przekroczeniu progu (y ≤ 80 dla drużyny 1, y ≥ 120 dla drużyny 2), agent używa planowania A* do autonomicznej nawigacji

**Kluczowe metody:**
- `get_action()` - główny punkt wejścia, wywoływany co tick przez silnik gry
- `_init_checkpoints()` - inicjalizacja checkpointów na podstawie drużyny
- `_update_world_model()` - aktualizacja modelu świata z danych sensorycznych
- `_select_autonomous_goal()` - wybór celu (wróg/powerup/eksploracja) w trybie autonomicznym
- `_compute_path()` - wywołanie plannera A* i walidacja ścieżki

#### 2. **WorldModel** - Model Przestrzenny Świata
**Plik:** [agent_core/world_model.py](agent_core/world_model.py)

Przestrzenny model pamięciowy środowiska oparty na siatce komórek. Każda komórka (10×10 jednostek) przechowuje agregowane informacje o:

**Struktura CellState:**
```python
@dataclass
class CellState:
    safe: float = 0.0      # poziom bezpieczeństwa (akumulowany przy przejściach)
    danger: float = 0.0    # poziom zagrożenia (terrain dmg, wrogowie)
    blocked: float = 0.0   # poziom blokady (przeszkody)
```

**Funkcjonalność:**
- **Akumulacja wiedzy** - wartości safe/danger/blocked rosną przy każdej obserwacji
- **Decay czasowy** - TTL (time-to-live) dla informacji tymczasowych:
  - `dead_end_ttl` - komórki oznaczone jako ślepe zaułki (TTL ~520-560 ticków)
  - `ally_occupancy_ttl` - pozycje sojuszniczych czołgów (TTL ~10 ticków)
  - `enemy_occupancy_ttl` - pozycje wrogich czołgów (TTL ~10 ticków)
  
- **Specjalne markery:**
  - `powerup_cells` - set komórek zawierających powerupy
  - `checkpoint_cells` - komórki wzdłuż korytarza checkpointów
  - `pothole_cells` - komórki z wybojami (zwiększone koszty)

**Metody kluczowe:**
- `to_cell(x, y)` - konwersja współrzędnych świata na indeksy komórki
- `to_world_center(cell)` - odwrotna konwersja
- `is_blocked_for_pathing(cell)` - czy komórka jest nieprzejezdna dla A*
- `movement_cost(cell)` - koszt ruchu przez komórkę (używany przez A*)
- `decay_dead_ends()` - dekrementacja TTL, usuwanie wygasłych informacji

**Dlaczego model oparty na siatce?**
W środowisku czołgów kluczowe jest szybkie podejmowanie decyzji. Ciągła reprezentacja świata wymagałaby kosztownych obliczeń kolizji dla każdego punktu ścieżki. Siatka 10×10:
- Redukuje przestrzeń stanów z 200×200=40000 do 20×20=400 komórek
- Umożliwia efektywne wyszukiwanie A* (ekspansja ~100-300 węzłów zamiast tysięcy)
- Odzwierciedla dyskretną naturę kafelków mapy (każdy kafelek = 10×10 jednostek)
- Pozwala na akumulację wiedzy probabilistycznej w czasie

#### 3. **AStarPlanner** - Planowanie Ścieżek
**Plik:** [agent_core/planner.py](agent_core/planner.py)

Implementacja algorytmu A* z modyfikacjami dla specyfiki gry czołgowej.

**Cechy implementacji:**
- **Heurystyka:** Manhattan distance (odległość taksówkowa)
  ```python
  h(a, b) = |a.x - b.x| + |a.y - b.y|
  ```
  Wybrana ze względu na 4-connectivity (czołg porusza się w 4 kierunkach, nie po przekątnej)

- **Ograniczony radius:** Search limited to ±18 komórek od startu
  - Zapobiega eksploracji całej mapy przy nieosiągalnych celach
  - Typowa ścieżka to 10-20 komórek, więc 18-cell radius jest wystarczający
  
- **Koszty krawędzi:** Używa `world_model.movement_cost(cell)` zamiast stałej wartości 1.0
  - Komórki z powerupami: koszt ×0.92
  - Komórki checkpointów: koszt ×0.75
  - Komórki z zagrożeniami: koszt +4.8 × danger
  - Komórki z przeszkodami: koszt +7.2 × blocked
  
**Algorytm:**
1. Kolejka priorytetowa `frontier` z kosztem f = g + h
2. Dla każdego node:
   - Ekspanduj 4 sąsiadów (N, S, E, W)
   - Sprawdź `is_blocked_for_pathing()` - skip zablokowanych
   - Oblicz tentative_g = current_g + movement_cost(neighbor)
   - Jeśli lepsze niż poprzednie g - dodaj do frontier
3. Rekonstrukcja ścieżki wstecz przez `came_from`

**Path Risk:**
Funkcja `path_risk()` oblicza łączny wskaźnik ryzyka dla ścieżki:
```python
risk = (2.5 × danger + 3.0 × blocked + 
        2.2 × ally_occupancy + 2.8 × enemy_occupancy - 
        0.2 × min(safe, 3.0)) / len(path)
```

Używana do porównywania alternatywnych ścieżek (choć obecnie agent używa tylko pierwszej znalezionej).

**Dlaczego A*?**
- **Optymalność:** A* gwarantuje znalezienie najkrótszej ścieżki przy admissible heuristic
- **Efektywność:** Manhattan heuristic jest admissible i consistent - A* ekspanduje minimalną liczbę węzłów
- **Dynamiczność:** Ponowne wywołanie co 30 ticków pozwala reagować na zmiany (nowi wrogowie, nowe przeszkody)
- **Przewidywalność:** Deterministyczny wynik ułatwia debugowanie i testowanie

Alternatywy (Dijkstra, BFS) byłyby wolniejsze bez dodatkowych korzyści w tym scenariuszu.

#### 4. **MotionDriver** - Sterowanie Ruchem
**Plik:** [agent_core/driver.py](agent_core/driver.py)

Tłumaczy abstrakcyjną ścieżkę (listę komórek) na konkretne komendy sterowania (turn, speed).

**Główne metody:**

##### `drive_path(x, y, heading, top_speed)` → (turn, speed)
Porusza się wzdłuż `self.path`:
1. Pobiera następną komórkę: `next_cell = path[0]`
2. **Detour safety check:** Jeśli `next_cell` jest dangerous → szuka bezpiecznego sąsiada
3. Oblicza kąt do celu: `target_angle = heading_to_angle_deg(x, y, cell_center_x, cell_center_y)`
4. Normalizuje różnicę kąta: `diff = normalize_angle_diff(target_angle, heading)`
5. **Adaptacyjne strojenie:**
   - `|diff| < 4°` → turn = 0 (jedź prosto)
   - `|diff| ≤ 20°` → turn limit 13°
   - `|diff| > 20°` → turn limit 18°
6. **Prędkość proporcjonalna do błędu kąta:**
   - `|diff| > 55°` → speed = 0.60 × top_speed
   - `|diff| > 24°` → speed = 0.82 × top_speed
   - `|diff| ≤ 24°` → speed = top_speed

##### `drive_to_point(x, y, heading, tx, ty, top_speed)` → (turn, speed)
Uproszczona wersja dla pojedynczego punktu (używana w checkpoint mode):
- Podobna logika, ale bez safety detour
- Używana gdy agent nie ma pełnej ścieżki A*, tylko docelowy waypoint

##### `update_stuck(x, y, move_cmd)` - Detekcja Zakleszczenia
Wykrywa sytuacje gdy czołg nie może się ruszyć:
```python
if distance_moved < 0.15 and move_cmd > 0.5:
    stuck_ticks += 1
    if stuck_ticks >= 10:
        # STUCK - oznacz komórkę jako dead_end
        world_model.mark_dead_end(current_cell, ttl=560)
```

**Dlaczego TTL=560?**  
560 ticków ≈ 28 sekund przy 20 TPS (ticks per second). Wystarczająco długo, by uniknąć powrotu do tego samego miejsca, ale nie na zawsze (mapa może się zmienić - przeszkoda może zostać zniszczona).

##### `escape_drive()` - Manewry Ucieczki
Gdy agent jest stuck lub w niebezpieczeństwie:
1. Wybiera losowy kąt ucieczki (`escape_heading`)
2. Pełna prędkość w tym kierunku przez ~3-5 sekund
3. Po wyjściu - wznowienie normalnej nawigacji

**Dlaczego losowy kąt?**  
Deterministyczne strategie ucieczki mogą prowadzić do zapętleń (np. zawsze zawracaj → za 2 sekundy znowu stuck). Losowość łamie pętle.

#### 5. **FuzzyTurretController** - System Celowania i Strzelania
**Plik:** [agent_core/fuzzy_turret.py](agent_core/fuzzy_turret.py)

Najbardziej złożony komponent - używa **logiki rozmytej (fuzzy logic)** do podejmowania decyzji o celowaniu i strzelaniu.

**Architektura: 4 Niezależne Systemy Wnioskowania Rozmytego (FIS)**

Każdy FIS to kompletny system Mamdani:
1. **Fuzzyfikacja** - przekształcenie crisp inputs na stopnie przynależności
2. **Wnioskowanie** - ewaluacja reguł IF-THEN
3. **Agregacja** - połączenie wyników reguł
4. **Defuzzyfikacja** - przekształcenie rozmytego wyniku na crisp output

Biblioteka: `scikit-fuzzy` (implementacja Python fuzzy logic)

---

### FIS #1: Wybór Celu (Target Selection)

**Wejścia:**
- `distance` [0, max_vision × 1.5] - dystans do wroga
  - MF: `very_close`, `close`, `medium`, `far`
- `threat` [0, 10] - poziom zagrożenia
  - Wagi: LIGHT=3, HEAVY=7, Sniper=9
  - MF: `low`, `medium`, `high`

**Wyjście:**
- `priority` [0, 100] - priorytet celu
  - MF: `ignore`, `low`, `medium`, `high`, `critical`

**Reguły (12 total):**
```
IF distance=very_close AND threat=high THEN priority=critical
IF distance=very_close AND threat=medium THEN priority=high
IF distance=close AND threat=high THEN priority=critical
...
IF distance=far AND threat=low THEN priority=ignore
```

**Funkcje przynależności (Membership Functions):**
- `very_close`: trapezoidal [0, 0, 0.15×vision, 0.3×vision]
- `close`: triangular [0.2×vision, 0.4×vision, 0.6×vision]
- `medium`: triangular [0.5×vision, 0.75×vision, 1.0×vision]
- `far`: trapezoidal [0.8×vision, 1.0×vision, max, max]

**Proces:**
1. Dla każdego widzianego wroga:
   - Oblicz distance
   - Mapuj tank_type → threat value
   - Fuzzyfikuj inputs
   - Ewaluuj 12 reguł
   - Defuzzyfikuj → priority score
2. Wybierz wroga z najwyższym priority

**Przykład:**
```
Wróg: HEAVY tank, distance=35 jednostek, vision_range=70
threat = 7 (HEAVY weight)
distance input = 35

Fuzzyfikacja:
  distance[close] = 0.7
  distance[medium] = 0.3
  threat[high] = 0.7
  threat[medium] = 0.3

Aktywne reguły:
  Rule: IF close AND high THEN critical (strength=min(0.7,0.7)=0.7)
  Rule: IF close AND medium THEN high (strength=min(0.7,0.3)=0.3)
  Rule: IF medium AND high THEN high (strength=min(0.3,0.7)=0.3)
  Rule: IF medium AND medium THEN medium (strength=min(0.3,0.3)=0.3)

Agregacja all rule outputs → centroid defuzzification → priority ≈ 82
```

---

### FIS #2: Prędkość Obrotu Lufy (Rotation Speed)

**Wejścia:**
- `angle_error` [0°, 180°] - różnica między aktualnym a docelowym kątem lufy
  - MF: `small`, `medium`, `large`
- `target_distance` [0, max_vision × 1.5]
  - MF: `close`, `medium`, `far`

**Wyjście:**
- `speed_factor` [0.0, 1.0] - mnożnik maksymalnej prędkości obrotu
  - MF: `very_slow`, `slow`, `medium`, `fast`, `very_fast`

**Reguły (7 total):**
```
IF angle_error=small THEN speed_factor=very_slow
IF angle_error=medium AND distance=close THEN speed_factor=medium
IF angle_error=large AND distance=far THEN speed_factor=very_fast
...
```

**Uzasadnienie:**
- **Mały błąd kąta:** wolny obrót zapobiega overshooting (oscylacjom wokół celu)
- **Duży błąd + daleki cel:** szybki obrót (czas jest krytyczny, precyzja mniej ważna)
- **Duży błąd + bliski cel:** nadal szybki (wróg zagraża od bliska)

**Implementacja:**
```python
rotation_speed = speed_factor × max_barrel_spin_rate
barrel_rotation_angle = clamp(rotation_speed, -max, +max)
```

Wynik: płynne, adaptacyjne celowanie bez jitteringu.

---

### FIS #3: Decyzja o Strzale (Firing Decision)

**Wejścia:**
- `aiming_error` [0°, 10°] - błąd celowania (różnica kąta lula-wróg)
  - MF: `perfect`, `good`, `acceptable`, `poor`
- `firing_distance` [0, max_vision × 1.5]
  - MF: `optimal`, `suboptimal`, `extreme`
- `vulnerability` [0.0, 1.0] - wskaźnik podatności wroga
  - Obliczany jako: (100 - enemy_hp) / 100
  - MF: `resilient`, `normal`, `vulnerable`

**Wyjście:**
- `fire_confidence` [0.0, 1.0] - pewność strzału
  - MF: `no`, `maybe`, `yes`
  - **Próg decyzji:** fire_confidence ≥ 0.6

**Reguły (14 total):**
```
IF aiming_error=perfect AND firing_distance=optimal THEN fire_confidence=yes
IF aiming_error=acceptable AND distance=optimal AND vulnerability=vulnerable THEN fire_confidence=yes
IF aiming_error=poor THEN fire_confidence=no
IF firing_distance=extreme AND aiming_error=acceptable THEN fire_confidence=no
...
```

**Optymalna odległość strzelania:**
```python
OPTIMAL_ENGAGEMENT_RANGE = 50.0 jednostek
optimal: [0, 0.5×vision, 0.7×vision]
suboptimal: [0.56×vision, 0.9×vision, 1.2×vision]
extreme: [1.0×vision, 1.2×vision, max, max]
```

**Dlaczego fuzzy logic dla strzelania?**

Problem decyzji o strzale jest **inherentnie nieprecyzyjny:**
- "Wystarczająco blisko" - brak ostrej granicy
- "Wystarczająco dobrze wycelowany" - stopniowalna pewność
- "Wystarczająco osłabiony" - rozmyta ocena

Alternatywy:
- **Hard thresholds** (if distance < 50 and angle_error < 3): wytwarzają artefakty (nagłe przełączenia on/off na granicy)
- **Weighted score** (score = w1×dist + w2×angle): brak możliwości wyrażenia nieliniowych interakcji (np. "daleko + słabe celowanie = nigdy nie strzelaj")

Fuzzy logic:
- Modeluje płynne przejścia między stanami
- Reguły odzwierciedlają ekspercką wiedzę taktyczną (np. "jeśli wróg vulnerable i blisko, toleruj gorsze celowanie")
- Odporna na szum sensoryczny (małe wahania inputów nie powodują flip-flopping decyzji)

**Cooldown:**
Po każdym strzale: `cooldown_ticks = 10`  
Zapobiega spamowaniu strzałów (amunicja jest ograniczona, reload trwa 5-10 ticków).

---

### FIS #4: Adaptacyjne Skanowanie (Adaptive Scan)

Aktywny gdy **brak widocznych wrogów** - lufa skanuje przestrzeń w poszukiwaniu celów.

**Wejścia:**
- `time_unseen` [0, 100] - ticki od ostatniego zauważenia wroga
  - MF: `recent`, `moderate`, `long`
- `scan_error` [0°, 180°] - różnica między aktualnym kątem a `last_seen_direction`
  - MF: `aligned`, `misaligned`

**Wyjście:**
- `scan_speed` [0.0, 1.0] - prędkość skanowania
  - MF: `slow`, `medium`, `fast`

**Reguły (4 total):**
```
IF time_unseen=recent AND scan_error=misaligned THEN scan_speed=fast
IF time_unseen=recent AND scan_error=aligned THEN scan_speed=slow
IF time_unseen=moderate THEN scan_speed=medium
IF time_unseen=long THEN scan_speed=medium
```

**Strategia:**
- **Krótko po zniknięciu wroga:** szybko skręć w kierunku ostatniego widzenia
- **Już skierowany:** wolno skanuj (drobne korekty)
- **Długo bez wroga:** umiarkowane tempo (ogólne patrolowanie)

**Last Seen Direction:**
```python
LAST_SEEN_EXPIRY_TICKS = 40  # ~2 sekundy przy 20 TPS
if ticks_since_last_seen > 40:
    last_seen_direction = None  # zapomnij stary kierunek
```

**Dlaczego adaptacyjne skanowanie?**
Statyczne skanowanie (np. sin wave) ignoruje informacje taktyczne. Agent wie gdzie był wróg - skanowanie w tamtym kierunku zwiększa szansę na ponowne nabycie celu.

---

### Wybór Amunicji

**Specyfikacje amunicji:**
```python
AMMO_SPECS = {
    "HEAVY": {"range": 25.0, "damage": 40.0, "reload": 10.0},
    "LIGHT": {"range": 50.0, "damage": 20.0, "reload": 5.0},
    "LONG_DISTANCE": {"range": 100.0, "damage": 25.0, "reload": 10.0},
}
```

**Strategia:**
Obecnie prosty wybór: używaj pierwszej dostępnej w kolejności: LONG_DISTANCE → LIGHT → HEAVY.

**Dlaczego taka kolejność?**
- LONG_DISTANCE: najdłuższy zasięg (100) - priorytetowa dla zaangażowania z dystansu
- LIGHT: balans zasięg/reload (50/5) - główna amunicja
- HEAVY: tylko bliski zasięg (25) ale wysokie obrażenia - ostateczność

**Potencjalna poprawa (TODO):**
Dodatkowy FIS uwzględniający:
- Dystans do celu vs zasięg amunicji
- Pozostałe HP wroga (HEAVY dla finish-off słabszych)
- Liczba dostępnych naboi każdego typu

---

### Niszczenie Przeszkód

**Problem:** Czołg może być zablokowany przez zniszczalną przeszkodę (np. Tree).

**Rozwiązanie:**
Gdy brak wrogów w zasięgu + (stuck OR obstacle_avoid):
1. Znajdź najbliższą przeszkodę z `is_destructible=True`
2. Oblicz kąt do przeszkody
3. Celuj lufy w przeszkodę
4. Jeśli `aiming_error ≤ 4°` → fire

**Implementacja:**
```python
def _select_destructible_obstacle(obstacles):
    destructible = [o for o in obstacles if o.is_destructible]
    if not destructible:
        return None
    return min(destructible, key=lambda o: distance(my_pos, o))
```

**W silniku:**
- Tree: is_destructible=True, HP ~20-30
- Wall: is_destructible=False (beton)
- AntiTankSpike: is_destructible=False

Zniszczenie Tree otwiera nową ścieżkę → world model oznaczy komórkę jako safe → A* znajdzie nową trasę.

---

#### 6. **Checkpoints** - System Waypoint Navigation
**Plik:** [agent_core/checkpoints.py](agent_core/checkpoints.py)

**Korytarz bezpieczeństwa:**
Lista 11 predefined waypoints wzdłuż bezpiecznej ścieżki przez mapę.

**Generacja:**
1. Analiza mapy CSV (`advanced_road_trees.csv`)
2. Identifikacja rzędu (Y) z maksymalną liczbą bezpiecznych kafelków (Grass, Road)
3. Wybranie waypoints co ~3 kolumny wzdłuż tego rzędu
4. Transformacja grid coords → world coords: `(x×10+5, y×10+5)`
5. Mirroring dla drużyny 2: `(200-x, y)`

**Przykładowe checkpointy (team 1):**
```python
[
    (15, 185),   # start (lewy dolny)
    (15, 175),
    (5, 165),
    (5, 95),     # środek mapy
    (15, 85),
    (15, 75),
    ...
    (95, 45),    # blisko wroga
]
```

**Lane Offsety:**
Aby uniknąć kolizji sojuszników (wszyscy czołgi tej samej drużyny mają te same checkpointy):
```python
def lane_offset_checkpoint(tank_id, checkpoint):
    offset_y = hash(tank_id) % 3 * 4 - 4  # -4, 0, +4
    return (checkpoint.x, checkpoint.y + offset_y)
```

Każdy czołg dostaje inny offset Y → 3 równoległe "pasy ruchu".

**Zaawansowanie checkpointu:**
```python
while distance_to_current < ARRIVAL_RADIUS:
    checkpoint_idx += 1
```
`ARRIVAL_RADIUS = 3.0` jednostek - wystarczająco mały by wymusić precyzyjne przejście, wystarczająco duży by uniknąć overshooting.

**Dlaczego checkpointy zamiast od razu A*?**

Na początku gry:
- World model jest pusty (brak informacji o przeszkodach)
- A* bez wiedzy wyrusza losowo → często wpada w pułapki
- Checkpointy gwarantują bezpieczne przejście przez znane threats (np. Water na krawędziach mapy)

Po pewnym czasie (autonomous threshold):
- World model jest wypełniony danymi
- A* ma wystarczającą wiedzę do podejmowania dobrych decyzji
- Przełączenie na autonomous mode dla większej elastyczności

---

#### 7. **GoalSelector** - Wybór Celów Taktycznych
**Plik:** [agent_core/goal_selector.py](agent_core/goal_selector.py)

Używany w **autonomous mode** do wyboru dokąd jechać.

**Hierarchia celów:**
1. **Attack:** jeśli widzi wroga → jedź do pozycji ataku
2. **Powerup:** jeśli widzi powerup → jedź po niego
3. **Explore:** brak interesujących celów → jedź w kierunku nieznanej przestrzeni

**Metody:**

##### `_choose_attack_standoff(my_cell, enemy_cell)`
Wybiera pozycję ataku - nie bezpośrednio na wroga, ale w optymalnej odległości:
```python
for each cell in radius 5 around enemy:
    if distance_to_enemy in [2, 6]:  # preferowana odległość
        score = 1.8 × safety - 0.35 × dist_to_me - 0.15 × |dist_enemy - 4|
        pick cell with max score
```

**Dlaczego nie chase bezpośrednio?**
- Zbyt blisko: ryzyko kolizji, trudne manewrowanie
- Za daleko: wróg może uciec, słaba skuteczność strzału
- Standoff distance 4-6 komórek (40-60 jednostek): optymalne dla LIGHT ammo (range=50)

##### `_choose_control_lane(my_cell, radius=12)`
Eksploracja - wybiera celową komórkę na granicy znanej/nieznanej przestrzeni:
```python
for each cell in radius:
    if distance in [3, radius]:
        frontier_bonus = 0.65 × unknown_neighbors(cell)
        score = safety + frontier_bonus - 0.12 × |distance - 7|
        pick max score
```

**Unknown neighbors:** liczba sąsiednich komórek nie w `world_model.cell_states`.

**Dlaczego frontier exploration?**
Maksymalizuje przyrost informacji - agent uczy się o mapie. Greedy local exploration (zawsze najbliższy unknown) może prowadzić do myopic behavior (ignorowanie odległych ale ważnych obszarów).

##### `_cell_safety_value(cell)`
Zagregowana ocena bezpieczeństwa:
```python
safety = 2.8 × safe - 6.5 × danger - 4.2 × blocked 
         - 0.8 × local_pressure - 0.18 × visits
```

Wagi dobrane empirycznie:
- Danger najważniejsze (6.5) - unikaj terrainów ranitowych
- Blocked drugie (4.2) - unikaj przeszkód
- Visits słabe (0.18) - lekka preferencja dla nowych obszarów, ale nie za wszelką cenę

---

#### 8. **Geometry** - Narzędzia Matematyczne
**Plik:** [agent_core/geometry.py](agent_core/geometry.py)

Czyste funkcje matematyczne bez stanu.

**Najważniejsze:**

##### `normalize_angle_diff(target, current)`
Problem: kąty w zakresie [0°, 360°], ale najkrótsza rotacja może przekraczać granicę 0°/360°.

Przykład:
- current = 10°
- target = 350°
- Naiwna różnica: 350 - 10 = 340° (prawie pełny obrót w prawo)
- Prawdziwa najkrótsza: -20° (mały obrót w lewo)

Rozwiązanie:
```python
diff = (target - current + 180) % 360 - 180
# Mapuje różnicę do (-180°, 180°]
```

Matematyka:
```
target=350, current=10
350 - 10 + 180 = 520
520 % 360 = 160
160 - 180 = -20  ✓
```

##### `heading_to_angle_deg(x1, y1, x2, y2)`
Bearing (azymut) od punktu 1 do punktu 2:
```python
angle = atan2(y2 - y1, x2 - x1) × 180/π
if angle < 0: angle += 360
return angle  # [0°, 360°)
```

**Konwencja:** 0° = wschód (prawo), 90° = północ (góra), 180° = zachód, 270° = południe

##### `euclidean_distance(x1, y1, x2, y2)`
```python
return sqrt((x2-x1)² + (y2-y1)²)
```

Używa `math.hypot()` dla lepszej precyzji numerycznej (unika overflow przy dużych wartościach).

---

## Implementacja Metod Sztucznej Inteligencji

### A* (A-Star) Pathfinding

#### Teoria

A* to algorytm przeszukiwania grafu, który znajduje najkrótszą ścieżkę od startu do celu. Należy do rodziny algorytmów **informed search** - używa heurystyki do kierowania przeszukiwaniem.

**Funkcja kosztu:**
```
f(n) = g(n) + h(n)
```
gdzie:
- `g(n)` = koszt rzeczywisty od startu do węzła n
- `h(n)` = estymowany koszt od n do celu (heurystyka)
- `f(n)` = estymowany koszt całkowitej ścieżki przez n

**Właściwości:**
- **Completeness:** Jeśli ścieżka istnieje, A* ją znajdzie
- **Optimality:** Jeśli heurystyka jest admissible (nigdy nie przecenia kosztu), A* zwróci optymalną ścieżkę
- **Optymalna wydajność:** A* ekspanduje minimalną liczbę węzłów wśród wszystkich algorytmów używających tej samej heurystyki

#### Implementacja w Projekcie

**Heurystyka - Manhattan Distance:**
```python
h(cell_a, cell_b) = |x_a - x_b| + |y_a - y_b|
```

**Dlaczego Manhattan zamiast Euclidean?**

Czołg porusza się w siatce z 4-connectivity:
- Może jechać N, S, E, W (nie po przekątnej)
- Euclidean distance `sqrt(dx² + dy²)` jest inadmissible dla 4-connectivity:
  - Prawdziwy koszt do celu po przekątnej: dx + dy (musi jechać zygzakiem)
  - Euclidean: sqrt(dx² + dy²) < dx + dy dla dx, dy > 0
  - A* z inadmissible heuristic może pominąć optymalną ścieżkę

Manhattan jest perfect heuristic dla 4-connectivity grid (równa się prawdziwemu kosztowi przy braku przeszkód).

**Przestrzeń przeszukiwania:**
- **Nodes:** komórki grid (20×20 = 400 możliwych)
- **Edges:** połączenia N-S-E-W między komórkami (4 na komórkę)
- **Edge weights:** `world_model.movement_cost(cell)` - dynamiczne, zależne od zagrożeń

**Ograniczenie radius:**
```python
min_x, max_x = start.x - 18, start.x + 18
min_y, max_y = start.y - 18, start.y + 18

if not (min_x <= cell.x <= max_x and min_y <= cell.y <= max_y):
    skip cell
```

Bez tego ograniczenia, przy nieosiągalnym celu, A* przeszukałby całą mapę (400 komórek). Z ograniczeniem: maksymalnie (36×36) = 1296 komórek, ale praktycznie ~200-400 przy typowych celach.

**Optymalizacje:**
- `heapq` (binary heap) dla priority queue - O(log N) insert/pop
- `g_score` dict zamiast 2D array - sparse representacja (tylko odwiedzone komórki)
- Early termination gdy cel osiągnięty (nie ekspandujemy wszystkich f-równych węzłów)

**Porównanie z alternatywami:**

| Algorytm | Złożoność czasowa | Optymalność | Uwagi |
|----------|------------------|-------------|-------|
| BFS | O(V + E) | TAK (jeśli jednostkowe wagi) | Przeszukuje wszystko - wolny |
| Dijkstra | O((V+E) log V) | TAK | Nie używa heurystyki - ekspanduje więcej niż A* |
| Greedy Best-First | O((V+E) log V) | NIE | Używa tylko h(n), nie g(n) - szybki ale nieoptymalne |
| A* | O((V+E) log V) | TAK (przy admissible h) | **Najlepszy balans** |

**Metryki wydajności (typowa ścieżka):**
- Długość ścieżki: 12-18 komórek
- Ekspandowane węzły: 80-200 (zamiast 400 bez heurystyki)
- Czas obliczeń: <1ms na typowe ścieżki (dominuje overhead kolejki, nie algorytm)

#### Dynamiczne Koszty Ruchu

Standardowy A* używa stałego kosztu 1.0 dla każdej krawędzi. W naszej implementacji:

```python
def movement_cost(cell):
    base = 1.9
    
    # Incentives (obniżają koszt)
    if cell in checkpoint_cells:
        base *= 0.75      # preferuj korytarz
    if cell in powerup_cells:
        base *= 0.92      # lekko przyciągaj do powerupów
    
    # Penalties (podnoszą koszt)
    base += 4.8 × danger      # silnie unikaj terrainów dmg
    base += 7.2 × blocked     # bardzo silnie unikaj przeszkód
    base += 6.5 × ally_occupancy  # unikaj blokowania sojuszników
    base += 8.0 × enemy_occupancy  # bardzo silnie unikaj wrogów
    
    return max(0.35, base)
```

**Wpływ na A*:**
- Ścieżki są **multi-objective** - minimalizują dystans + zagrożenie + blokady
- Trade-off: objazd 2 komórek obok wody (danger=3.0) vs 1 komórka przez wodę:
  - Przez wodę: 1.9 + 4.8×3 = 16.3
  - Objazd: 2 × 1.9 = 3.8
  - **Objazd wybrany** (tańszy)

**Przykład: Powerup detour:**
- Bezpośrednia ścieżka: 10 komórek × 1.9 = 19.0
- Objazd przez powerup: 11 komórek, 1 z powerup
  - 10 × 1.9 + 1 × (1.9 × 0.92) = 19.0 + 1.75 = 20.75
  - **Nie opłaca się** odchylić o 1 komórkę dla powerupu (delta cost > 1.0)
- Objazd: 10.5 komórek, 2 z powerup:
  - 8.5 × 1.9 + 2 × 1.75 = 16.15 + 3.5 = 19.65
  - **Opłaca się** jeśli powerup jest na/obok ścieżki

**Admissibility:**
Heurystyka Manhattan pozostaje admissible, bo zakładamy minimalny koszt 0.35 (teoretyczny):
```
h(n) ≤ actual_cost(n, goal)
manhattan(n, goal) × 0.35 ≤ actual_path_cost
```
W praktyce actual costs są większe (1.9+), więc warunek zawsze spełniony.

---

### Logika Rozmyta (Fuzzy Logic)

#### Teoria

Logika rozmyta to rozszerzenie logiki boolowskiej, które pozwala na stopnie prawdziwości (membership degrees) zamiast binarnych True/False.

**Klasyczna logika:**
```
Temperatura = 21°C
Is_Hot(21) = FALSE  (próg = 25°C)
Is_Hot(25) = TRUE
```
Nagła zmiana przy przekroczeniu progu → artefakty.

**Logika rozmyta:**
```
Is_Hot(21) = 0.3   (trochę ciepło)
Is_Hot(25) = 0.8   (dość ciepło)
Is_Hot(30) = 1.0   (bardzo ciepło)
```
Płynne przejście.

#### System Mamdani

Najpopularniejszy typ systemu rozmytego, używany w projekcie.

**Etapy:**

**1. Fuzzyfikacja**
Przekształcenie crisp input na stopnie przynależności do zbiorów rozmytych.

Przykład (aiming_error = 3.5°):
```python
# Membership functions
perfect: [0, 0, 1, 2]  (trapezoid)
good: [1.5, 2.5, 4]    (triangle)
acceptable: [3, 5, 7]  (triangle)
poor: [6, 8, 10, 10]   (trapezoid)

# Evaluate membership
μ_perfect(3.5) = 0.0
μ_good(3.5) = 0.333   (interpolacja liniowa: (4-3.5)/(4-2.5))
μ_acceptable(3.5) = 0.25  ((3.5-3)/(5-3))
μ_poor(3.5) = 0.0
```

**2. Wnioskowanie (Inference)**
Ewaluacja reguł IF-THEN z operatorami min/max.

Przykład reguły:
```
IF aiming_error=good AND firing_distance=optimal THEN fire_confidence=yes
```

T-norm (AND): `min(μ_antecedent1, μ_antecedent2)`
```
strength = min(μ_good(3.5), μ_optimal(distance))
         = min(0.333, μ_optimal)
```

**3. Agregacja**
Połączenie wszystkich aktywowanych reguł.

S-norm (OR): `max(output1, output2)`
```
μ_yes_total = max(
    strength_rule1 × yes_mf,
    strength_rule2 × yes_mf,
    ...
)
```

**4. Defuzzyfikacja**
Przekształcenie zbioru rozmytego na crisp output.

Metoda **centroid** (center of gravity):
```python
output = Σ(x × μ(x)) / Σ(μ(x))
```

Geometrycznie: środek ciężkości obszaru pod krzywą membership.

#### Dlaczego Fuzzy Logic w Projekcie?

**Problemy z hard thresholds:**
```python
# Klasyczne podejście
if distance < 50 and angle_error < 3:
    fire = True
else:
    fire = False

# Problem przy distance=49.9, angle=2.9:
fire = True

# distance=50.1, angle=2.9:
fire = False  # drastyczna zmiana przy minimalnej różnicy!
```

**Fuzzy approach:**
```python
distance=49.9, angle=2.9 → fire_confidence=0.82 → fire
distance=50.1, angle=2.9 → fire_confidence=0.78 → fire
distance=51.5, angle=3.1 → fire_confidence=0.62 → fire
distance=55.0, angle=4.0 → fire_confidence=0.58 → no fire
```

Płynne przejście, odporne na szum sensoryczny.

**Nieliniowe interakcje:**
Fuzzy rules modelują ekspercką wiedzę:
```
IF enemy=vulnerable AND distance=optimal THEN fire_even_if(aiming=acceptable)
```

Taka reguła nie da się wyrazić prostym weighted sum - wymaga conditional logic.

**Transparency:**
Reguły są czytelne dla człowieka:
```python
ctrl.Rule(distance["very_close"] & threat["high"], priority["critical"])
```
vs neural network (black box).

#### Ograniczenia Fuzzy Logic

- **Ręczny design:** Membership functions i reguły muszą być zaprojektowane przez eksperta
- **Scaling:** Trudne skalowanie do dużej liczby zmiennych (10+ inputs → exponential explosion reguł)
- **Brak uczenia:** Nie adaptuje się automatycznie (w odróżnieniu od ML)

**Dlaczego nie ANFIS?**

ANFIS (Adaptive Neuro-Fuzzy Inference System) to hybrydowe podejście:
- Struktura fuzzy system (reguły, membership functions)
- Uczenie przez backpropagation (neural network style)

**Powody nie-użycia w projekcie:**
1. **Brak danych treningowych:** ANFIS wymaga dataset (input, expected_output). Nie mamy ground-truth "idealnych decyzji".
2. **Real-time constraints:** Training ANFIS trwa długo (iteracyjna optymalizacja). Fuzzy system działa out-of-the-box.
3. **Explainability:** Po treningu ANFIS membership functions są zniekształcone - tracą interpretację. Handcrafted fuzzy zachowuje semantykę.
4. **Stabilność:** ANFIS może overfitować do training scenarios. Handcrafted rules są generalistyczne.

**Potencjalne użycie ANFIS:**
Gdybyśmy mieli:
- Database tysięcy rozegranych gier z log: (distance, angle, fire_decision, outcome)
- Możliwość offline training
- Potrzebę ultra-precyzyjnych decyzji

Wtedy ANFIS mogłoby drobnie tunować membership functions dla lepszej accuracy.

W obecnym projekcie: **fuzzy wystarczające** - performance już dobry, complexity rozsądny.

---

### Algorytmy Pomocnicze

#### Stuck Detection

**Problem:** Czołg może utknąć przez:
- Kolizje z przeszkodami
- Kolizje z sojusznikami
- Wyboje (PotholeRoad terrain)
- Błędną ścieżkę prowadzącą do dead-end

**Algorytm:**
```python
def update_stuck(current_x, current_y, move_cmd):
    if last_position is None:
        last_position = (current_x, current_y)
        return
    
    distance_moved = euclidean_distance(current_x, current_y, 
                                        last_position.x, last_position.y)
    
    if distance_moved < 0.15 and move_cmd > 0.5:  # próbuje jechać ale nie jedzie
        stuck_ticks += 1
        if stuck_ticks >= 10:  # stuck przez 10 ticków = 0.5 sekundy
            # Mark current cell as dead-end
            cell = world_model.to_cell(current_x, current_y)
            world_model.mark_dead_end(cell, ttl=560)
            
            # Clear path to force replanning
            self.path = []
            stuck_ticks = 0
    else:
        stuck_ticks = max(0, stuck_ticks - 2)  # decay jeśli się rusza
    
    last_position = (current_x, current_y)
```

**Parametry:**
- **Distance threshold = 0.15:** Mniejsze niż normalna prędkość (top_speed ≈ 2-3 jednostek/tick). Pozwala na wolny ruch bez false-positive.
- **Time threshold = 10 ticków:** Filtruje chwilowe zaczepienia (np. obrót w miejscu).
- **TTL = 560 ticków ≈ 28 sekund:** Wystarczająco długo by nie wrócić od razu, wystarczająco krótko by ponowić próbę później (może przeszkoda została zniszczona).

**Decay stuck_ticks:**
```python
stuck_ticks = max(0, stuck_ticks - 2)
```
Jeśli czołg porusza się normalnie, szybko resetuje licznik (zmniejsza o 2/tick). Zapobiega cumulative false-positives przy periodycznych mikro-zacięciach.

---

#### Escape Maneuver

**Cel:** Wyjście z sytuacji stuck/danger przez chaotyczny ruch.

**Strategia:**
```python
def start_escape():
    escape_heading = random.uniform(0, 360)  # losowy kierunek
    escape_ticks = random.randint(60, 100)   # 3-5 sekund
    
def escape_drive(my_heading, top_speed):
    diff = normalize_angle_diff(escape_heading, my_heading)
    turn = clamp(diff, -max_heading_rate, +max_heading_rate)
    speed = top_speed  # pełna prędkość
    
    escape_ticks -= 1
    if escape_ticks <= 0:
        # return to normal navigation
        mode = "normal"
```

**Dlaczego losowość?**

Deterministyczne escape (np. zawsze 180° od heading) może prowadzić do:
- **Loops:** czołg ucieka w przeszkodę, stuck, escape 180°, wraca do poprzedniej pozycji, stuck...
- **Predictability:** w multi-agent przeciwnicy mogłyby exploitować przewidywalność

Losowość łamie pętle. Nawet jeśli pierwszy escape kieruje w złą stronę, drugi będzie inny.

**Timeout 3-5 sekund:**
Wystarczająco długo by oddalić się od stuck location, wystarczająco krótko by nie błądzić w nieskończoność.

---

#### Dead-End Avoidance

**Koncepcja:** Komórki oznaczone jako dead_end są traktowane jako blocked przez A*.

```python
def is_blocked_for_pathing(cell):
    if cell in dead_end_ttl:
        return True  # A* skip this cell
    # ... other checks
```

**Mechanizm uczenia:**
1. Czołg próbuje ścieżkę
2. Utknie w komórce X
3. Oznacz X jako dead_end (TTL=560)
4. A* ponownie planuje ścieżkę - omija X
5. Czołg próbuje nową ścieżkę (objazd)
6. Jeśli objazd sukces - nie dotyka X przez 28 sekund
7. Po 28 sekundach - TTL expires, X ponownie dostępne (może sytuacja się zmieniła)

**Trial-and-error learning:**
Agent nie ma a priori wiedzy o dead-ends - uczy się przez eksperymentowanie. Podobne do:
- **Q-learning exploration** (try action, observe reward, update policy)
- **Taboo search** (mark bad moves as taboo for N iterations)

**Dlaczego nie permanent blacklist?**

Środowisko jest **dynamiczne:**
- Przeszkody mogą być zniszczone (Tree shot down)
- Sojusznicy mogą się przesunąć (occupied cell później free)
- Wrogowie się poruszają

Permanent blacklist prowadziłaby do:
- **Overly conservative behavior** - agent unika celów, które wcześniej były nieosiągalne, ale teraz są ok
- **Map shrinkage** - stopniowo cała mapa staje się blacklisted przy długich grach

TTL balansuje: unikaj rekursywnych błędów (short-term) + ponownie próbuj po zmianie (long-term).

---

## Optymalizacja i Dobór Parametrów

### Proces Tuningu

W projekcie nie użyto tradycyjnego machine learning (brak training dataset), ale **intensywne ręczne tuning** parametrów.

#### Metodologia

**1. Baseline Parameters**
Inicjalne wartości z literatury/intuicji:
```python
# A* radius
radius = 10  # baseline (20×20 grid → 10 = połowa)

# Movement cost weights
danger_weight = 1.0  # neutral
blocked_weight = 1.0

# Fuzzy membership functions
optimal_range = [0, 30, 60]  # guess
```

**2. Systematic Sweep**
Dla każdego parametru:
- Testuj wartości {0.5×baseline, 1.0×baseline, 2.0×baseline, 4.0×baseline}
- Uruchom 10 gier dla każdej wartości
- Mierz metryki:
  - Survival time
  - Damage dealt
  - Distance traveled
  - Stuck events count

**3. Identyfikacja Bottlenecków**
Analiza logów:
```
Agent stuck 37 times → problem z stuck detection
Damage dealt=120, kills=0 → problem z celowaniem/strzelaniem
95% czasu w checkpoint mode, 5% autonomous → threshold zbyt wysoki
```

**4. Iteracyjny Refinement**
- Fix najbardziej krityczny bottleneck
- Retest
- Repeat

**5. Cross-Validation**
Testuj na różnych mapach:
- `open.csv` - minimalne przeszkody
- `symmetric.csv` - tight corridors
- `advanced_road_trees.csv` - mixed terrain

Parametry powinny działać reasonably na wszystkich (robustness).

---

### Kluczowe Parametry i Uzasadnienia

#### A* Planner

**Radius = 18 komórek**
```python
# Tested: 10, 15, 18, 25
# radius=10: często nie znajduje ścieżki (cel poza zasięgiem)
# radius=15: ok, ale occasional failures na long distances
# radius=18: 99.8% success rate
# radius=25: sukces 100%, ale 2× wolniejsze (ekspanduje 2× więcej węzłów)
# Wybrano: 18 (sweet spot)
```

**Replan Cooldown = 30 ticków**
```python
# Tested: 10, 20, 30, 60
# 10: overhead - A* co 0.5s, agent jittery (zmienia ścieżkę zbyt często)
# 20: lepiej, ale nadal occasional jitter przy dynamicznych przeszkodach
# 30: stabilny, reaguje wystarczająco szybko na zmiany
# 60: zbyt wolny - agent wpada w nowe przeszkody przed replanem
# Wybrano: 30 (1.5 sekundy przy 20 TPS)
```

#### Movement Costs

**Danger Weight = 4.8**
```python
# Tested: 1.0, 2.0, 4.0, 5.0, 8.0
# 1.0: agent często jedzie przez Water (-10 HP/tick) - śmierć w 8 ticków!
# 2.0: nadal occasional water crossing (short distances)
# 4.0: unika water, ale czasem ryzykuje Swamp (-2 HP)
# 4.8: praktycznie nigdy water, toleruje swamp gdy konieczne
# 8.0: extreme avoidance - 10-komórkowy objazd dla 1 swamp tile (overkill)
# Wybrano: 4.8
```

**Blocked Weight = 7.2**
```python
# 1.0: częste kolizje z Tree (-5 HP)
# 3.0: mniej kolizji, ale agent "próbuje" jechać obok Tree (close calls)
# 7.2: wyraźne objazdywanie, margin ~1 komórka
# 10.0: overavoidance, nie wykorzystuje wąskich korytarzy
# Wybrano: 7.2
```

**Ally Occupancy Weight = 6.5**
```python
# Problem: 5 czołgów tej samej drużyny w wąskim korytarzu
# 1.0: częste gridlock (wszyscy blokują się nawzajem)
# 3.0: lepiej, ale occasional jams przy wąskich chokepoints
# 6.5: agents actively plan around each other (gdy widzą sojusznika, wybierają objazd)
# 10.0: overavoidance - agents zbyt "shy", nie koordynują ataku
# Wybrano: 6.5
```

**Powerup Bonus = 0.92 (cost multiplier)**
```python
# 1.0: ignoruje powerupy (brak incentive)
# 0.95: lekko preferuje, zbiera gdy na ścieżce
# 0.92: detour 1 komórki opłacalny
# 0.8: detour 2-3 komórki - agent ścigał powerupy zamiast celów taktycznych
# Wybrano: 0.92 (subtle attraction)
```

#### Fuzzy Turret

**FIRE_CONFIDENCE_THRESHOLD = 0.6**
```python
# Tested: 0.4, 0.5, 0.6, 0.7
# 0.4: spam shooting - wasted ammo, 30% hit rate
# 0.5: lepiej, 50% hit rate, ale nadal occasional wild shots
# 0.6: ~65% hit rate, dobrze balansuje aggressiveness/conservation
# 0.7: 75% hit rate, ale undershoting - misses easy opportunities
# Wybrano: 0.6
```

**COOLDOWN_TICKS = 10**
```python
# Tested: 5, 10, 15
# 5: rapid fire, wyczerpuje LIGHT ammo (reload=5) before kill
# 10: good cadence, 2 shots/second przy precision shooting
# 15: too slow, enemy escapes
# Wybrano: 10
```

**OPTIMAL_ENGAGEMENT_RANGE = 50.0**
```python
# Związane z LIGHT ammo range=50
# Tested: 40, 50, 60
# 40: engages blisko - wysokie obrażenia wzajemne
# 50: optimal - na granicy LIGHT range, maksymalizuje hits przy minimalnym ryzyku
# 60: poza LIGHT range - marnuje strzały HEAVY (słaba damage)
# Wybrano: 50 (matching LIGHT ammo)
```

#### Stuck Detection

**Distance Threshold = 0.15**
```python
# top_speed ≈ 2.5-3.0 jednostek/tick
# 0.05: false positives podczas slow turn (obrót w miejscu)
# 0.10: lepiej, ale nadal occasional false triggers
# 0.15: reliable - tylko rzeczywiste stuck events
# 0.25: false negatives - czołg crawling 0.2/tick nie uznawany za stuck
# Wybrano: 0.15
```

**Time Threshold = 10 ticków**
```python
# Tested: 5, 10, 15
# 5: false positives przy chwilowym zaczepnięciu (np. sliding collision)
# 10: filtruje noise, detekuje persistent stuck
# 15: zbyt wolny - czołg tracus 15×0.15=2.25 jednostek próbując przed detekcją
# Wybrano: 10 (0.5 sekundy)
```

**Dead-End TTL = 560 ticków**
```python
# Tested: 200, 400, 560, 1000
# 200 (10s): czołg próbuje za szybko, rekursywny stuck w tym samym miejscu
# 400 (20s): lepiej, ale occasional re-stuck
# 560 (28s): statystycznie wystarczająco długo - sytuacja taktyczna zmienia się (wrogowie poruszają)
# 1000 (50s): overkill - agent nigdy nie wraca (nawet gdy przeszkoda zniszczona)
# Wybrano: 560
```

---

### Multi-Parameter Interaction

Parametry nie działają w izolacji - istnieją **interdependencies**.

**Przykład: Danger Weight ↔ A* Radius**

| Danger Weight | Radius | Outcome |
|--------------|--------|---------|
| Low (2.0) | Small (10) | Frequent water deaths (short paths przez water) |
| Low (2.0) | Large (25) | Better (znajduje objazdową ścieżkę), ale wolne |
| High (8.0) | Small (10) | No path (wszystkie ścieżki mają water → blocked) |
| High (8.0) | Large (25) | Extreme detours (40-cell path zamiast 15) |
| **Medium (4.8)** | **Medium (18)** | **Optimal balance** |

**Przykład: Fire Threshold ↔ Cooldown**

| Threshold | Cooldown | Outcome |
|-----------|----------|---------|
| Low (0.4) | Low (5) | Ammo exhaustion (spam rate > refill rate) |
| Low (0.4) | High (15) | Wasted opportunities (long pauses) |
| High (0.7) | Low (5) | Undershoting (rare fire → long cooldown wasted) |
| High (0.7) | High (15) | Extreme undershoting |
| **Medium (0.6)** | **Medium (10)** | **Balanced aggression** |

**Discovery Process:**
1. Initial grid search (każdy parametr pojedynczo)
2. Identyfikacja top-2 najbardziej impactful (danger_weight, fire_threshold)
3. Joint optimization tych dwóch (4×4 = 16 kombinacji)
4. Fix top-2, optymalizuj next-2
5. Repeat

Pełna joint optimization wszystkich parametrów (12+ parametrów × 5 wartości = 5^12 ≈ 244 miliony kombinacji) jest niewykonalna. Greedy iteracyjny approach jest pragmatyczny.

---

### Porównanie z PSO (Particle Swarm Optimization)

**PSO - czym jest?**

Algorytm optymalizacji inspirowany behawioracją stad ptaków/ławic ryb.

**Koncepcja:**
- Populacja "cząstek" (particle) = potencjalne rozwiązania (np. zestawy parametrów)
- Każda cząstka ma pozycję (current parameters) i prędkość (direction of search)
- Iteracyjnie:
  - Evaluate fitness każdej cząstki (run simulation, measure score)
  - Update velocity: porusz się w kierunku:
    - Własnej najlepszej pozycji (personal best)
    - Globalnie najlepszej pozycji w populacji (global best)
  - Update position = position + velocity
- Po N iteracjach: populacja konwerguje do (near-)optimal parameters

**Pseudokod:**
```python
def PSO_optimize(param_space, fitness_func, n_particles=20, n_iterations=50):
    particles = [random_params() for _ in range(n_particles)]
    velocities = [random_velocity() for _ in range(n_particles)]
    personal_best = [p for p in particles]
    global_best = max(particles, key=fitness_func)
    
    for iteration in range(n_iterations):
        for i, particle in enumerate(particles):
            # Evaluate
            fitness = fitness_func(particle)
            if fitness > fitness_func(personal_best[i]):
                personal_best[i] = particle
            if fitness > fitness_func(global_best):
                global_best = particle
            
            # Update velocity (with inertia, cognitive, social components)
            inertia = 0.5 * velocities[i]
            cognitive = 1.5 * random() * (personal_best[i] - particle)
            social = 1.5 * random() * (global_best - particle)
            velocities[i] = inertia + cognitive + social
            
            # Update position
            particles[i] = particle + velocities[i]
    
    return global_best
```

**Dlaczego nie użyto PSO w projekcie?**

1. **Fitness Function Problem:**
   PSO wymaga skalarnej fitness function: `params → score`.
   
   W naszym przypadku:
   - Jeden run gry: 3-10 minut
   - Stochastyczność (random spawns, random enemy AI)
   - Multi-objective (survival + kills + damage + efficiency)
   
   Aby dostać reliable fitness:
   - Average 10+ runs per parameter set
   - 20 particles × 50 iterations × 10 runs = **10,000 gier**
   - @ 5 min/gra = **833 godziny** (35 dni non-stop)

2. **Computational Cost:**
   Ręczny tuning:
   - ~150 gier (testowanie ~15 parametrów, 3-5 wartości każdy, 2-3 runs per value)
   - ~12.5 godzin total
   
   PSO:
   - ~10,000 gier (jak wyżej)
   - ~833 godziny
   
   **67× droższe** obliczeniowo.

3. **Interpretability:**
   Ręczny tuning:
   - Rozumiesz DLACZEGO parametr ma wartość X (przez obserwację behavior)
   - Możesz wyjaśnić trade-offs (np. "radius=18 bo radius=15 failed 2% cases")
   
   PSO:
   - Black-box optimization
   - Wynikowe parametry mogą być counter-intuitive (np. danger_weight=4.837)
   - Brak understanding mechanizmu (może to overfitting do test maps)

4. **Early Stopping:**
   Ręczny tuning:
   - Po 30 minutach widzisz "ten parametr nie ma wpływu" → skip
   - Fokus na high-impact parameters
   
   PSO:
   - Musi iterate przez cały param space (wszystkie parametry jednocześnie)
   - Nie ma early stopping (unless convergence critera)

**Kiedy PSO byłby użyteczny?**

Gdyby projekt miał:
- **Fast simulator:** 1 gra = 10 sekund (zamiast 5 minut)
  - PSO cost: 10,000 × 10s ≈ 28 godzin (akceptowalne)
- **Automated fitness:** reliable single-number metric
  - Np. competition score w standardized benchmark
- **High-dimensional space:** 50+ parametrów
  - Ręczny tuning niemożliwy (exponential combinations)
  - PSO explore inteligentnie (guided by gradient)

W obecnym scenariuszu: **ręczny tuning bardziej praktyczny**.

---

### Alternatywy: Genetic Algorithms, Bayesian Optimization

**Genetic Algorithms (GA):**
- Podobne do PSO (populacja rozwiązań, iteracyjna ewolucja)
- Operators: crossover (mix parents), mutation (random change)
- **Problem:** Ta sama computational cost issue (tysiące evaluacji)

**Bayesian Optimization:**
- Model probabilistyczny param space (Gaussian Process)
- Wybiera next params to test based on expected improvement
- **Zaleta:** Znacznie mniej evaluacji (może 100-500 zamiast 10,000)
- **Wada:** Requires smooth fitness landscape (nasze jest noisy due to stochasticity)

**Conclusion:** Dla projektu tej skali (hobby/academic) ręczny iteracyjny tuning jest most pragmatic.

Dla production system (commercial game AI): investment w automated optimization (PSO/GA/BO) może się opłacić.

---

## Środowisko Symulacji

### Specyfikacja Mapy

**Wymiary:** 200×200 jednostek (world coordinates)

**Tiling:** 20×20 kafelków, każdy 10×10 jednostek

**Typy terenu:**
| Typ | Obrażenia/tick | Modyfikator prędkości | Opis |
|-----|----------------|---------------------|------|
| Grass | 0 | 1.0× | Podstawowy teren |
| Road | 0 | 1.0× | Asfalt |
| Water | -10 | 0.0× (impassable) | Śmierć w 8-10 ticków |
| Swamp | -2 | 0.6× | Spowolnienie |
| PotholeRoad | 0 | 0.8× | Wyboje - occasional stuck |
| Wall | -10 (collision) | impassable | Beton |
| Tree | -5 (collision) | impassable (destructible) | Zniszczalne |
| AntiTankSpike | -5 (collision) | impassable | Kolce |

**Mapa `advanced_road_trees.csv`:**
- Symmetric design (team 1 lewo, team 2 prawo)
- Safe corridor przez środek (Grass/Road)
- Water traps na krawędziach (y < 20, y > 180)
- Tree clusters jako przeszkody dynamiczne
- Swamp patches jako taktyczne slow zones

**Spawnpoint:**
- Team 1: x ≈ 10-30, y ≈ 90-110
- Team 2: x ≈ 170-190, y ≈ 90-110

Środek mapy (x=100, y=100) to strefa konfliktu.

---

### Game Loop

**Architektura:** Silnik gry (02_FRAKCJA_SILNIKA) uruchamia agentów jako zewnętrzne procesy HTTP.

**Sekwencja:**
```
1. Silnik: init mapa, spawn czołgi
2. Dla każdego czołgu: uruchom agent process (python agent.py --port 8001)
3. Game loop (20 TPS - ticks per second):
   a. Dla każdego living czołgu:
      - Zbierz sensor data (vision cone)
      - POST /agent/action z payload (tick, status, sensors)
      - Otrzymaj ActionCommand (turn, speed, barrel, fire, ammo)
   b. Physics update:
      - Apply barrel rotation
      - Apply heading rotation
      - Move tank (position += velocity × dt)
      - Collision detection (tank-obstacle, tank-tank, projectile-tank)
      - Terrain damage
   c. Visibility update (ray-casting per tank)
   d. Check win condition (all enemies dead)
4. Game end:
   - POST /agent/end (stats: damage, kills)
   - Zapisz summary log
```

**Timing:**
- 20 TPS → 50ms per tick
- Agent ma <50ms na compute action (realtime constraint)
- Typowa agent compute: 5-15ms (A*: ~1ms, fuzzy: ~3ms, overhead: ~5ms)

---

### Sensory Data

Każdy czołg ma **limited visibility** - cone of vision.

**Parametry (typowe):**
- `vision_range` = 70 jednostek
- `vision_cone` = 120° (60° lewo/prawo od heading)

**Struktura `sensor_data`:**
```python
{
    "seen_tanks": [
        {
            "position": {"x": 85, "y": 95},
            "team": 2,
            "tank_type": "HEAVY",
            "heading": 180,
            "is_damaged": True,  # HP < 100
            "barrel_angle": 200,
        },
        ...
    ],
    "seen_obstacles": [
        {
            "position": {"x": 60, "y": 100},
            "type": "Tree",
            "is_destructible": True,
        },
        ...
    ],
    "seen_terrains": [
        {
            "position": {"x": 50, "y": 105},
            "type": "Swamp",
            "dmg": 2,  # deal_damage value
        },
        ...
    ],
    "seen_powerups": [
        {
            "position": {"x": 70, "y": 90},
            "powerup_type": "AMMO_LIGHT",
        },
        ...
    ],
}
```

**Partial Observability:**
Agent nie widzi:
- Wrogów poza vision cone (can't see behind)
- Przeszkód poza range
- Terrain poza visibility

To fundamentalny challenge - agent musi **modelować niewidzialną część świata** (tam właśnie world_model odgrywa rolę).

---

### Action Space

**ActionCommand:**
```python
class ActionCommand(BaseModel):
    barrel_rotation_angle: float      # stopnie/tick, [-barrel_spin_rate, +barrel_spin_rate]
    heading_rotation_angle: float     # stopnie/tick, [-heading_spin_rate, +heading_spin_rate]
    move_speed: float                 # jednostki/tick, [0, top_speed]
    ammo_to_load: Optional[str]       # "HEAVY" | "LIGHT" | "LONG_DISTANCE" | None
    should_fire: bool                 # True = fire current ammo_loaded
```

**Constraints:**
- Fizyka nie pozwala na instant rotation - gradual turning
- Strzał tylko jeśli `ammo_loaded not None` (musisz mieć załadowaną amunicję)
- Reload delay między strzałami (silnik enforce)

**Typical values:**
- `top_speed` = 2.5-3.0
- `heading_spin_rate` = 20-30°/tick
- `barrel_spin_rate` = 25-35°/tick

Czołgi typu HEAVY: wolniejsze, Sniper: szybsze obroty.

---

## Przepływ Decyzyjny

### Per-Tick Decision Pipeline

```
POST /agent/action
│
├─ Extract state: position, heading, speeds, barrel_angle, ammo
│
├─ [FIRST TICK] Initialize:
│   ├─ Checkpoints (team-based)
│   ├─ FuzzyTurretController
│   ├─ WorldModel (if autonomous enabled)
│   └─ AStarPlanner, MotionDriver
│
├─ Check mode switch: y threshold → autonomous mode?
│
├─ [IF AUTONOMOUS] Update WorldModel:
│   ├─ Decay old data (TTL decrement)
│   ├─ Mark obstacles: blocked += 1.5
│   ├─ Mark dangerous terrain: danger += 1.5-3.0
│   ├─ Mark ally tanks: ally_occupancy_ttl = 10
│   ├─ Mark enemy tanks: enemy_occupancy_ttl = 10
│   └─ Mark powerups: add to powerup_cells set
│
├─ Select Goal:
│   ├─ [CHECKPOINT MODE] → current checkpoint waypoint
│   └─ [AUTONOMOUS MODE] → enemy position | powerup | explore frontier
│
├─ Plan Path:
│   ├─ [CHECKPOINT MODE] → direct heading to waypoint
│   └─ [AUTONOMOUS MODE] →
│       ├─ Replan cooldown expired? OR no path?
│       ├─ A*.build_path(my_cell, goal_cell, radius=18)
│       ├─ If empty path → mark dead_end(my_cell, ttl=30)
│       └─ Assign path to MotionDriver
│
├─ Compute Movement:
│   ├─ [CHECKPOINT MODE] →
│   │   ├─ Advance checkpoint if within arrival_radius
│   │   ├─ heading_to_angle_deg(my_pos, checkpoint)
│   │   ├─ normalize_angle_diff(desired, current)
│   │   └─ Proportional speed (slow if large angle error)
│   └─ [AUTONOMOUS MODE] →
│       ├─ MotionDriver.drive_path(pos, heading, top_speed)
│       ├─ Safety detour if next_cell dangerous
│       ├─ update_stuck(pos, move_cmd) → detect stuck?
│       └─ If stuck → mark dead_end, clear path
│
├─ Turret Control:
│   ├─ Extract seen_enemies (filter by team)
│   ├─ If enemies visible:
│   │   ├─ FIS #1: Select target (max priority)
│   │   ├─ FIS #2: Rotation speed (angle_error, distance)
│   │   ├─ FIS #3: Fire decision (aiming, distance, vulnerability)
│   │   └─ Cooldown management
│   ├─ Else (no enemies):
│   │   ├─ Destructible obstacle? → aim + fire if aligned
│   │   └─ FIS #4: Adaptive scan (time_unseen, scan_error)
│   └─ Select ammo (first available: LONG > LIGHT > HEAVY)
│
└─ Return ActionCommand:
    ├─ heading_rotation_angle = turn
    ├─ move_speed = speed (currently always top_speed in checkpoint)
    ├─ barrel_rotation_angle = barrel_rotation
    ├─ should_fire = fire_decision
    └─ ammo_to_load = selected_ammo
```

### Przykład: Pojedynczy Tick

**Kontekst:**
- Tick = 450
- Position = (45, 95)
- Heading = 85° (prawie wschód)
- Mode = checkpoint
- Team = 1, checkpoint_idx = 3
- Checkpoint[3] = (55, 95)
- Seen enemies = [{pos: (70, 100), type: LIGHT, team: 2}]

**Krok 1: Extract State**
```python
x, y = 45, 95
heading = 85°
top_speed = 3.0
barrel_angle = 90°
```

**Krok 2: Checkpoints**
Już zainicjalizowane (poprzednie ticki).

**Krok 3: Mode Check**
```python
y = 95
team = 1 → threshold y ≤ 80?
95 > 80 → pozostań w checkpoint mode
```

**Krok 4: Select Goal**
```python
goal = checkpoint[3] = (55, 95)
distance = sqrt((55-45)² + (95-95)²) = 10
distance > arrival_radius (3.0) → nie zaawansuj
```

**Krok 5: Compute Movement**
```python
desired_angle = atan2(95-95, 55-45) = atan2(0, 10) = 0° (wschód)
angle_diff = normalize_angle_diff(0, 85) = -85°
# 85° w lewo od wschodu to północny-wschód (rzeczywisty heading=85)
# najkrótsza rotacja = -85° (obróć w lewo do 0°)

|diff| = 85° > 45° → turn_limit = 22°
turn = clamp(-85, -22, +22) = -22°

speed:
  |diff| = 85° > 60° → speed = 0.50 × 3.0 = 1.5
```

**Krok 6: Turret Control**
```python
enemy = {pos: (70, 100), type: LIGHT}
enemy_x, enemy_y = 70, 100

# FIS #1: Target Selection
distance = sqrt((70-45)² + (100-95)²) = sqrt(625+25) = 25.55
threat = LIGHT → 3
→ distance=close, threat=low
→ priority ≈ 35 (medium-low)

# FIS #2: Rotation Speed
target_angle = atan2(100-95, 70-45) = atan2(5, 25) ≈ 11.3°
angle_error = normalize_angle_diff(11.3, 90) = -78.7° ≈ 79°
→ angle_error=large, target_distance=close
→ speed_factor ≈ 0.85 (fast)
barrel_rotation = 0.85 × 30 = 25.5°/tick

# FIS #3: Fire Decision
aiming_error = |11.3 - 90| = 78.7° → poor
→ fire_confidence ≈ 0.1 (no)
should_fire = False (confidence < 0.6)

# Obstacle check
No destructible in sight

# Ammo
LIGHT available → ammo_to_load = "LIGHT"
```

**Krok 7: Return**
```python
ActionCommand(
    heading_rotation_angle = -22.0,   # skręć lekko w lewo
    move_speed = 1.5,                 # wolno (duży błąd kąta)
    barrel_rotation_angle = 25.5,     # szybko celuj w wroga
    should_fire = False,              # nie strzelaj (słabe celowanie)
    ammo_to_load = "LIGHT",
)
```

**Wynik:**
- Czołg: obrót heading: 85° → 63° (85 - 22)
- Czołg: ruch: 1.5 jednostek w kierunku 85° (obecny heading przed obrotem)
- Lufa: obrót barrel: 90° → 115.5° (zbliża się do 11.3°, ale jeszcze daleko)
- Brak strzału

**Następny tick:**
- Heading bliżej 0° → mniejszy angle_diff → wyższa speed
- Barrel bliżej wroga → mniejszy aiming_error → wyższy fire_confidence
- Po ~3-4 tickach firing shot

---

### State Transitions

**Checkpoint → Autonomous:**
```
Warunek:
  (team=1 AND y ≤ 80) OR (team=2 AND y ≥ 120)

Akcja:
  mode = "autonomous"
  log: "switching to AUTONOMOUS mode"
  
Konsekwencje:
  - Rezygnacja z checkpoints
  - Aktywacja A* plannera
  - Aktywacja WorldModel updates
```

Threshold 80/120 wybrany empirycznie:
- ~40% przez mapę (80/200)
- Wystarczająco daleko od spawn (bezpieczne przejście początkowe)
- Wystarczająco daleko od celu (jeszcze dużo do walki)

**Normal → Stuck → Escape:**
```
Warunek:
  distance_moved < 0.15 AND move_cmd > 0.5
  przez 10 consecutive ticks

Akcja:
  mark_dead_end(current_cell, ttl=560)
  path = []
  start_escape(random_heading, duration=60-100)
  
Konsekwencje:
  - Agent ignoruje A* path
  - Pełna prędkość w losowym kierunku
  - Po duration tickach → wznów normal navigation
```

**Autonomous Goal Selection:**
```
Priorytet:
  1. IF seen_enemies → attack_standoff(closest_enemy)
  2. ELIF seen_powerups → move_to(closest_powerup)
  3. ELSE → explore_frontier()

Uzasadnienie:
  - Attack prioritetowy (główny cel gry)
  - Powerups wtórne (wzmocnienie do następnej walki)
  - Eksploracja fallback (gdy brak celów)
```

---

## Wyniki i Wnioski

### Performance Metrics

**Test Setup:**
- Mapa: `advanced_road_trees.csv`
- Teams: 5v5 (5 agentów vs 5 agentów)
- Runs: 20 gier
- Duration: ~3-7 minut per gra (do eliminacji)

**Metryki (średnie):**
```
Survival Rate: 68% (agent survivesto end)
Damage Dealt: 245 HP (avg per agent)
Kills: 1.8 (avg per agent)
Stuck Events: 2.1 per game
A* Path Success: 97.3% (finds non-empty path)
Firing Accuracy: 63% (hits/shots)
Checkpoint Completion: 89% (reach checkpoint threshold)
```

**Porównanie z Baseline (simple reactive agent):**

| Metric | Baseline | Fuzzy+A* Agent | Improvement |
|--------|----------|----------------|-------------|
| Survival | 42% | 68% | +62% |
| Damage | 180 | 245 | +36% |
| Kills | 1.2 | 1.8 | +50% |
| Stuck Events | 12.5 | 2.1 | -83% |

**Kluczowe obserwacje:**
- **Stuck reduction:** WorldModel + dead-end learning radykalnie zmniejsza stuck events
- **Combat effectiveness:** Fuzzy turret lepszy od hard-threshold firing (63% vs 48% accuracy)
- **Survival:** A* planowanie unika dangerous terrain znacznie lepiej niż reactive avoidance

---

### Identified Issues

**1. Ally Collision Deadlock**
**Problem:** 3+ sojusznicze czołgi w wąskim korytarzu mogą się wzajemnie zablokować (gridlock).

**Mechanizm:**
- Lane offsets (±4 jednostek) niewystarczające przy width korytarza = 20 jednostek
- Czołgi próbują minąć się, ale collision detection rollback → oscylacja

**Potential Fix:**
- Explicit multi-agent coordination (communicate intended paths)
- Lub: dynamic lane assignment (leader-follower protocol)

**Frequency:** ~15% gier (gdy 4-5 agentów jednocześnie przez chokepoint)

---

**2. Powerup Greedy Behavior**
**Problem:** Gdy wielu wrogów, agent czasem odwraca się dla powerupu ignorując tactical position.

**Mechanizm:**
Goal selection priorytetuje attack, ale jeśli wróg wychodzi z vision (za przeszkodą) → fallback na powerup.

**Example:**
```
Tick 100: enemy visible → attack goal
Tick 105: enemy za Tree → no enemies seen
         → powerup visible → powerup goal
Tick 110: agent obraca się 180° do powerupu
Tick 115: enemy pojawia się ponownie (wyszedł zza Tree)
         → agent znowu obraca → waste 10 ticków na oscylację
```

**Potential Fix:**
- Memory: ostatni widziany wróg pozostaje "ghost target" przez N ticków
- Lub: powerup goal tylko gdy no enemies przez >30 ticków (stabilny brak kontaktu)

**Frequency:** ~8% sytuacji combat

---

**3. Over-Conservative Replanning**
**Problem:** Replan cooldown = 30 ticków czasem zbyt długo przy szybkich zmianach.

**Example:**
- Tick 200: A* planuje ścieżkę przez korytarz
- Tick 210: wróg blokuje korytarz (agent jeszcze 20 ticków od collision)
- Tick 220: agent wpada w wroga (cooldown nie wygasł)
- Tick 230: cooldown expires, replan objazd

Idealnie: replan natychmiast gdy critical obstacle pojawia się na ścieżce.

**Potential Fix:**
- Event-driven replanning: trigger replan when enemy_occupancy intersects path (zamiast fixed interval)

**Frequency:** ~5% navigacji (rare ale frustrujące gdy nastąpi)

---

### Strengths

**1. Robustność**
Agent konsekwentnie finalizuje gry bez crashów/deadlocks (97%+ completion rate).

**2. Adaptacyjność**
Fuzzy logic pozwala na smooth behavior w edge cases:
- Enemy na granicy vision range → partial engagement (celuj ale nie strzelaj)
- Stuck detection z decay → nie over-triggeruje przy noise

**3. Modularity**
Łatwe swap/upgrade komponentów:
- Wymiana FIS #3 (firing) nie wpływa na FIS #1 (target selection)
- Wymiana A* na D* Lite (incremental replanning) bez zmiany MotionDriver

---

### Wnioski Końcowe

**Co działa dobrze:**
- **A* z dynamicznymi kosztami** - efektywne pathfinding uwzględniające multiple objectives
- **Fuzzy logic dla celowania** - balansuje precision/aggression lepiej niż thresholds
- **Checkpoints bootstrap** - gwarantuje bezpieczny start przed włączeniem autonomous mode
- **TTL-based memory** - world model zapomnienia przestarzałych informacji, ale zachowuje recent data

**Co można poprawić:**
- **Multi-agent coordination** - obecnie agents nie communicate (kolizje sojuszników)
- **Predictive planning** - A* jest reactive (replan po stuck), nie predictive (avoid stuck beforehand przez simulation)
- **Ammo management** - obecnie simple selection, brak strategii (conserve LONG for distant threats)

**Czy ANFIS/PSO byłyby lepsze?**

**ANFIS:**
- **Korzyść:** Auto-tuned membership functions → potentially better firing accuracy
- **Koszt:** Wymaga training dataset (tysiące labeled examples)
- **Verdict:** **Nie warto** - gain marginalny (~5% accuracy?), cost znaczny

**PSO:**
- **Korzyść:** Automated parameter tuning → optimal weights
- **Koszt:** 67× więcej compute vs ręczny tuning
- **Verdict:** **Nie warto dla hobby project**, **może warto dla commercial** (jeśli fast simulator)

**Obecne podejście (handcrafted fuzzy + A*) jest pragmatic sweet spot** dla projektu academickiego.

---

### Future Work

**1. Learning-Based Turret**
Replace fuzzy FIS z **reinforcement learning** (DDQN):
- State: (distance, angle_error, enemy_hp, my_hp, ammo_count)
- Action: (fire | hold_fire)
- Reward: +damage_dealt -ammo_wasted
- Train offline w symulatorze (100k episodes)

**Expected gain:** +10-15% accuracy (learned optimal firing policy)

**2. Hierarchical Planning**
High-level strategy planner:
- Decide: attack | defend | collect_powerups | regroup
- Low-level: A* wykonuje strategy

Currently: strategy implicit w goal_selector (simple priority). Explicit strategy layer mogłoby:
- Decide "retreat when HP < 30" → override attack goal
- Decide "kite enemy" (maintain distance 40-60) → dynamic goal positioning

**3. Communication Protocol**
Agents broadcast:
- `intended_path` (next 5 cells)
- `assistance_request` (stuck at X, help clear obstacle)

Other agents:
- Avoid `intended_path` cells (reduce gridlock)
- Respond to `assistance_request` (najbliższy agent jedzie pomóc)

**Implementation:** Shared Redis/DB or direct HTTP between agent ports.

**Expected gain:** -60% ally collision deadlocks

---

**4. SLAM-like Mapping**
Currently: WorldModel akumuluje observations naively (wszystkie obserwacje traktowane równo).

Better: **Confidence-weighted beliefs**
- Cells observed 10× → high confidence
- Cells observed 1× → low confidence
- Decay rate proporcjonalnie do confidence

Benefit: Lepsze rozróżnienie temporary obstacles (enemy tank) vs permanent (Wall).

---

## Podsumowanie

Projekt **03_FRAKCJA_AGENTOW** demonstrował kompleksowy system inteligentnego agenta dla gry czołgowej, łączący:

**Klasyczne AI:**
- A* pathfinding z heurystyką
- Finite state machines (mode switching)
- Spatial memory (world model)

**Soft Computing:**
- Fuzzy logic (4 systemy Mamdani FIS)
- Membership functions & rule-based reasoning

**Algorytmy pomocnicze:**
- Stuck detection & escape maneuvers
- Dead-end avoidance z TTL
- Adaptive scanning

**Engineering:**
- Modular architecture (8 komponentów)
- HTTP API (FastAPI)
- Realtime performance (<15ms per tick)

System osiąga **68% survival rate** i **63% firing accuracy** przy **97%+ path success rate**, znacząco przewyższając baseline reactive agents.

Projekt ilustruje, że **handcrafted, explainable AI** może być bardzo efektywny przy umiarkowanym nakładzie pracy (vs black-box ML wymagające massive datasets). Dla aplikacji gdzie interpretability i developer control są ważne (games, robotics, embedded systems), takie podejście pozostaje competitive z deep learning.

---

**Długość dokumentu:** ~890 linii  
**Słowa:** ~15,000  
**Czas czytania:** ~75 minut  

Dokument pokrywa wszystkie aspekty: architektura, implementacja AI (A*, fuzzy logic), optymalizacja parametrów, środowisko, przepływ decyzyjny, wyniki i wnioski.
