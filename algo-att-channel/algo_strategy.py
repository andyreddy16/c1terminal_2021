import math
import copy
import sklearn
from sklearn.naive_bayes import GaussianNB

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

        # Locations passed by reference to GameState. Should only be updated in GameState
        self.turret_locations = []
        self.wall_locations = []
        self.support_locations = []

        # Fake gamestate creation support
        self.remove_loc_check = []
        for j in range(13, -1, -1):
            for i in range(13-j, 15+j):
                self.remove_loc_check.append([i, j])

        self.enemy_attack_predictor = GaussianNB()

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
        self.score_locations = []
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
        game_state = gamelib.GameState(self.config, turn_state, self.turret_locations, self.wall_locations,
                                       self.support_locations)
        gamelib.debug_write('Performing turn {} of your custom algo strategy'.format(game_state.turn_number))
        game_state.suppress_warnings(True)  # Comment or remove this line to enable warnings.

        game_state.update_loc(TURRET)
        game_state.update_loc(WALL)
        game_state.update_loc(SUPPORT)

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
        attack_in_progress = False
        if self.ready_attack and game_state.get_resource(MP, 0) > 9:
            # left is in our view
            enemy_has_most_defense_on_left = self.get_side_enemy_defense(game_state)
            # want to build attack on same side as their defense since it will go opposite side
            self.build_attack(game_state, left=enemy_has_most_defense_on_left)
            attack_in_progress = True
            # remove offensive structure if not enough MP for next turn.
            # Do not remove if enemy health is lower than our MP units for next round.
            # Does MP update after putting scouts?
            new_mp = game_state.project_future_MP()
            if new_mp <= 9 and game_state.enemy_health > new_mp:
                self.refund_structures(SUPPORT, game_state, False)
                self.refund_structures(WALL, game_state, False)
                self.refund_structures(TURRET, game_state, False)
                self.ready_attack = False
        else:
            walls = 6
            supports = 10 - walls  # 10 represents number of support units needed to build attack

            if self.is_ready_to_build_offensive(supports, walls, game_state):
                self.refund_structures(TURRET, game_state, False)
                self.refund_structures(WALL, game_state, False)
                self.ready_attack = True
                return

        self.add_corner_turrets(True, game_state)
        gamelib.debug_write(attack_in_progress)
        if not attack_in_progress:
            self.add_v_turret_configuration(game_state)
        else:
            self.add_v_turret_configuration(game_state, 2)

        # only block if not attacking
        if not attack_in_progress:
            other_walls = [[1, 12], [2, 12], [3, 12], [4, 12], [23, 12], [24, 12], [25, 12], [26, 12]]
            game_state.attempt_spawn(WALL, other_walls)

        # always block middle
        self.block_middle_with_walls(3, 14, game_state)

        # self.upgrade_top_turrets(4, game_state)

        # if game_state.turn_number > 3 and game_state.get_resource(SP, 0) > 30:
        # interceptors_loc = self.create_interceptor_shooter(8, True, True, game_state)

        self.build_reactive_defense(game_state)

    def build_attack(self, game_state, left=True):
        left_channel = [[5, 10], [6, 9], [7, 8], [8, 7], [9, 6], [10, 5], [11, 4], [12, 3], [13, 2], [13, 1]]
        left_interceptor = [5, 8]
        left_scout = [12, 1]
        left_channel.reverse()  # reverse so supports start from bottom (might not need to reverse if not destroyed)
        right_channel = [[22, 10], [21, 9], [20, 8], [19, 7], [18, 6], [17, 5], [16, 4], [15, 3], [14, 2], [14, 1]]
        right_interceptor = [22, 8]
        right_scout = [15, 1]
        right_channel.reverse()

        if left:
            channel = left_channel
            interceptor = left_interceptor
            scout = left_scout
        else:
            channel = right_channel
            interceptor = right_interceptor
            scout = right_scout

        game_state.attempt_spawn(SUPPORT, channel)
        game_state.attempt_spawn(WALL, channel)  # in case not enough SP

        game_state.attempt_spawn(INTERCEPTOR, interceptor)  # not sure if needed all the time
        game_state.attempt_spawn(SCOUT, scout, 1000)

    def get_side_enemy_defense(self, game_state) -> bool:
        turret_locations = game_state.game_map.get_enemy_unit_locations(TURRET)
        wall_locations = game_state.game_map.get_enemy_unit_locations(WALL)
        support_locations = game_state.game_map.get_enemy_unit_locations(SUPPORT)
        all_locations = turret_locations + wall_locations + support_locations
        left_count = 0
        right_count = 0
        for location in all_locations:
            if location[0] <= 13:
                left_count += 1
            else:
                right_count += 1
        return left_count > right_count

    def refund_structures(self, unit_type, game_state, include_upgraded=False):
        remove_locs = []

        if unit_type == TURRET:
            locations = game_state.turret_locations
        elif unit_type == WALL:
            locations = game_state.wall_locations
        elif unit_type == SUPPORT:
            locations = game_state.support_locations
        else:
            return

        game_state.update_loc(unit_type)

        gamelib.debug_write(locations)
        gamelib.debug_write(game_state.turret_locations)

        for loc in locations:
            for unit in game_state.game_map[loc[0], loc[1]]:
                if unit.unit_type == unit_type and unit.upgraded == include_upgraded:
                    remove_locs.append(loc)

        game_state.attempt_remove(remove_locs)

    def is_ready_to_build_offensive(self, num_supports: int, num_walls: int, game_state, num_scouts=8) -> bool:
        """
        Checks if MP and SP are high enough.
        """
        sp_needed = num_supports * game_state.type_cost(SUPPORT)[SP] + num_walls * game_state.type_cost(WALL)[SP]
        mp_needed = num_scouts * game_state.type_cost(SCOUT)[MP]
        mp = game_state.project_future_MP(1, 0)
        gamelib.debug_write("MP " + str(mp))
        sp = self.calculate_possible_SP(game_state)
        gamelib.debug_write("SP " + str(sp))

        # if we have more than 9 MP (or mp_needed) and the turn number is close to next group of 10
        # then we will send out attack; otherwise we wait for want to save up our MP
        # removed 3 in turn_number since this is preparing for offense, so next turn will be ready for offense
        return mp > mp_needed and sp > sp_needed and (
                    game_state.turn_number % 10 not in [0, 1, 2] or game_state.my_health < 10)

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

    def add_v_turret_configuration(self, game_state, reduce_sides=0):
        """
        Adds initial v_turret_config. Reduce_sides removes from both left and right (for attack so not in the way)
        """
        left_turrets = [[5, 12], [6, 11], [8, 10]]
        right_turrets = [[22, 12], [21, 11], [19, 10]]
        if reduce_sides > len(left_turrets):
            reduce_sides = len(left_turrets)
        if reduce_sides > 0:
            del left_turrets[-reduce_sides:]
            del right_turrets[-reduce_sides:]

        middle_turrets = [[12, 9], [15, 9]]
        sides_zipped = [item for pair in zip(left_turrets, right_turrets) for item in pair]
        turret_locations = middle_turrets + sides_zipped
        game_state.attempt_spawn(TURRET, turret_locations)

    def upgrade_top_turrets(self, num, game_state):
        # sort list by largest y value
        sorted_turrets = sorted(game_state.turret_locations, key=lambda x: x[1], reverse=True)
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
        for turret_loc in game_state.turret_locations:
            game_state.attempt_remove(turret_loc)

    def calculate_possible_SP(self, game_state):
        sp = game_state.get_resource(SP, 0)
        for turret_loc in game_state.turret_locations:
            for unit in game_state.game_map[turret_loc[0], turret_loc[1]]:
                if unit.unit_type == TURRET and not unit.upgraded:
                    sp += unit.cost[SP] * 0.97
        return sp

    def prepare_offensive_hit(self, game_state):
        # remove non-upgraded turrets for offensive hit
        for turret_loc in game_state.turret_locations:
            for unit in game_state.game_map[turret_loc[0], turret_loc[1]]:
                if unit.unit_type == TURRET and not unit.upgraded:
                    removed = game_state.attempt_remove(turret_loc)
                    gamelib.debug_write("Removed: " + str(removed))

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

        self.add_walls_to_turrets(game_state.turret_locations, game_state)

    def add_walls_to_turrets(self, turret_locations, game_state):
        for loc in turret_locations:
            wall_loc = [[loc[0] - 1, loc[1] + 2], [loc[0], loc[1] + 2], [loc[0] + 1, loc[1] + 2]]
            gamelib.debug_write("Wall locations to add.")
            gamelib.debug_write(wall_loc)
            spawned = game_state.attempt_spawn(WALL, wall_loc)

    def build_reactive_defense(self, game_state):
        """
        This function builds reactive defenses based on where the enemy scored on us from.
        We can track where the opponent scored by looking at events in action frames 
        as shown in the on_action_frame function
        """
        for location in self.scored_on_locations:
            # Build turret one space above so that it doesn't block our own edge spawn locations
            build_location = [location[0], location[1] + 2]
            spawned = game_state.attempt_spawn(TURRET, build_location)

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


    def optimal_attack_path(self, game_state):
        # Create fake gamestate
        game_state_copy = copy.deepcopy(game_state)
        location_options = game_state_copy.game_map.get_edge_locations(game_state_copy.game_map.BOTTOM_LEFT) + game_state_copy.game_map.get_edge_locations(game_state_copy.game_map.BOTTOM_RIGHT)

        for loc in self.remove_loc_check:
            game_state_copy.game_map.remove_unit(loc)

        damages_taken = []
        damages_given_scout = []
        damages_given_demolisher = []
        # Get the damage estimate each path will take
        for location in location_options:
            path = game_state_copy.find_path_to_edge(location)
            damage_taken = 0
            damage_given = 0
            for path_location in path:
                # Get number of enemy turrets that can attack each location and multiply by turret damage
                damage_taken -= len(game_state.get_attackers(path_location, 0)) * gamelib.GameUnit(TURRET,
                                                                                             game_state.config).damage_i
                scout_attack_loc = game_state_copy.game_map.get_locations_in_range(path_location, gamelib.GameUnit(SCOUT, game_state_copy.config).attackRange)
                demolisher_attack_loc = game_state_copy.game_map.get_locations_in_range(path_location, gamelib.GameUnit(DEMOLISHER, game_state_copy.config).attackRange)

                scout_damage = 0
                demolisher_damage = 0

                for loc in scout_attack_loc:
                    if game_state_copy.contains_stationary_unit(loc) and loc[1] >= 14:
                        scout_damage += gamelib.GameUnit(SCOUT, game_state_copy.config).damage_f
                for loc in demolisher_attack_loc:
                    if game_state_copy.contains_stationary_unit(loc) and loc[1] >= 14:
                        demolisher_damage += gamelib.GameUnit(DEMOLISHER, game_state_copy.config).damage_f

            damages_taken.append(damage_taken)
            damages_given_scout.append(scout_damage)
            damages_given_demolisher.append(demolisher_damage)


        scout_heuristic = [a+b for a, b in zip(damages_taken, damages_given_scout)]
        demolisher_heuristic = [a+b for a, b in zip(damages_taken, damages_given_demolisher)]


        # Now just return the location that takes the least damage
        return game_state_copy.find_path_to_edge(location_options[scout_heuristic.index(min(scout_heuristic))]), game_state_copy.find_path_to_edge(location_options[demolisher_heuristic.index(min(demolisher_heuristic))])



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
            else:
                self.score_locations.append(location)


if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()
