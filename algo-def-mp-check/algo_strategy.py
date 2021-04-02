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
        global WALL, SUPPORT, TURRET, SCOUT, DEMOLISHER, INTERCEPTOR, MP, SP, WALL_LOCATIONS, SUPPORT_LOCATIONS, TURRET_LOCATIONS
        WALL = config["unitInformation"][0]["shorthand"]
        SUPPORT = config["unitInformation"][1]["shorthand"]
        TURRET = config["unitInformation"][2]["shorthand"]
        SCOUT = config["unitInformation"][3]["shorthand"]
        DEMOLISHER = config["unitInformation"][4]["shorthand"]
        INTERCEPTOR = config["unitInformation"][5]["shorthand"]
        MP = 1
        SP = 0
        WALL_LOCATIONS = []
        SUPPORT_LOCATIONS = []
        TURRET_LOCATIONS = []
        # This is a good place to do initial setup
        self.scored_on_locations = []

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
        # game_state.suppress_warnings(True)  # Comment or remove this line to enable warnings.

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
        # If health is very low (and enemy is high), build turrets
        if game_state.my_health < 12 and game_state.enemy_health > 15:
            gamelib.debug_write("Attempting defensive recovery.")
            self.immediate_defensive_recovery(game_state)

        # Place initial defensive structure in beginning
        if game_state.turn_number < 2:
            gamelib.debug_write("Setup initial defense")
            num_turrets = 10  # assume 1 wall cost for each turret (2 cost)
            gamelib.debug_write("Num turrets" + str(num_turrets))
            self.setup_initial_defense(num_turrets, game_state, False)

        if game_state.get_resource(MP, 1) < 4 or game_state.enemy_health < 15:
            self.offensive_supports(game_state.game_map.BOTTOM_LEFT, game_state)
            self.deploy_demolishers(game_state, game_state.game_map.BOTTOM_LEFT)
        else:
            # Move turrets to locations where enemy scored (check which places have no scores)
            gamelib.debug_write("Reconfigure turrets.")
            self.reconfigure_turrets(game_state)

        # If opponents has low MP, build more supports. Else, more turrets and walls.

        # If the turn is less than 5, stall with interceptors and wait to see enemy's base
        if game_state.turn_number < 5:
            self.stall_with_interceptors(game_state)
        else:
            # Now let's analyze the enemy base to see where their defenses are concentrated.
            # If they have many units in the front we can build a line for our demolishers to attack them at long range.
            if self.detect_enemy_unit(game_state, unit_type=None, valid_x=None, valid_y=[14, 15]) > 10:
                self.demolisher_line_strategy(game_state)
            else:
                # They don't have many units in the front so lets figure out their least defended area and send Scouts there.

                # Only spawn Scouts every other turn
                # Sending more at once is better since attacks can only hit a single scout at a time
                if game_state.turn_number % 2 == 1:
                    # To simplify we will just check sending them from back left and right
                    scout_spawn_location_options = [[13, 0], [14, 0]]
                    best_location = self.least_damage_spawn_location(game_state, scout_spawn_location_options)
                    game_state.attempt_spawn(SCOUT, best_location, 1000)

                # Lastly, if we have spare SP, let's build some Factories to generate more resources
                support_locations = [[13, 2], [14, 2], [13, 3], [14, 3]]
                game_state.attempt_spawn(SUPPORT, support_locations)

    def immediate_defensive_recovery(self, game_state):
            # deploy turrets at locations where hurt
            self.build_reactive_defense(game_state)

    def offensive_supports(self, side, game_state):
        support_locations_right = [[23, 11], [22, 10], [21, 9], [20, 8], [19, 7], [18, 6], [17, 5], [16, 4], [15, 3], [14, 2], [13, 1]]
        support_locations_right.reverse()
        support_locations_left = [[4, 11], [5, 10], [6, 9], [7, 8], [8, 7], [9, 6], [10, 5], [11, 4], [12, 3], [13, 2], [14, 1]]
        support_locations_left.reverse()

        if side == game_state.game_map.BOTTOM_LEFT:
            game_state.attempt_remove(support_locations_left)
        else:
            game_state.attemp_remove(support_locations_right)

        num_supports = game_state.number_affordable(SUPPORT)
        if num_supports < len(support_locations_right) - 2:
            sp_needed = (len(support_locations_right) - 2 - num_supports) * game_state.type_cost(SUPPORT)[0]
            num_turrets_remove = sp_needed / (game_state.type_cost(TURRET)[0]) * 0.9
            self.attempt_remove_num(num_turrets_remove, TURRET_LOCATIONS, game_state)

        if game_state.game_map.BOTTOM_LEFT == side:
            game_state.attempt_spawn(SUPPORT, support_locations_left)
        else:
            game_state.attempt_spawn(SUPPORT, support_locations_right)

    def deploy_demolishers(self, game_state, side):
        right_deploy_location = [13, 0]
        left_deploy_location = [14, 0]
        deploy_location = left_deploy_location
        if side == game_state.game_map.BOTTOM_RIGHT:
            deploy_location = right_deploy_location

        game_state.attempt_spawn(DEMOLISHER, deploy_location, 1000)

    def setup_initial_defense(self, num_turrets, game_state, upgrade=False):
        # add turrets in middle
        if num_turrets == 0:
            return
        # turret_middle_locations = [[8, 11], [19, 11], [13, 11], [14, 11]]
        turret_middle_locations = [[0, 13], [27, 13], [4, 11], [23, 11], [6, 9], [10, 9], [17, 9], [21, 9], [13, 6], [14, 6]]
        turrets_added = self.attempt_spawn_num(TURRET, num_turrets, turret_middle_locations, game_state)
        gamelib.debug_write("Turrets added " + str(turrets_added))
        num_turrets -= turrets_added

        gamelib.debug_write("Upgrade " + str(upgrade))
        if upgrade:
            upgraded = game_state.attempt_upgrade(turret_middle_locations)
            gamelib.debug_write("Number upgraded: " + str(upgraded))
        # add turrets at corners
        """
        right_empty = True
        left_empty = True
        turret_right_corner = [[27, 13], [26, 13], [25, 13]]
        turret_left_corner = [[0, 13], [1, 13], [2, 13]]
        for corner in turret_right_corner:
            if game_state.contains_stationary_unit(corner):
                right_empty = False
        for corner in turret_left_corner:
            if game_state.contains_stationary_unit(corner):
                left_empty = False

        if right_empty and num_turrets > 0:
            num_turrets -= self.attempt_spawn_num(TURRET, 1, turret_right_corner, game_state)
        if left_empty and num_turrets > 0:
            num_turrets -= self.attempt_spawn_num(TURRET, 1, turret_left_corner, game_state)
        """

        self.place_walls_front_of_turrets(turret_middle_locations, game_state)

    def place_walls_front_of_turrets(self, locations, game_state):
        wall_locations = []
        for location in locations:
            if TURRET == game_state.contains_stationary_unit(location):
                wall_location = [location[0], location[1] + 1]
                wall_locations.append(wall_location)
        game_state.attempt_spawn(WALL, wall_locations)
        for wall_location in wall_locations:
            if WALL == game_state.contains_stationary_unit(location):
                WALL_LOCATIONS.append(wall_location)

    def attempt_spawn_num(self, unit_type, num, locations, game_state):
        spawned = 0
        gamelib.debug_write("HERE." + str(num))
        gamelib.debug_write(locations)
        if len(locations) == 0:
            gamelib.debug_write("Zero locations!")
            return 0
        for location in locations:
            if spawned == num:
                break
            one_spawn = game_state.attempt_spawn(unit_type, location)
            if one_spawn > 0:
                gamelib.debug_write("Spawned: " + str(one_spawn))
                spawned += one_spawn
        return spawned

    def attempt_remove_num(self, num, locations, game_state):
        removed = 0
        gamelib.debug_write("Removing number of units: " + str(num))
        gamelib.debug_write(locations)
        if len(locations) == 0:
            gamelib.debug_write("Zero locations!")
            return 0
        for location in locations:
            if removed == num:
                break
            one_spawn = game_state.attempt_remove(location)
            if one_spawn > 0:
                gamelib.debug_write("Removed: " + str(one_spawn))
                removed += one_spawn
        return removed

    def reconfigure_turrets(self, game_state):
        turrets_to_remove = []
        # if len(self.scored_on_locations) * 2 > game_state.get_resource(SP, 0) * 0.6:
        for turret_location in TURRET_LOCATIONS:
            if TURRET == game_state.contains_stationary_unit(turret_location):
                if turret_location not in self.scored_on_locations:
                    can_remove = True
                    for scored_on in self.scored_on_locations:
                        if game_state.game_map.distance_between_locations(turret_location, scored_on) < 0:
                            can_remove = False
                            break
                    if can_remove:
                        turrets_to_remove.append(turret_location)
            # else:
                # TURRET_LOCATIONS.remove(turret_location)

        game_state.attempt_remove(turrets_to_remove)

        for location in self.scored_on_locations:
            game_state.attempt_spawn(TURRET, location)

    def build_defences(self, game_state):
        """
        Build basic defenses using hardcoded locations.
        Remember to defend corners and avoid placing units in the front where enemy demolishers can attack them.
        """
        # Useful tool for setting up your base locations: https://www.kevinbai.design/terminal-map-maker
        # More community tools available at: https://terminal.c1games.com/rules#Download

        # Place turrets that attack enemy units
        turret_locations = [[0, 13], [27, 13], [8, 11], [19, 11], [13, 11], [14, 11]]
        # attempt_spawn will try to spawn units if we have resources, and will check if a blocking unit is already there
        game_state.attempt_spawn(TURRET, turret_locations)

        # Place walls in front of turrets to soak up damage for them
        wall_locations = [[8, 12], [19, 12]]
        game_state.attempt_spawn(WALL, wall_locations)
        # upgrade walls so they soak more damage
        game_state.attempt_upgrade(wall_locations)

    def build_reactive_defense(self, game_state):
        """
        This function builds reactive defenses based on where the enemy scored on us from.
        We can track where the opponent scored by looking at events in action frames 
        as shown in the on_action_frame function
        """
        for location in self.scored_on_locations:
            # Build turret one space above so that it doesn't block our own edge spawn locations
            build_location = [location[0], location[1] + 1]
            game_state.attempt_spawn(TURRET, build_location)
            game_state.attempt_spawn(WALL, build_location)

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
