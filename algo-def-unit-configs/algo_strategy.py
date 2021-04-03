import math

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
        self.ready_attack = False

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

        self.update_locations(TURRET, game_state)
        self.update_locations(WALL, game_state)
        self.update_locations(SUPPORT, game_state)
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
        if self.ready_attack:
            self.build_attack(game_state)
            # assume that refund happens after turn
            self.refund_structures(SUPPORT, game_state, False)
            self.refund_structures(WALL, game_state, False)
            self.refund_structures(TURRET, game_state, False)
            self.ready_attack = False
            return

        if self.is_ready_to_build_offensive(game_state):
            self.refund_structures(TURRET, game_state, False)
            self.ready_attack = True
            return

        self.block_middle_with_walls(3, 15, game_state)
        self.add_corner_turrets(True, game_state)
        self.add_v_turret_configuration(game_state)
        self.upgrade_top_turrets(4, game_state)

        if game_state.turn_number > 3 and game_state.get_resource(SP, 0) > 30:
            interceptors_loc = self.create_interceptor_shooter(8, True, True, game_state)

        self.build_reactive_defense(game_state)

    def build_attack(self, game_state):
        left_channel = [[5, 10], [6, 9], [7, 8], [8, 7], [9, 6], [10, 5], [11, 4], [12, 3], [13, 2], [13, 1]]
        left_channel.reverse()
        game_state.attempt_spawn(SUPPORT, left_channel)
        game_state.attempt_spawn(WALL, left_channel)  # in case not enough SP

        interceptor_loc = [6, 7]
        game_state.attempt_spawn(INTERCEPTOR, interceptor_loc)

        scout_loc = [12, 1]
        game_state.attempt_spawn(SCOUT, scout_loc, 1000)

    def refund_structures(self, unit_type, game_state, include_upgraded=False):
        remove_locs = []
        locations = []

        if unit_type == TURRET:
            locations = self.turret_locations
        elif unit_type == WALL:
            locations = self.wall_locations
        elif unit_type == SUPPORT:
            locations == self.support_locations
        else:
            return

        for loc in locations:
            for unit in game_state.game_map[loc[0], loc[1]]:
                if unit.unit_type == unit_type and unit.upgraded == include_upgraded:
                    remove_locs.append(loc)

        game_state.attempt_remove(remove_locs)

    def is_ready_to_build_offensive(self, game_state):
        """
        Checks if MP and SP are high enough.
        """
        mp = game_state.project_future_MP(1, 0)
        sp = self.calculate_possible_SP(game_state)

        return sp > 30 and mp > 7

    def add_corner_turrets(self, upgrade, game_state):
        """
        Add corner turrets, and upgrades if wanted.
        """
        left_corner = [[0, 13]]
        right_corner = [[27, 13]]
        turret_locations = left_corner + right_corner
        game_state.attempt_spawn(TURRET, turret_locations)
        if upgrade:
            game_state.attempt_upgrade(turret_locations)

    def add_v_turret_configuration(self, game_state):
        """
        Adds initial v_turret_config
        """
        left_turrets = [[5, 12], [6, 11], [8, 9], [10, 7]]
        right_turrets = [[22, 12], [21, 11], [19, 9], [17, 7]]
        middle_turrets = [[12, 9], [15, 9]]
        turret_locations = middle_turrets + left_turrets + right_turrets
        game_state.attempt_spawn(TURRET, turret_locations)

    def upgrade_top_turrets(self, num, game_state):
        self.update_locations(TURRET, game_state)

        # sort list by largest y value
        sorted_turrets = sorted(self.turret_locations, key=lambda x: x[1], reverse=True)

        upgraded = 0

        for loc in sorted_turrets:
            if upgraded == num:
                break
            upgraded += game_state.attempt_upgrade(loc)


    def block_middle_with_walls(self, depth, length, game_state):
        """
        Blocks the middle with a line of walls.
        :param depth: distance from center of game map.
        :param length: length of line of walls
        """
        if length == 0:
            return
        left_length = int(length / 2)
        right_length = length - left_length
        far_left_x = 13 - (left_length - 1)
        far_right_x = 14 + (right_length - 1)
        if length == 1:
            far_left_x = 13
            far_right_x = 13
        if length == 2:
            far_left_x = 13
            far_right_x = 14

        wall_locations = []

        gamelib.debug_write("Far left: " + str(far_left_x))
        gamelib.debug_write("Far right: " + str(far_right_x))

        for x in range(far_left_x, far_right_x + 1):
            wall_locations.append([x, 13 - depth])

        game_state.attempt_spawn(WALL, wall_locations)

    def create_interceptor_shooter(self, num_supports: int, left: bool, right: bool, game_state):
        """
        Middle channels should be empty or contain an interceptor only.
        Need at least ... SP and ... MP.
        num_supports must be less than 13 if only one side, and 26 for both sides.
        Create interceptor casing and add interceptor to explode for corners.
        Returns empty list if not possible, or list of locations interceptors were deployed if possible.
        """
        right_casing = [[24, 12], [23, 11], [22, 10], [21, 9], [20, 8], [21, 7]]
        right_casing.reverse()
        right_channel = [[25, 12], [24, 11], [25, 11], [23, 10], [24, 10], [22, 9], [23, 9], [21, 8], [22, 8]]
        right_interceptor = [[22, 8], [23, 9]]  # 2 possible positions, depends on speed needed

        left_casing = [[3, 12], [4, 11], [5, 10], [6, 9], [7, 8], [6, 7]]
        left_casing.reverse()
        left_channel = [[2, 12], [2, 11], [3, 11], [3, 10], [4, 10], [4, 9], [5, 9], [5, 8], [6, 8]]
        left_interceptor = [[4, 9], [5, 8]]  # 4 possible positions, depends on speed needed

        # check if channel is empty or only contains mobile units.

        # check if enough SP for supports. If not, replace with wall. If not enough for wall, only do one side.
        if left and right:
            num_walls = len(right_casing) * 2 - num_supports
            gamelib.debug_write("Num walls: " + str(num_walls))
            gamelib.debug_write("Num supports: " + str(num_supports))
            remove_supports = self.supports_to_replace_with_walls(num_walls, num_supports, game_state)
            gamelib.debug_write("Remove supports " + str(remove_supports))
            if remove_supports < num_supports:
                num_supports -= remove_supports
            else:
                # only one casing instead
                right = False
        if left != right:  # XOR
            num_walls = len(right_casing) - num_supports
            remove_supports = self.supports_to_replace_with_walls(num_walls, num_supports, game_state)
            if remove_supports >= 0:
                num_supports -= remove_supports
            else:
                return []

        # place num_supports divided equally between each wall
        for support in range(int(num_supports)):
            if left and right:  # divide evenly between two casings
                if support % 2 == 0 and left_casing:
                    self.attempt_support_spawn_last(left_casing, game_state)
                elif right_casing:
                    self.attempt_support_spawn_last(right_casing, game_state)
            elif left and left_casing:
                self.attempt_support_spawn_last(left_casing, game_state)
            elif right and right_casing:
                self.attempt_support_spawn_last(right_casing, game_state)

        # place walls
        if left and left_casing:
            game_state.attempt_spawn(WALL, left_casing)
        if right and right_casing:
            game_state.attempt_spawn(WALL, right_casing)

        interceptors = []

        # place interceptor
        if left:
            game_state.attempt_spawn(INTERCEPTOR, left_interceptor[0])
            interceptors.append(left_interceptor[0])
        if right:
            game_state.attempt_spawn(INTERCEPTOR, right_interceptor[0])
            interceptors.append(right_interceptor[0])

        gamelib.debug_write(interceptors)

        return interceptors

    def attempt_support_spawn_last(self, positions, game_state):
        """
        Spawns a support on last position of list.
        If successful, remove item from list.
        If unsuccessful, try to remove wall for next turn.
        """
        spawned_pos = []
        good = False

        for pos in positions:
            spawned = game_state.attempt_spawn(SUPPORT, pos)
            if spawned == 1:
                spawned_pos = pos
                break

        if good:
            positions.remove(spawned_pos)
            return

        for pos in positions:
            for unit in game_state.game_map[pos[0], pos[1]]:
                gamelib.debug_write(pos)
                if unit.unit_type == WALL:
                    removed = game_state.attempt_remove(pos)
                    if removed:
                        return

    def supports_to_replace_with_walls(self, num_walls: int, num_supports: int, game_state) -> int:
        """
        Get number of supports that need to be replaced by walls in interceptor shooter.
        """
        sp_needed = num_walls * game_state.type_cost(WALL)[SP] + num_supports * game_state.type_cost(SUPPORT)[SP]
        gamelib.debug_write("SP needed : " + str(sp_needed))
        current_sp = game_state.get_resource(SP, 0)
        gamelib.debug_write("SP current: " + str(current_sp))
        if current_sp < sp_needed:
            sp_diff = sp_needed - current_sp
            remove_supports = sp_diff / (game_state.type_cost(SUPPORT)[SP] - game_state.type_cost(WALL)[SP])
            remove_supports = math.ceil(remove_supports)
            gamelib.debug_write("Supports to remove: " + str(remove_supports))
            return remove_supports
        else:
            return 0

    def remove_turrets_for_sp(self, sp: int, game_state) -> bool:
        """
        Removes turrets to gain SP. If not enough, do nothing and return false.
        """
        # Check if there are enough non-upgraded turrets to remove
        sp_possible = self.calculate_possible_SP(game_state)
        if sp_possible < sp:
            return False
        for turret_loc in self.turret_locations:
            game_state.attempt_remove(turret_loc)

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