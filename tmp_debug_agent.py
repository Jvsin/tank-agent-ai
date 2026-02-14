from agent_core.agent import SmartAgent
from agent_core.goal_selector import Goal
from agent_core.geometry import euclidean_distance

agent = SmartAgent('Debug')
agent.current_goal = Goal((5,5),'explore',300.0)
agent.route_commit_until = 999999
agent.route_commit_mode = 'explore'
agent.driver.path = [(5,5)]

my_status = {"position": {"x":50.0, "y":50.0}, "heading":0.0, "hp":80.0, "_max_hp":100.0, "_team":1, "_top_speed":3.0, "_barrel_spin_rate":90.0, "_heading_spin_rate":70.0, "_vision_range":100.0}

sensor = {"seen_tanks":[{"id":"enemy_1","team":2,'tank_type':'LIGHT','position':{'x':60.0,'y':50.0}, 'is_damaged':False,'heading':180.0,'barrel_angle':0.0,'distance':10.0}], 'seen_obstacles':[], 'seen_terrains':[], 'seen_powerups':[] }

action = agent.get_action(current_tick=10, my_tank_status=my_status, sensor_data=sensor, enemies_remaining=1)
print('returned should_fire=', action.should_fire)
closest = None
for t in sensor['seen_tanks']:
    pos = t.get('position')
    d = euclidean_distance(my_status['position']['x'], my_status['position']['y'], pos['x'], pos['y'])
    closest = d if closest is None or d < closest else closest
print('closest_dist=', closest)
print('route_commit_mode=', agent.route_commit_mode)
print('current_goal=', agent.current_goal)
print('route_commit_until=', agent.route_commit_until)
print('driver.path=', agent.driver.path)
