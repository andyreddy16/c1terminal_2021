import gamelib
import random
import math
import warnings
from sys import maxsize
import json

class FirstAlgo(gamelib.AlgoCore):

    def __init__(self):
        # Stores the initial template

        # Corners of the filters in the basic template
        corners = [[0, 13], [2, 13], [8, 7], [12, 7], [12, 13]]
        all_filters = []

        # Adds all the locations in between the above corners to all_filters
        for i in range(len(corners) - 1):
            if corners[i+1][0] - corners[i][0] > 0:
                x_increment = 1
            elif corners[i+1][0] - corners[i][0] < 0:
                x_increment = -1
            else:
                x_increment = 0
            if corners[i+1][1] - corners[i][1] > 0:
                y_increment = 1
            elif corners[i+1][1] - corners[i][1] < 0:
                y_increment = -1
            else:
                y_increment = 0

            x = corners[i][0]
            y = corners[i][1]
            while x != corners[i+1][0] or y != corners[i+1][1]:
                all_filters.append([x, y])
                all_filters.append([27 - x, y])
                x += x_increment
                y += y_increment

        self.basic_template = {'filters': all_filters, 'destructors': [[11, 12], [16, 12], [1, 12], [26, 12], [12, 5], [15, 5]]}
        gamelib.debug_write("Beautiful")
        gamelib.debug_write(self.basic_template['filters'])

    def build(self, game_state, lst):
        priority = lst[0]
        unit = lst[1]
        position = lst[2]
        build = lst[3]

        if lst[3]:
            return game_state.attempt_spawn(unit, position)
        else:
            return game_state.attempt_upgrade(position)

    def build_funnel(self, game_state):
        firewalls = {
            0: FILTER,
            1: DESTRUCTOR,
            2: ENCRYPTOR
        }

        pqueue = []

        for x in range(3):
            pqueue.append([100, FILTER, [10 - x + 2, 13], True])
            pqueue.append([100, FILTER, [15 + x, 13], True])

            pqueue.append([95 - 30*x, DESTRUCTOR, [10 - x + 2, 12], True])
            pqueue.append([95 - 30*x, DESTRUCTOR, [15 + x, 12], True])

        for x in range(3):
            for y in range(11, 7, -1):
                pqueue.append([50 + y, firewalls[x], [10 - x + 2, y], True])
                pqueue.append([50 + y, firewalls[x], [15 + x, y], True])

        for y in range(13, 7, -1):
            pqueue.append([13 + y, None, [12, y], False])
            pqueue.append([10 + y, None, [11, y], False])
            pqueue.append([13 + y, None, [15, y], False])
            pqueue.append([10 + y, None, [16, y], False])
            pqueue.append([6  + y, None, [11, y], False])
            pqueue.append([6  + y, None, [15, y], False])

        pqueue = sorted(pqueue, key = lambda x: x[0], reverse = True)

        for item in pqueue:
            self.build(game_state, item)

    def on_game_start(self, config):
        self.config = config;
        global FILTER, ENCRYPTOR, DESTRUCTOR, PING, EMP, SCRAMBLER, UNIT_TO_ID
        FILTER, ENCRYPTOR, DESTRUCTOR, PING, EMP, SCRAMBLER = [config['unitInformation'][idx]["shorthand"] for idx in range(6)]
        self.scored_on_locations = []
        #self.init_funnel()


    def on_turn(self, turn_state):
        game_state = gamelib.GameState(self.config, turn_state)
        game_state.enable_warnings = False

        self.defense(game_state)
        self.offensive_strategy(game_state)

        game_state.submit_turn()

    def build_defenses(self, location_list, firewall_unit, game_state, row=None):
        for loc in location_list:
            if not type(loc) == list:
                loc = [loc, row]

            if game_state.can_spawn(firewall_unit, loc):
                game_state.attempt_spawn(firewall_unit, loc)
                gamelib.debug_write("{firewall_unit} deployed at {loc}")
                game_state._player_resources[0]['cores'] -= game_state.type_cost(firewall_unit)[0]

            elif not game_state.contains_stationary_unit(loc):
                return False

        return True

    def defense(self, game_state):


        if not self.build_defenses(self.basic_template['filters'][:len(self.basic_template['filters']) // 2], FILTER, game_state):
            return

        if not self.build_defenses(self.basic_template['destructors'], DESTRUCTOR, game_state):
            return

        if not self.build_defenses(self.basic_template['filters'][len(self.basic_template['filters']) // 2:], FILTER, game_state):
            return

        row = 11
        destructors = [2, 25, 6, 21, 11, 16]
        if not self.build_defenses(destructors, DESTRUCTOR, game_state, row=row):
            return

        if not self.build_funnel(game_state):
            return

        # filters = [3, 24, 4, 23, 5, 22, 7, 20, 8, 19, 9]
        # if not self.build_defenses(filters, FILTER, game_state, row=row):
        #     return

    def reactive_defense(self, game_state):
        for loc in self.scored_on_locations:
            gamelib.debug_write("updating most important filters")
            if 0 < loc[0] < 8:
                self.basic_template['filters'].insert(0, self.basic_template['filters'].pop(self.basic_template['filters'].index([loc[0] + 1, loc[1] + 1])))
            elif 27 > loc[0] > 19:
                self.basic_template['filters'].insert(0, self.basic_template['filters'].pop(self.basic_template['filters'].index([loc[0] - 1, loc[1] + 1])))


    def attack(self, game_state):
        pass

    def on_action_frame(self, turn_string):
        """
        This is the action frame of the game. This function could be called
        hundreds of times per turn and could slow the algo down so avoid putting slow code here.
        Processing the action frames is complicated so we only suggest it if you have time and experience.
        Full doc on format of a game frame at: https://docs.c1games.com/json-docs.html
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

    def filter_blocked_locations(self, locations, game_state):
        filtered = []
        for location in locations:
            if not game_state.contains_stationary_unit(location):
                filtered.append(location)
        return filtered

    def offensive_strategy(self, game_state):
        our_resources, enemy_resources = game_state.get_resources(player_index=0), game_state.get_resources(
            player_index=1)

        prob = random.random()

        # Switch focus to "defensive" offensive
        if enemy_resources[1] >= 10 and prob > 0.5:
            start_locs = [[13, 0], [14, 0]]
            for i in range(math.ceil(enemy_resources[1] / 5) - 1):
                game_state.attempt_spawn(SCRAMBLER, start_locs[i % 2])
        else:
            if prob <= 0.1:
                return

            attack_positions_left = self.filter_blocked_locations([[i, 13 - i] for i in range(14)], game_state)
            attack_positions_right = self.filter_blocked_locations([[i + 14, i] for i in range(14)], game_state)

            # Evaluate defensive rating
            attack_rating_single = []
            attack_rating_double = []
            for attack_pos in attack_positions_left + attack_positions_right:
                hit_profit, damage, i = [0], 0, 0
                path = game_state.find_path_to_edge(attack_pos)
                path_length = len(path)
                for loc in path:
                    encounters = game_state.game_map.get_locations_in_range(loc, 4.5)
                    offensive_hits = len([game_state.contains_stationary_unit(unit) for unit in encounters])
                    defensive_hits = len(game_state.get_attackers(loc, 1))
                    if defensive_hits + damage <= 2:
                        hit_profit.append((offensive_hits - defensive_hits + hit_profit[i]))
                        damage += defensive_hits
                        i += 1
                        if damage >= 1:
                            attack_rating_single.append((attack_pos, max(hit_profit), path_length))
                    else:
                        break
                attack_rating_double.append((attack_pos, max(hit_profit), path_length))
            attack_rating_single.sort(key=lambda x: x[1], reverse=True)
            attack_rating_double.sort(key=lambda x: x[1], reverse=True)
            top_pos_single, top_pos_double = attack_rating_single[:2], attack_rating_double[:2]

            num_emp = int(game_state.number_affordable(EMP))
            emp_deployed = 0
            total_hits = 0
            if game_state.turn_number < 30:
                for i in range(2):
                    if attack_rating_double[i][1] >= 1.5 * attack_rating_single[0][1]:
                        if num_emp >= 2 and prob > 0.25:
                            game_state.attempt_spawn(EMP, top_pos_double[i][0], num=2)
                            num_emp -= 2
                            emp_deployed += 2
                            total_hits += top_pos_double[i][1]
                    elif attack_rating_single[i][1] >= 7:
                        if num_emp >= 2 and prob > 0.16:
                            game_state.attempt_spawn(EMP, top_pos_single[i][0], num=2)
                            num_emp -= 2
                            emp_deployed += 2
                            total_hits += top_pos_single[i][1]
                    else:
                        if prob > 0.25:
                            game_state.attempt_spawn(PING, top_pos_single[i][0],
                                                     num=int(0.4 * game_state.number_affordable(PING)))

                if emp_deployed > 0:
                    cost = int(our_resources[1] - emp_deployed)
                    if total_hits >= 15:
                        game_state.attempt_spawn(PING, sorted(attack_rating_single, key=lambda x: x[2])[0][0], num=cost)
            else:
                if game_state.turn_number % 2 == 0 or game_state.enemy_health <= 5:
                    game_state.attempt_spawn(EMP, top_pos_double[0][0], num=num_emp - 1)
                    game_state.attempt_spawn(PING, sorted(attack_rating_single, key=lambda x: x[2])[0][0],
                                             num=int(game_state.number_affordable(PING)))


if __name__ == "__main__":
    algo = FirstAlgo()
    algo.start()