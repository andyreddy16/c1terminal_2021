import gamelib
import random
from sys import maxsize
import json

"""
Most of the algo code you write will be in this file unless you create new
modules yourself. Start by modifying the 'on_turn' function.

Advanced strategy tips: 

  - You can analyze action frames by modifying on_action_frame function

  - The GameState.map object can be manually manipulated to create hypothetical 
  board states. Though, we recommended making a copy of the map to preserve 
  the actual current map state.
"""


class AlgoStrategy(gamelib.AlgoCore):
    def __init__(self):
        super().__init__()
        seed = random.randrange(maxsize)
        random.seed(seed)
        gamelib.debug_write('Random seed: {}'.format(seed))

    def on_game_start(self, config):
        """ 
        Read in config and perform any initial setup here 
        """
        gamelib.debug_write('Configuring your custom algo strategy...')
        self.config = config
        global WALL, SUPPORT, TURRET, SCOUT, DEMOLISHER, INTERCEPTOR, MP, SP
        WALL = config["unitInformation"][0]["shorthand"]
        SUPPORT = config["unitInformation"][1]["shorthand"]
        TURRET = config["unitInformation"][2]["shorthand"]
        SCOUT = config["unitInformation"][3]["shorthand"]
        DEMOLISHER = config["unitInformation"][4]["shorthand"]
        INTERCEPTOR = config["unitInformation"][5]["shorthand"]
        MP = 1
        SP = 0
        # This is a good place to do initial setup
        self.scored_on_locations = []
        self.turret_locations = []
        self.wall_locations = []
        self.support_locations = []
        self.add_supports = False

    def on_turn(self, turn_state):
        """
        This function is called every turn with the game state wrapper as
        an argument. The wrapper stores the state of the arena and has methods
        for querying its state, allocating your current resources as planned
        unit deployments, and transmitting your intended deployments to the
        game engine.
        """
        game_state = gamelib.GameState(self.config, turn_state)
        gamelib.debug_write('Performing turn {} of your custom algo strategy'.format(game_state.turn_number))
        game_state.suppress_warnings(True)  # Comment or remove this line to enable warnings.

        self.starter_strategy(game_state)

        game_state.submit_turn()

    """
    NOTE: All the methods after this point are part of the sample starter-algo
    strategy and can safely be replaced for your custom algo.
    """

    def starter_strategy(self, game_state):
        """
        For defense we will use a spread out layout and some interceptors early on.
        We will place turrets near locations the opponent managed to score on.
        For offense we will use long range demolishers if they place stationary units near the enemy's front.
        If there are no stationary units to attack in the front, we will send Scouts to try and score quickly.
        """

        # deploy basic v-shaped defense structure (if turn < 2 or health is low)
        if game_state.turn_number <= 2 or game_state.my_health < 10:
            gamelib.debug_write("Building basic defenses")
            self.build_v_defences(game_state)

            # if health is very low, upgrade turrets
            if game_state.my_health < 10:
                gamelib.debug_write("Upgrading turrets")
                self.update_locations(TURRET, game_state)
                game_state.attempt_upgrade(self.turret_locations)
                self.send_interceptors(2, game_state)

        # send interceptors (if MP health of enemy is greater > 4)
        if game_state.get_resource(MP, 1) > 7:
            gamelib.debug_write("Sending interceptors")
            self.update_locations(TURRET, game_state)
            self.add_walls_to_turrets(self.turret_locations, game_state)

        # replace hit locations with turrets
        self.build_reactive_defense(game_state)
        self.add_walls_to_turrets(self.turret_locations, game_state)

        # prepare to convert to channel of supports (if SP is high and predicted MP is high)
        self.update_locations(TURRET, game_state)
        support_cost = gamelib.GameUnit(SUPPORT, game_state.config).cost[SP]
        possible_sp = self.calculate_possible_SP(game_state)
        if possible_sp > support_cost * 6 and game_state.project_future_MP() > 6:
            gamelib.debug_write("Preparing offensive hit")
            self.prepare_offensive_hit(game_state)
        if self.add_supports:
            self.add_support_channel(game_state)
            if game_state.get_resource(MP, 0) > 6:
                game_state.attempt_spawn(SCOUT, [13, 0], 1000)
                # check if successful, if not, send demolisher

        if game_state.get_resource(SP, 0) > 4:
            wall_line = [[4, 9], [5, 8], [6, 7], [7, 6], [8, 5], [9, 4]]
            # game_state.attempt_spawn(SUPPORT, wall_line)
            self.add_walls_to_turrets(self.turret_locations, game_state)

    def calculate_possible_SP(self, game_state):
        self.update_locations(TURRET, game_state)
        sp = game_state.get_resource(SP, 0)
        for turret_loc in self.turret_locations:
            for unit in game_state.game_map[turret_loc[0], turret_loc[1]]:
                if unit.unit_type == TURRET and not unit.upgraded:
                    sp += unit.cost[0]
        return sp

    def prepare_offensive_hit(self, game_state):
        # remove non-upgraded turrets for offensive hit
        indices_to_remove = []
        for turret_loc in self.turret_locations:
            for unit in game_state.game_map[turret_loc[0], turret_loc[1]]:
                if unit.unit_type == TURRET and not unit.upgraded:
                    indices_to_remove.append(self.turret_locations.index(turret_loc))
                    removed = game_state.attempt_remove(turret_loc)
                    gamelib.debug_write("Removed: " + str(removed))

        for index in sorted(indices_to_remove, reverse=True):
            del self.turret_locations[index]
        self.add_supports = True
        self.add_support_channel(game_state)

    def add_support_channel(self, game_state):
        support_locations_right = [[23, 11], [22, 10], [21, 9], [20, 8], [19, 7], [18, 6], [17, 5], [16, 4], [15, 3],
                                   [14, 2], [13, 1]]
        support_locations_right.reverse()
        support_locations_left = [[4, 11], [5, 10], [6, 9], [7, 8], [8, 7], [9, 6], [10, 5], [11, 4], [12, 3], [13, 2],
                                  [14, 1]]
        support_locations_left.reverse()

        for loc in support_locations_left:
            spawned = game_state.attempt_spawn(SUPPORT, loc)
            if spawned == 1:
                self.support_locations.append(loc)

    def send_interceptors(self, num, game_state):
        left_pos = [[4, 9], [5, 8], [6, 7], [7, 6], [8, 5], [9, 4]]
        right_pos = [[23, 9], [22, 8], [21, 7], [20, 6], [19, 5], [18, 4]]

        for i in range(num):
            if i % 2 == 0:
                location = random.choice(left_pos)
            else:
                location = random.choice(right_pos)

            spawned = game_state.attempt_spawn(INTERCEPTOR, location)

            if spawned == 0:
                num += 1

    def build_v_defences(self, game_state):
        """
        Build basic defenses using hardcoded locations in v-shaped formation
        Remember to defend corners and avoid placing units in the front where enemy demolishers can attack them.
        """
        # Useful tool for setting up your base locations: https://www.kevinbai.design/terminal-map-maker
        # More community tools available at: https://terminal.c1games.com/rules#Download

        # Place turrets that attack enemy units
        turret_locations = [[0, 13], [27, 13], [4, 11], [23, 11], [7, 9], [20, 9], [9, 7], [18, 7], [13, 6], [14, 6]]
        # attempt_spawn will try to spawn units if we have resources, and will check if a blocking unit is already there
        game_state.attempt_spawn(TURRET, turret_locations)
        self.add_structure_units(turret_locations, game_state)

        self.update_locations(TURRET, game_state)
        self.add_walls_to_turrets(self.turret_locations, game_state)

    def add_walls_to_turrets(self, turret_locations, game_state):
        for loc in turret_locations:
            wall_loc = [[loc[0] - 1, loc[1] + 2], [loc[0], loc[1] + 2], [loc[0] + 1, loc[1] + 2]]
            gamelib.debug_write("Wall locations to add.")
            gamelib.debug_write(wall_loc)
            spawned = game_state.attempt_spawn(WALL, wall_loc)
            gamelib.debug_write(spawned)
            if spawned == len(wall_loc):
                self.wall_locations.extend(wall_loc)
            elif spawned > 0:
                self.add_structure_units(wall_loc, game_state)

    def add_structure_units(self, locations, game_state):
        """
        Updates list of structure unit positions. Will not remove any from list, even if not there anymore.
        """
        for location in locations:
            # does this update immediately, or based on previous round?
            unit_type = game_state.contains_stationary_unit(location)
            if unit_type == TURRET and location not in self.turret_locations:
                self.turret_locations.append(location)
            elif unit_type == WALL and location not in self.wall_locations:
                self.wall_locations.append(location)
            elif unit_type == SUPPORT and location not in self.support_locations:
                self.support_locations.append(location)

    def update_locations(self, unit_type, game_state):
        if unit_type == TURRET:
            self.turret_locations[:] = (loc for loc in self.turret_locations if
                                        game_state.contains_stationary_unit(loc) == TURRET)
        if unit_type == WALL:
            self.wall_locations[:] = (loc for loc in self.wall_locations if
                                      game_state.contains_stationary_unit(loc) == WALL)
        if unit_type == SUPPORT:
            self.support_locations[:] = (loc for loc in self.support_locations if
                                         game_state.contains_stationary_unit(loc) == SUPPORT)

    def build_reactive_defense(self, game_state):
        """
        This function builds reactive defenses based on where the enemy scored on us from.
        We can track where the opponent scored by looking at events in action frames 
        as shown in the on_action_frame function
        """
        for location in self.scored_on_locations:
            # Build turret one space above so that it doesn't block our own edge spawn locations
            build_location = [location[0], location[1] + 1]
            spawned = game_state.attempt_spawn(TURRET, build_location)
            if spawned == 1 and build_location not in self.turret_locations:
                self.turret_locations.append(location)

    def stall_with_interceptors(self, game_state):
        """
        Send out interceptors at random locations to defend our base from enemy moving units.
        """
        # We can spawn moving units on our edges so a list of all our edge locations
        friendly_edges = game_state.game_map.get_edge_locations(
            game_state.game_map.BOTTOM_LEFT) + game_state.game_map.get_edge_locations(game_state.game_map.BOTTOM_RIGHT)

        # Remove locations that are blocked by our own structures 
        # since we can't deploy units there.
        deploy_locations = self.filter_blocked_locations(friendly_edges, game_state)

        # While we have remaining MP to spend lets send out interceptors randomly.
        while game_state.get_resource(MP) >= game_state.type_cost(INTERCEPTOR)[MP] and len(deploy_locations) > 0:
            # Choose a random deploy location.
            deploy_index = random.randint(0, len(deploy_locations) - 1)
            deploy_location = deploy_locations[deploy_index]

            game_state.attempt_spawn(INTERCEPTOR, deploy_location)
            """
            We don't have to remove the location since multiple mobile 
            units can occupy the same space.
            """

    def demolisher_line_strategy(self, game_state):
        """
        Build a line of the cheapest stationary unit so our demolisher can attack from long range.
        """
        # First let's figure out the cheapest unit
        # We could just check the game rules, but this demonstrates how to use the GameUnit class
        stationary_units = [WALL, TURRET, SUPPORT]
        cheapest_unit = WALL
        for unit in stationary_units:
            unit_class = gamelib.GameUnit(unit, game_state.config)
            if unit_class.cost[game_state.MP] < gamelib.GameUnit(cheapest_unit, game_state.config).cost[game_state.MP]:
                cheapest_unit = unit

        # Now let's build out a line of stationary units. This will prevent our demolisher from running into the enemy base.
        # Instead they will stay at the perfect distance to attack the front two rows of the enemy base.
        for x in range(27, 5, -1):
            game_state.attempt_spawn(cheapest_unit, [x, 11])

        # Now spawn demolishers next to the line
        # By asking attempt_spawn to spawn 1000 units, it will essentially spawn as many as we have resources for
        game_state.attempt_spawn(DEMOLISHER, [24, 10], 1000)

    def least_damage_spawn_location(self, game_state, location_options):
        """
        This function will help us guess which location is the safest to spawn moving units from.
        It gets the path the unit will take then checks locations on that path to 
        estimate the path's damage risk.
        """
        damages = []
        # Get the damage estimate each path will take
        for location in location_options:
            path = game_state.find_path_to_edge(location)
            damage = 0
            for path_location in path:
                # Get number of enemy turrets that can attack each location and multiply by turret damage
                damage += len(game_state.get_attackers(path_location, 0)) * gamelib.GameUnit(TURRET,
                                                                                             game_state.config).damage_i
            damages.append(damage)

        # Now just return the location that takes the least damage
        return location_options[damages.index(min(damages))]

    def detect_enemy_unit(self, game_state, unit_type=None, valid_x=None, valid_y=None):
        total_units = 0
        for location in game_state.game_map:
            if game_state.contains_stationary_unit(location):
                for unit in game_state.game_map[location]:
                    if unit.player_index == 1 and (unit_type is None or unit.unit_type == unit_type) and (
                            valid_x is None or location[0] in valid_x) and (valid_y is None or location[1] in valid_y):
                        total_units += 1
        return total_units

    def filter_blocked_locations(self, locations, game_state):
        filtered = []
        for location in locations:
            if not game_state.contains_stationary_unit(location):
                filtered.append(location)
        return filtered

    def on_action_frame(self, turn_string):
        """
        This is the action frame of the game. This function could be called 
        hundreds of times per turn and could slow the algo down so avoid putting slow code here.
        Processing the action frames is complicated so we only suggest it if you have time and experience.
        Full doc on format of a game frame at in json-docs.html in the root of the Starterkit.
        """
        # Let's record at what position we get scored on
        state = json.loads(turn_string)
        events = state["events"]
        breaches = events["breach"]
        for breach in breaches:
            location = breach[0]
            unit_owner_self = True if breach[4] == 1 else False
            # When parsing the frame data directly, 
            # 1 is integer for yourself, 2 is opponent (StarterKit code uses 0, 1 as player_index instead)
            if not unit_owner_self:
                gamelib.debug_write("Got scored on at: {}".format(location))
                self.scored_on_locations.append(location)
                gamelib.debug_write("All locations: {}".format(self.scored_on_locations))


if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()
