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
        # Locations passed by reference to GameState. Should only be updated in GameState
        self.turret_locations = []
        self.wall_locations = []
        self.support_locations = []

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
        self.damaged_locations = []
        self.add_supports = False
        self.ready_attack = False
        self.attacked_in_last_round_and_removed_all = False
        self.potential_hole = []

        # needs to be cleared or updated each turn
        self.mobile_units_enemy_last_turn = {
            SCOUT: 0,
            DEMOLISHER: 0,
            INTERCEPTOR: 0
        }
        self.last_turn_enemy_MP = 0
        self.num_scored_on = 0
        self.last_turn_damaged = 0

        # keep for entire game
        self.MP_per_scored_on = []
        self.MP_per_damage = []
        self.MP_per_enemy_scouts_deployed = []

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

        # store statistics for when we get scored on and enemy's MP during that turn
        gamelib.debug_write("Last turn, was breached {0} times.", self.num_scored_on)
        gamelib.debug_write("Last turn, was damaged {0} times.", self.num_scored_on)

        if self.num_scored_on > 0:
            self.MP_per_scored_on.append((self.num_scored_on, self.last_turn_enemy_MP))

        if self.last_turn_damaged > 0:
            self.MP_per_damage.append((self.last_turn_damaged, self.last_turn_enemy_MP))

        if self.mobile_units_enemy_last_turn[SCOUT] > 0:
            self.MP_per_enemy_scouts_deployed.append((self.mobile_units_enemy_last_turn[SCOUT], self.last_turn_enemy_MP))

        avg_damage, avg_breached = self.predict_enemy_attack_magnitude(game_state)

        attack_in_progress = False
        if self.ready_attack and game_state.get_resource(MP, 0) > 9:
            # left is in our view
            enemy_has_most_defense_on_left = self.get_side_enemy_defense(game_state)
            # want to build attack on same side as their defense since it will go opposite side
            max_turrets = 1000
            if game_state.get_resource(SP, 0) < game_state.type_cost(SUPPORT)[SP] * 10 + game_state.type_cost(TURRET)[SP] * 5:
                max_turrets = 5
            self.build_attack(game_state, left=enemy_has_most_defense_on_left, max_turrets=max_turrets)
            attack_in_progress = True
            # remove offensive structure if not enough MP for next turn.
            # Do not remove if enemy health is lower than our MP units for next round.
            # Does MP update after putting scouts?
            new_mp = game_state.project_future_MP()
            if new_mp <= 9 and game_state.enemy_health > new_mp:
                self.refund_structures(SUPPORT, game_state, False)
                self.refund_structures(WALL, game_state, False)
                self.refund_structures(TURRET, game_state, False)
                self.attacked_in_last_round_and_removed_all = True
                self.ready_attack = False
        elif self.is_ready_to_build_offensive(4, 6, game_state) and len(game_state.turret_locations) > 2 and not self.attacked_in_last_round_and_removed_all:
            if not self.need_to_send_demolisher(game_state):
                self.refund_structures(TURRET, game_state, False)
                self.refund_structures(WALL, game_state, False)
                self.ready_attack = True
        else:
            self.attacked_in_last_round_and_removed_all = False

        if self.need_to_send_demolisher(game_state):
            demolisher_location = [3, 10]
            self.potential_hole = [4, 12]  # to let demolisher pass our defense
            if self.check_if_holes(demolisher_location, game_state):
                game_state.attempt_remove(demolisher_location)
                game_state.attempt_spawn(DEMOLISHER, demolisher_location, 2)
            else:
                removed = game_state.attempt_remove(self.potential_hole)
                if removed == 0:
                    game_state.attempt_remove(demolisher_location)
                    game_state.attempt_spawn(DEMOLISHER, demolisher_location, 2)

        self.add_corner_turrets(True, game_state)
        gamelib.debug_write(attack_in_progress)
        if not attack_in_progress:
            self.add_v_turret_configuration(game_state)
        else:
            self.add_v_turret_configuration(game_state, 2)

        # only block if not attacking
        if not attack_in_progress:
            other_walls = [[1, 12], [2, 12], [3, 12], [4, 12], [23, 12], [24, 12], [25, 12], [26, 12]]
            if len(self.potential_hole) != 0:
                other_walls.remove(self.potential_hole)
            game_state.attempt_spawn(WALL, other_walls)

        # always block middle
        self.block_middle_with_walls(3, 14, game_state)

        # self.upgrade_top_turrets(4, game_state)

        # if game_state.turn_number > 3 and game_state.get_resource(SP, 0) > 30:
        # interceptors_loc = self.create_interceptor_shooter(8, True, True, game_state)

        # should fortify most attacked locations, but make sure not to block offense since it will be upgraded units
        # since we are avoiding the edges, for the very front, if y + 2 doesn't work, try x +/- 2
        # could also aim interceptors at those spots (need to make sure speed and pathing works out)
        self.build_reactive_defense(game_state, attack_soon=(attack_in_progress or self.ready_attack))

        if attack_in_progress or self.ready_attack:
            gamelib.debug_write("SP left for defense")
            gamelib.debug_write(game_state.get_resource(SP, 0))
            offset_from_edge = 3  # to not block offensive

            no_right_offset = self.get_side_enemy_defense(game_state)  # if returns true, then left side is where attack is sent out, so right side should not be offset
            no_left_offset = not no_right_offset
            self.defend_lower_map(offset_from_edge, game_state, no_left_offset=no_left_offset, no_right_offset=no_right_offset)
        else:
            offset_from_edge = 0
            self.defend_lower_map(offset_from_edge, game_state)

        if self.ready_attack:
            self.refund_structures(TURRET, game_state, False)
            self.refund_structures(WALL, game_state, False)

        # clear placeholders for next turn stats
        self.num_scored_on = 0
        self.last_turn_damaged = 0
        self.mobile_units_enemy_last_turn[SCOUT] = 0
        self.mobile_units_enemy_last_turn[DEMOLISHER] = 0
        self.mobile_units_enemy_last_turn[INTERCEPTOR] = 0
        self.last_turn_enemy_MP = game_state.get_resource(MP, 1)
        self.potential_hole = []

        # doesn't really worked if path is blocked
        # if avg_breached + 5 > game_state.my_health or avg_damage > 7:
        if game_state.project_future_MP(player_index=1) > 12 or game_state.my_health < game_state.project_future_MP(player_index=1):
            self.send_interceptors_most_attacked(4, game_state)
            self.ready_attack = False

    def build_attack(self, game_state, left=True, max_turrets=1000):
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

        for turret in range(max_turrets):
            if turret < len(channel):
                game_state.attempt_spawn(SUPPORT, channel[turret])
            else:
                break

        game_state.attempt_spawn(WALL, channel)  # in case not enough SP

        # game_state.attempt_spawn(INTERCEPTOR, interceptor)  # not sure if needed all the time
        game_state.attempt_spawn(SCOUT, scout, 1000)

    def need_to_send_demolisher(self, game_state):
        demolisher_location = [3, 10]
        any_holes = self.check_if_holes(demolisher_location, game_state)
        enemy_walls = len(game_state.game_map.get_enemy_unit_locations(WALL))
        enemy_turrets = len(game_state.game_map.get_enemy_unit_locations(TURRET))
        return (not any_holes or enemy_turrets + enemy_walls > 25) and game_state.project_future_MP(0) > 9

    def check_if_holes(self, start_location, game_state):
        """
        Returns true if path reaches other side.
        """
        path = game_state.find_path_to_edge(start_location)
        if not path:
            return False

        found_edge = False
        our_hole = [4, 12]
        need_to_re_add_hole = False
        if game_state.contains_stationary_unit(our_hole):
            game_state.game_map.remove_unit(our_hole)
            need_to_re_add_hole = True

        for loc in path:
            if game_state.game_map.check_if_on_enemy_edge(loc):
                found_edge = True

        if need_to_re_add_hole:
            game_state.game_map.add_unit(WALL, our_hole)

        return found_edge


    def defend_lower_map(self, offset_from_edge: int, game_state, include_y_offset=True, no_left_offset=False, no_right_offset=False):
        """
        Uses remaining structure points to defend lower part of map.
        include_y_offset also offsets in y direction from the middle of board. Does not offset middle turrets.
        """
        left_edge = [[0, 13], [1, 12], [2, 11], [3, 10], [4, 9], [5, 8], [6, 7], [7, 6], [8, 5]]
        right_edge = [[27, 13], [26, 12], [25, 11], [24, 10], [23, 9], [22, 8], [21, 7], [20, 6], [19, 5]]
        bottom_left = [[7, 8], [9, 8], [11, 8], [10, 6]]
        bottom_right = [[16, 8], [18, 8], [20, 8], [17, 6]]
        bottom_middle = [[13, 5], [14, 5]]

        side_important = [[2, 11], [25, 11]]

        game_state.attempt_spawn(TURRET, side_important)
        game_state.attempt_upgrade(side_important)

        if include_y_offset:
            left_edge[:] = (loc for loc in left_edge if loc[1] <= 13 - offset_from_edge)
            right_edge[:] = (loc for loc in right_edge if loc[1] <= 13 - offset_from_edge)

        all_locations = [item for pair in zip(left_edge, right_edge) for item in pair] + bottom_middle \
                        + [item for pair in zip(bottom_left, bottom_right) for item in pair]

        gamelib.debug_write(all_locations)

        # apply x offsets
        for location in all_locations:
            if location[0] <= 13 and not no_left_offset:
                location[0] += offset_from_edge
            elif not no_right_offset:
                location[0] -= offset_from_edge

        if [3, 10] in all_locations:
            all_locations.remove([3, 10])

        # build turrets, and then change to walls if no more sp
        game_state.attempt_spawn(TURRET, all_locations)
        game_state.attempt_spawn(WALL, all_locations)

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

    def predict_enemy_attack_magnitude(self, game_state) -> (float, float):
        """
        Returns predicted magnitude of enemy attack (avg_damage, avg_breached)
        :param game_state: game state
        :param attack_magnitude: number of scouts deployed
        """
        enemy_current_mp = game_state.get_resource(MP, 1)

        total_damage_sum = 0
        num_damage_stats = 0

        # get damage usually inflicted at enemy_current_mp +/- 1
        for mp_per_damage in self.MP_per_damage:
            damage, mp = mp_per_damage
            if abs(mp - enemy_current_mp) <= 1:
                total_damage_sum += damage
                num_damage_stats += 1

        if num_damage_stats == 0:
            avg_damage = 0
        else:
            avg_damage = total_damage_sum / num_damage_stats

        num_breached_sum = 0
        num_breached_stats = 0

        # get number of locations usually breached at enemy_current_mp +/- 1
        for mp_per_scored_on in self.MP_per_scored_on:
            num_scored_on, mp = mp_per_scored_on
            if abs(mp - enemy_current_mp) <= 1:
                num_breached_sum += damage
                num_breached_stats += 1

        if num_breached_stats == 0:
            avg_breached = 0
        else:
            avg_breached = num_breached_sum / num_breached_stats

        return avg_damage, avg_breached

        """
        if len(self.MP_per_enemy_scouts_deployed) == 0:
            return 0

        num_attacks = 0
        enemy_current_mp = game_state.get_resource(MP, 1)
        for mp_per_scouts in self.MP_per_enemy_scouts_deployed:
            scouts_deployed, mp = mp_per_scouts
            if scouts_deployed >= attack_magnitude and abs(mp - enemy_current_mp) <= 1:
                num_attacks += 1

        if num_attacks == 0:
            return 0

        # effectiveness of attack
        successful_attacks_at_enemy_mp = 0
        for mp_per_scored_on in self.MP_per_scored_on:
            num_scored, mp = mp_per_scored_on
            if abs(mp - enemy_current_mp) <= 1:
                successful_attacks_at_enemy_mp += 1

        gamelib.debug_write("Number of attacks {0} at attack magnitude {1}", num_attacks, attack_magnitude)
        effectiveness = successful_attacks_at_enemy_mp / num_attacks
        gamelib.debug_write("Effectiveness {0}", effectiveness)

        return num_attacks / len(self.MP_per_enemy_scouts_deployed) * effectiveness
        """

    def send_interceptors_most_attacked(self, num, game_state):
        sorted_hits = self.get_sorted_hits(game_state)
        spawned = 0
        for i in range(num):
            if i < len(sorted_hits):
                sorted_hit = sorted_hits[i]
                if self.check_if_holes(sorted_hit, game_state):
                    spawned = game_state.attempt_spawn(INTERCEPTOR, sorted_hit)
                if spawned == 0:
                    # attempt to spawn close to location on board
                    is_left = sorted_hit[0] <= 13
                    if is_left:
                        lower_left = [sorted_hit[0] + 1, sorted_hit[1] - 1]
                        if self.check_if_holes(lower_left, game_state):
                            spawned = game_state.attempt_spawn(INTERCEPTOR, lower_left)
                        if spawned == 0:
                            upper_left = [sorted_hit[0] - 1, sorted_hit[1] + 1]
                            if self.check_if_holes(upper_left, game_state):
                                game_state.attempt_spawn(INTERCEPTOR, upper_left)
                    else:
                        lower_right = [sorted_hit[0] - 1, sorted_hit[1] - 1]
                        if self.check_if_holes(lower_right, game_state):
                            spawned = game_state.attempt_spawn(INTERCEPTOR, lower_right)
                        if spawned == 0:
                            upper_right = [sorted_hit[0] + 1, sorted_hit[1] + 1]
                            if self.check_if_holes(upper_right, game_state):
                                game_state.attempt_spawn(INTERCEPTOR, upper_right)

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

    def build_reactive_defense(self, game_state, attack_soon: bool):
        """
        This function builds reactive defenses based on where the enemy scored on us from.
        We can track where the opponent scored by looking at events in action frames 
        as shown in the on_action_frame function
        """
        # should fortify most attacked locations, but make sure not to block offense since it will be upgraded units
        # since we are avoiding the edges, for the very front, if y + 2 doesn't work, try x +/- 2
        # could also aim interceptors at those spots (need to make sure speed and pathing works out)

        locations_do_not_build = [3, 10]
        if attack_soon:
            locations_do_not_build = [[4, 11], [5, 11], [4, 12], [24, 12], [24, 11], [22,11]]

        sorted_hits = self.get_sorted_hits(game_state)

        for location in sorted_hits:
            # Build turret one space above so that it doesn't block our own edge spawn locations
            x, y = location  # converted into tuple for dictionary hashing
            build_location = [x, y + 2]
            if not game_state.can_spawn(WALL, build_location) or build_location in locations_do_not_build:
                x_shift = 2
                if x >= 14:
                    x_shift = -2
                build_location = [x + x_shift, y + 1]
                if not game_state.can_spawn(WALL, build_location) or build_location in locations_do_not_build:
                    build_location = [x + x_shift, y]

            if build_location not in locations_do_not_build:
                game_state.attempt_spawn(TURRET, build_location)
                game_state.attempt_spawn(WALL, build_location)  # at least a wall if the other doesn't work

    def get_sorted_hits(self, game_state):
        """
        Returns a list of locations by most hit to least hit
        """
        counts = dict()
        for i in self.scored_on_locations:
            loc = tuple(i)
            counts[loc] = counts.get(loc, 0) + 1

        # sorted by largest frequency
        return sorted(counts.keys(), key=lambda item: counts[item], reverse=True)

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
        damages = events["damage"]

        stationary_units = [0, 1, 2]

        turn_info = state["turnInfo"]
        phase = turn_info[0]
        turn_number = turn_info[1]
        action_phase = 1

        if phase == action_phase and turn_number == 0:
            # record enemy mobile units deployed
            p2_units = state["p2Units"]
            self.mobile_units_enemy_last_turn[SCOUT] = len(p2_units[3])
            self.mobile_units_enemy_last_turn[DEMOLISHER] = len(p2_units[4])
            self.mobile_units_enemy_last_turn[INTERCEPTOR] = len(p2_units[5])

        for damage in damages:
            location = damage[0]
            damage_taken = damage[1]
            unit_type = damage[2]
            player = damage[4]
            if player == 1 and unit_type in stationary_units:
                gamelib.debug_write("Got damage at: {}".format(location))
                self.damaged_locations.append(location)
                self.last_turn_damaged += damage_taken

        for breach in breaches:
            location = breach[0]
            unit_owner_self = True if breach[4] == 1 else False
            # When parsing the frame data directly, 
            # 1 is integer for yourself, 2 is opponent (StarterKit code uses 0, 1 as player_index instead)
            if not unit_owner_self:
                gamelib.debug_write("Got scored on at: {}".format(location))
                self.num_scored_on += 1
                self.scored_on_locations.append(location)
                gamelib.debug_write("All locations: {}".format(self.scored_on_locations))


if __name__ == "__main__":
    algo = AlgoStrategy()
    algo.start()
