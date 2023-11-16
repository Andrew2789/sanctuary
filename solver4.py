from workshop_items import *
from planning import *
from sanct_utils import *
from ocr import extract_cycle_from_screenshots, extract_cycle_from_snips
import joblib, itertools
from os import path, listdir, rename, makedirs
from random import random, shuffle
from multiprocessing import Pool
from time import time

NUM_PROCESSES = 12

def find_best_crafts_iter_combo_value_chunk(param_chunk, cycle, cycle_index, cycle_starting_grooves, cycle_starting_amounts_produced, season_data):
	"""note: this only tests permutation 0 of each combo, with 3 workshops and nothing else on that cycle, and no concern for later cycles. this is acceptable for runtime i think seeing as its just the coarse pass"""
	valued_combos = []
	for combo in param_chunk:
		starting_groove = cycle_starting_grooves[cycle_index]
		amounts_produced_instance = cycle_starting_amounts_produced[cycle_index].copy()
		value = combo.value(season_data, cycle, starting_groove, amounts_produced=amounts_produced_instance)
		groove_value = 0
		if starting_groove < MAX_GROOVE:
			groove_value = guess_groove_value(starting_groove, starting_groove + len(combo.permutations[0]) - 1, cycle_index) #assuming unbroken combo = len-1 groove gain 
		valued_combos.append((value + groove_value, combo))

	return cycle_index, valued_combos

def find_best_crafts_iter_replacements_chunk(param_chunk, current_value, current_best_combos, rest_days, season_data):
	test_cycle = current_best_combos[:]
	best_replacement = (0, None, -1, 0, []) #(value, combo, combo_rank, cycle_index, replace_indices)
	for cycle_index, replace_indices, combo, combo_rank in param_chunk:
		test_cycle[cycle_index] = current_best_combos[cycle_index][:] #can remove this?
		remove_combos(test_cycle[cycle_index], replace_indices, sorted=True)
		test_cycle[cycle_index].append((combo, len(replace_indices))) #add our new combo

		edited_plan = Plan(rest_days, test_cycle, season_data)
		net_value = edited_plan.value - current_value

		if net_value > best_replacement[0]:
			best_replacement = (net_value, combo, combo_rank, cycle_index, replace_indices)

		test_cycle[cycle_index] = current_best_combos[cycle_index][:]

	return best_replacement

def find_best_crafts_combinatorial_replacements_chunk(param_chunk, current_value, current_best_combos, rest_days, season_data):
	test_cycle = current_best_combos[:]
	best_replacement = (0, None, -1, 0, None, -1, 0, 0) #(value, combo1, combo1_rank, combo1_amt, combo2, combo2_rank, combo2_amt, cycle_index)
	for cycle_index, combo1, combo1_rank, combo2, combo2_rank in param_chunk:
		for combo1_amt, combo2_amt in ((3, 1), (2, 2)):
			test_cycle[cycle_index] = [
				(combo1, combo1_amt),
				(combo2, combo2_amt)
			]
			edited_plan = Plan(rest_days, test_cycle, season_data)
			net_value = edited_plan.value - current_value

			if net_value > best_replacement[0]:
				best_replacement = (net_value, combo1, combo1_rank, combo1_amt, combo2, combo2_rank, combo2_amt, cycle_index)

			test_cycle[cycle_index] = current_best_combos[cycle_index][:]

	return best_replacement

def find_best_crafts_iter(items_by_name, combos, season_data, pred_cycle, locked_in_days, rest_days, craft_cycles, pool=None, verbose=False):
	NUM_COMBOS_TO_CHECK = 100000

	NUM_REPLACEMENTS_TO_CHECK_PRED_CYCLE = {
		1: (32768, 8192, 192),
		2: (4096, 256, 160),
		3: (4096, 256, 128),
		4: (4096, 256, 128),
	}
	UPGRADE_REPL_PROP = 0.5
	NUM_REPL_HIGH, NUM_REPL_LOW, NUM_COMB_REPL = NUM_REPLACEMENTS_TO_CHECK_PRED_CYCLE[pred_cycle]
	num_replacements_to_check = NUM_REPL_HIGH

	COMBO_CHUNK_SIZE = 10000
	REPLACEMENTS_CHUNK_SIZE = 2000

	do_combinatorial = False

	current_best_combos = locked_in_days[:]
	stove = items_by_name["Isleworks Stove"]
	stove_combo = Combo([[stove, stove, stove, stove]])
	for i in range(len(locked_in_days), 5):
		current_best_combos.append([(stove_combo, 4)]) #add a low value placeholder combo
	current_plan = Plan(rest_days, current_best_combos, season_data)

	max_used_rank = 0
	last_changed_cycle = -1
	cycle_considered_combos = dict()
	cycle_valued_combos = dict()
	remaining_default_cycles = 5 - len(locked_in_days)
	total_value = 1
	while total_value > 0:
		cycle_starting_grooves = {0: 0}
		cycle_starting_amounts_produced = {0: dict()}
		for cycle_index, cycle in enumerate(craft_cycles):
			amounts_produced_instance = cycle_starting_amounts_produced[cycle_index].copy()
			groove = cycle_starting_grooves[cycle_index]

			_, _, groove = cycle_value(current_best_combos[cycle_index], season_data, cycle, groove, amounts_produced_instance)
			cycle_starting_grooves[cycle_index + 1] = groove
			cycle_starting_amounts_produced[cycle_index + 1] = amounts_produced_instance

		if remaining_default_cycles == 0: #reset ranked comboes (apart from c2/ind 0 since that'll never change), swap to fast mode
			cycle_considered_combos = {len(locked_in_days): cycle_considered_combos[len(locked_in_days)]} #TODO - pred_cycle-1? whatever the first non-locked in one is len(locked_in_days) also maybe
			num_replacements_to_check = NUM_REPL_LOW

		combo_chunks = []

		#create chunks of combos to process for each cycle
		start_time = time()
		for cycle_index, cycle in enumerate(craft_cycles):
			if cycle_index < len(locked_in_days) or cycle_index <= last_changed_cycle:
				continue

			combo_list = cycle_considered_combos.get(cycle_index, combos)
			combo_chunks += [(cycle_index, cycle, combo_list[i*COMBO_CHUNK_SIZE:(i+1)*COMBO_CHUNK_SIZE]) for i in range(ceil(len(combo_list)/COMBO_CHUNK_SIZE))]

		#process chunks to find each combo value
		if pool is None:
			processed_chunks = [find_best_crafts_iter_combo_value_chunk(param_chunk, cycle, cycle_index, cycle_starting_grooves, cycle_starting_amounts_produced, season_data) for (cycle_index, cycle, param_chunk) in combo_chunks]
		else:
			arg_sets = [(param_chunk, cycle, cycle_index, cycle_starting_grooves, cycle_starting_amounts_produced, season_data) for (cycle_index, cycle, param_chunk) in combo_chunks]
			processed_chunks = pool.starmap(find_best_crafts_iter_combo_value_chunk, arg_sets)

		# recombine processed chunks by cycle
		for cycle_index in set([cycle_index for cycle_index, _ in processed_chunks]):
			cycle_valued_combos[cycle_index] = [] #clear any cycles that were reprocessed this iteration
		for cycle_index, valued_comboes in processed_chunks:
			cycle_valued_combos[cycle_index] += valued_comboes

		if verbose: print(f"combo time: {time() - start_time:.2f}s\t", end="")
		start_time = time()

		#create list of jobs for full plan valuing
		for cycle_index in cycle_valued_combos.keys():
			cycle_valued_combos[cycle_index].sort(key=lambda x: x[0])
			if cycle_index not in cycle_considered_combos.keys() and len(cycle_valued_combos[cycle_index]) > NUM_COMBOS_TO_CHECK:
				cycle_considered_combos[cycle_index] = [combo for coarse_score, combo in cycle_valued_combos[cycle_index][-NUM_COMBOS_TO_CHECK:]] #after first sort, only check top 100k
			cycle_valued_combos[cycle_index] = cycle_valued_combos[cycle_index][-num_replacements_to_check:]

		if do_combinatorial:
			best_replacement = (0, None, -1, 0, None, -1, 0, 0) #(value, combo1, combo1_rank, combo1_amt, combo2, combo2_rank, combo2_amt, cycle_index)

			#build param blocks
			all_params = []
			for cycle_index in cycle_valued_combos.keys():
				to_combine = cycle_valued_combos[cycle_index][-NUM_COMB_REPL:]
				for combo1_rank, (coarse_score, combo1) in enumerate(reversed(to_combine)):
					for combo2_rank, (coarse_score, combo2) in enumerate(reversed(to_combine)):
						all_params.append((cycle_index, combo1, combo1_rank, combo2, combo2_rank))

			#run blocks
			if pool is None:
				best_replacement = find_best_crafts_combinatorial_replacements_chunk(all_params, current_plan.value, current_best_combos, rest_days, season_data)
			else:
				arg_sets = [(all_params[i*REPLACEMENTS_CHUNK_SIZE:(i+1)*REPLACEMENTS_CHUNK_SIZE], current_plan.value, current_best_combos, rest_days, season_data) for i in range(ceil(len(all_params)/REPLACEMENTS_CHUNK_SIZE))]
				best_replacement = sorted(pool.starmap(find_best_crafts_combinatorial_replacements_chunk, arg_sets), key=lambda x: x[0])[-1]

			if verbose: print(f"replacements time ({len(all_params)*2}): {time() - start_time:.2f}s combinatorial repl length: {NUM_COMB_REPL}")

			total_value, combo1, combo1_rank, combo1_amt, combo2, combo2_rank, combo2_amt, last_changed_cycle = best_replacement
			remaining_default_cycles -= 1

			if total_value > 0:
				current_best_combos[last_changed_cycle] = [
					(combo1, combo1_amt),
					(combo2, combo2_amt)
				]
				current_plan = Plan(rest_days, current_best_combos, season_data)
				#NOTE: the following line deletes all suboptimal permutations on the best plan which i think doesnt stop convergence on optimal solution, can remove it to test all permutations but it runs ~3.5x slower
				current_best_combos = current_plan.best_combos

				combo_rank = max(combo1_rank, combo2_rank)
				max_used_rank = max(max_used_rank, combo_rank)
				if verbose: 
					print(f"r{combo_rank}  \tscore {total_value}  c{craft_cycles[last_changed_cycle]}")
					current_plan.display()

				if combo_rank > num_replacements_to_check * UPGRADE_REPL_PROP and num_replacements_to_check*2 < NUM_REPL_HIGH:
					print(f"NUM_REPL {num_replacements_to_check} -> {num_replacements_to_check*2} (r{combo_rank}>{num_replacements_to_check}*{UPGRADE_REPL_PROP})")
					num_replacements_to_check *= 2


			elif num_replacements_to_check < NUM_REPL_HIGH: #must be combinatorial on this branch anyway
				print(f"No more combinatorial improvements, swapping to {NUM_REPL_HIGH}")
				do_combinatorial = False
				num_replacements_to_check = NUM_REPL_HIGH
				total_value = 1
			else:
				raise Exception(f"uh oh, this shouldn't happen.. num_repl: {num_replacements_to_check}, num_high: {NUM_REPL_HIGH}")

		else:
			best_replacement = (0, None, -1, 0, []) #(value, combo, combo_rank, cycle_index, replace_indices)
			if remaining_default_cycles > 0:
				nums_to_replace = [4] #while theres still whole default cycles, go for full replacement of all workshops
			else:
				nums_to_replace = list(range(1, 5)) #replace 1-4 workshops

			all_params = []
			for cycle_index in cycle_valued_combos.keys():
				all_replace_indices = []
				for num_workshops_replace in nums_to_replace:
					all_replace_indices += set(itertools.combinations(get_possible_indices(current_best_combos[cycle_index]), num_workshops_replace))

				for replace_indices in all_replace_indices:
					all_params += [(cycle_index, replace_indices, combo, combo_rank) for combo_rank, (coarse_score, combo) in enumerate(reversed(cycle_valued_combos[cycle_index]))]

			repl_chunk_size = min(6400, max(ceil(len(all_params)/64), 128))
			if pool is None:
				best_replacement = find_best_crafts_iter_replacements_chunk(all_params, current_plan.value, current_best_combos, rest_days, season_data)
			else:
				arg_sets = [(all_params[i*repl_chunk_size:(i+1)*repl_chunk_size], current_plan.value, current_best_combos, rest_days, season_data) for i in range(ceil(len(all_params)/repl_chunk_size))]
				#joblib.dump(arg_sets, "arg_sets-0.pth")
				best_replacement = sorted(pool.starmap(find_best_crafts_iter_replacements_chunk, arg_sets), key=lambda x: x[0])[-1]

			if verbose: print(f"replacements time ({len(all_params)}): {time() - start_time:.2f}s chunk size {repl_chunk_size}")

			total_value, combo, combo_rank, last_changed_cycle, replace_indices = best_replacement
			remaining_default_cycles -= 1

			if total_value > 0:
				remove_combos(current_best_combos[last_changed_cycle], replace_indices, sorted=True)
				current_best_combos[last_changed_cycle].append((combo, len(replace_indices)))
				current_plan = Plan(rest_days, current_best_combos, season_data)
				#NOTE: the following line deletes all suboptimal permutations on the best plan which i think doesnt stop convergence on optimal solution, can remove it to test all permutations but it runs ~3.5x slower
				current_best_combos = current_plan.best_combos

				max_used_rank = max(max_used_rank, combo_rank)
				if verbose: 
					if remaining_default_cycles < 0:
						print(f"r{combo_rank}  \tscore {total_value}  c{craft_cycles[last_changed_cycle]}")
						current_plan.display()
					else:
						print(f"r{combo_rank}  \tscore {total_value}  c{craft_cycles[last_changed_cycle]}  {len(replace_indices)}*{combo.permutations[0]}")

				if combo_rank > num_replacements_to_check * UPGRADE_REPL_PROP and num_replacements_to_check*2 < NUM_REPL_HIGH:
					print(f"NUM_REPL {num_replacements_to_check} -> {num_replacements_to_check*2} (r{combo_rank}>{num_replacements_to_check}*{UPGRADE_REPL_PROP})")
					num_replacements_to_check *= 2

			elif num_replacements_to_check < NUM_REPL_HIGH: #cant be on combinatorial if its on this branch
				print(f"No more improvements at repl {num_replacements_to_check}, trying combinatorial pass")
				do_combinatorial = True
				total_value = 1
			else:
				print(f"No improvement, exiting... (max used rank {max_used_rank})")

	final_plan = Plan(rest_days, current_best_combos, season_data)
	print(f"Final plan for rest days {rest_days}: ")
	final_plan.display()

	return (max_used_rank, final_plan)

def add_favours_combo_value_chunk(param_chunk, cycle, cycle_index, favours, favour_incentive, cycle_starting_grooves, cycle_starting_amounts_produced, season_data):
	valued_favour_comboes = []
	for combo in param_chunk:
		amounts_produced_instance = cycle_starting_amounts_produced[cycle_index].copy()
		score = combo.value(season_data, cycle, cycle_starting_grooves[cycle_index], amounts_produced=amounts_produced_instance)
		incentive = get_amt_favours_produced(combo, favours, capped=True)
		incentive_sum = sum(incentive.values())*favour_incentive
		valued_favour_comboes.append((score + incentive_sum, combo))

	return cycle_index, valued_favour_comboes

def add_favours_replacements_chunk(param_chunk, current_best_combos, favours, favour_incentive, remaining_favours, season_data, original_plan):
	test_cycle = current_best_combos[:]
	best_replacement = (-float("inf"), 0, 0, dict(), dict(), None, -1, 0, 0) #(value + incentive_sum, net_value, incentive_sum, net_favours, combo, combo_rank, cycle_index, replace_index)
	for cycle_index, replace_index, combo, combo_rank in param_chunk:
		test_cycle[cycle_index] = current_best_combos[cycle_index][:]
		removed_favours = get_amt_favours_produced(test_cycle[cycle_index][replace_index][0], favours, capped=False)
		remove_one_combo(test_cycle[cycle_index], replace_index)
		test_cycle[cycle_index].append((combo, 1)) #add our new combo x1

		edited_plan = Plan(original_plan.rest_days, test_cycle, season_data)
		net_value = edited_plan.value - original_plan.value
		added_favours = get_amt_favours_produced(combo, favours, capped=False)
		net_favours = {name: added_favours[name] - removed_favours[name] for name in favours.keys() if added_favours[name] - removed_favours[name] != 0}
		net_favours_capped = dict()
		for name in net_favours.keys():
			if remaining_favours[name] >= 0: #we dont want to lose any - cant exceed cap but can go negative
				net_favours_capped[name] = min(remaining_favours[name], net_favours[name])
			elif net_favours[name] - remaining_favours[name] < 0: #if we had a surplus but removed so much to need more again
				net_favours_capped[name] = net_favours[name] - remaining_favours[name]
			else:
				net_favours_capped[name] = 0

			if remaining_favours[name] != 1 and remaining_favours[name] - net_favours[name] == 1: #we reduced it to only 1 left, bad
				net_favours_capped[name] -= 1 #apply a penalty of 1

		incentive_sum = sum(net_favours_capped.values()) * favour_incentive

		value = net_value + incentive_sum
		if value > best_replacement[0]:
			best_replacement = (value, net_value, incentive_sum, net_favours, net_favours_capped, combo, combo_rank, cycle_index, replace_index)

		#remove changes before next iter
		test_cycle[cycle_index] = current_best_combos[cycle_index][:]

	return best_replacement

def add_favours(favours, favour_combos, season_data, pred_cycle, craft_cycles, plan, pool=None, verbose=False):
	NUM_COMBOS_TO_CHECK = 8192

	COMBO_CHUNK_SIZE = 1024
	REPLACEMENTS_CHUNK_SIZE = 256

	favour_incentive = 128 #increase as needed

	current_best_combos = plan.best_combos[:]
	remaining_favours = favours.copy()

	while any(value > 0 for favour_name, value in remaining_favours.items()):
		cycle_starting_grooves = {0: 0}
		cycle_starting_amounts_produced = {0: dict()}
		for cycle_index, cycle in enumerate(craft_cycles):
			amounts_produced_instance = cycle_starting_amounts_produced[cycle_index].copy()
			groove = cycle_starting_grooves[cycle_index]

			_, _, groove = cycle_value(current_best_combos[cycle_index], season_data, cycle, groove, amounts_produced_instance)
			cycle_starting_grooves[cycle_index + 1] = groove
			cycle_starting_amounts_produced[cycle_index + 1] = amounts_produced_instance

		#initialize remaining favours with current best combos
		remaining_favours = favours.copy()
		for name in remaining_favours.keys():
			remaining_favours[name] -= cycle_starting_amounts_produced[5].get(name, 0)
		if all(remaining_favours[name] <= 0 for name in remaining_favours.keys()):
			print(f"No need to add favours, already there ({remaining_favours})")
			break #solved already on iter 0

		best_replacement = (-float("inf"), 0, 0, dict(), None, -1, 0, 0) #(value + incentive_sum, net_value, incentive_sum, net_favours, combo, combo_rank, cycle_index, replace_index)
		cycle_valued_combos = dict()
		combo_chunks = []
		for cycle_index, cycle in enumerate(craft_cycles):
			if cycle <= pred_cycle:
				continue

			for name in favours.keys():
				if remaining_favours[name] > 0:
					combo_chunks += [(cycle_index, cycle, favour_combos[name][i*COMBO_CHUNK_SIZE:(i+1)*COMBO_CHUNK_SIZE]) for i in range(ceil(len(favour_combos[name])/COMBO_CHUNK_SIZE))]

		if pool is None:
			processed_chunks = [add_favours_combo_value_chunk(param_chunk, cycle, cycle_index, favours, favour_incentive, cycle_starting_grooves, cycle_starting_amounts_produced, season_data) for (cycle_index, cycle, param_chunk) in combo_chunks]
		else:
			arg_sets = [(param_chunk, cycle, cycle_index, favours, favour_incentive, cycle_starting_grooves, cycle_starting_amounts_produced, season_data) for (cycle_index, cycle, param_chunk) in combo_chunks]
			processed_chunks = pool.starmap(add_favours_combo_value_chunk, arg_sets)

		for cycle_index, valued_comboes in processed_chunks:
			cycle_valued_combos[cycle_index] = cycle_valued_combos.get(cycle_index, []) + valued_comboes

		all_params = []
		for cycle_index in cycle_valued_combos.keys():
			cycle_valued_combos[cycle_index].sort(key=lambda x: x[0])
			cycle_valued_combos[cycle_index] = cycle_valued_combos[cycle_index][-NUM_COMBOS_TO_CHECK:]
			for combo_rank, (coarse_score, combo) in enumerate(reversed(cycle_valued_combos[cycle_index])):
				all_params += [(cycle_index, i, combo, combo_rank) for i in range(len(current_best_combos[cycle_index]))]

		if pool is None:
			best_replacement = add_favours_replacements_chunk(all_params, current_best_combos, favours, favour_incentive, remaining_favours, season_data, plan)
		else:
			arg_sets = [(all_params[i*REPLACEMENTS_CHUNK_SIZE:(i+1)*REPLACEMENTS_CHUNK_SIZE], current_best_combos, favours, favour_incentive, remaining_favours, season_data, plan) for i in range(ceil(len(all_params)/REPLACEMENTS_CHUNK_SIZE))]
			best_replacement = sorted(pool.starmap(add_favours_replacements_chunk, arg_sets), key=lambda x: x[0])[-1]

		total_value, net_value, incentive_sum, net_favours, net_favours_capped, combo, combo_rank, cycle_index, replace_index = best_replacement

		if incentive_sum == 0 or sum(net_favours_capped.values()) < 0: #no progress was made towards remaining favours - either replaced by same, or replaced with something that produced less favour items
			if verbose: print(f"oops, favour incentive {favour_incentive} -> {favour_incentive*2}")
			favour_incentive *= 2
		else:
			if verbose: print(f"r{combo_rank} score {total_value} ({net_value} val + {incentive_sum} inc) net favours {net_favours} cycle {craft_cycles[cycle_index]}")
			remove_one_combo(current_best_combos[cycle_index], replace_index)
			for item_name, amount in net_favours.items():
				remaining_favours[item_name] -= amount
			added = False
			for i, (existing_combo, num_workshops) in enumerate(current_best_combos[cycle_index]):
				# print(existing_combo, combo)
				if type(existing_combo) is Combo:
					existing_combo = existing_combo.permutations[0]
				if existing_combo == combo.permutations[0]:
					current_best_combos[cycle_index][i] = (combo, num_workshops + 1)
					added = True
					break

			if not added: #couldnt just increment num_workshops as combo didnt already exist in this cycle
				current_best_combos[cycle_index].append((combo, 1))
			if verbose: print(f"remaining favours: {remaining_favours}")

	final_plan = Plan(plan.rest_days, current_best_combos, season_data)
	if verbose: 
		print(f"\nFinal remaining favours: {remaining_favours}")
		final_plan.display()

	return final_plan

def find_plans_single_favours(combos, items_by_name, season_data, pred_cycle, locked_in_days=[], locked_in_rest_days=[1], favours=dict(), only_favours=False, threading=True, verbose=True):
	if verbose: display_season_data(season_data)

	rest_day_combos = get_valid_rest_day_combos(locked_in_days, locked_in_rest_days)
	print(f"locked in days: {locked_in_days}, locked in rest days: {locked_in_rest_days}, possible rest days: {rest_day_combos}")

	pool = None
	if threading: pool = Pool(processes=NUM_PROCESSES)

	start_time = time()
	max_used_rank = -1
	best_plans = []
	if only_favours:
		best_plans.append(Plan(locked_in_rest_days, locked_in_days, season_data))
	else:
		for rest_days in rest_day_combos:
			if verbose: print(f"solving rest days {rest_days}")
			craft_cycles = list(range(1, 8))
			for rest_day in rest_days:
				craft_cycles.remove(rest_day)

			rest_day_start = time()
			max_used_rank_iter, best_plan = find_best_crafts_iter(items_by_name, combos, season_data, pred_cycle, locked_in_days, rest_days, craft_cycles, pool, verbose=verbose)
			max_used_rank = max(max_used_rank, max_used_rank_iter)
			best_plans.append(best_plan)
			time_total = time() - rest_day_start
			print(f"rest days {rest_days} done in {time_total/60:.2f}m")

	best_plans = sorted(best_plans, key=lambda plan: plan.value)
	time_total = (time() - start_time)/60
	print(f"\n---- Max rank used: {max_used_rank}, Time {time_total:.2f}m ----\n")
	# print("\n---- Best plans for each rest day combo: ----\n")
	# for best_plan in best_plans:
	# 	best_plan.display()

	best_plan = best_plans[-1]

	if len(favours.keys()) > 0:
		favour_combos = {name: [] for name in favours.keys()}
		for combo in combos:
			str_combo_items = [item.name for item in combo.permutations[0]]
			for name in favours.keys():
				if name in str_combo_items:
					favour_combos[name].append(combo)
		if verbose: print(f"favour combos len: {[(name, len(favour_combos[name])) for name in favours.keys()]}")


		craft_cycles = list(range(1, 8))
		for rest_day in best_plan.rest_days:
			craft_cycles.remove(rest_day)
		best_plan = add_favours(favours, favour_combos, season_data, pred_cycle, craft_cycles, best_plan, pool, verbose=verbose)
	if pool is not None: pool.close()

	return best_plan

def predict_next_season(current_week_num, blacklist, blacklist_ingredients):
	items = load_items(blacklist=blacklist, blacklist_ingredients=blacklist_ingredients)
	combos = find_all_combos(items, allow_load=False)
	season_data = read_season_data(current_week_num, verbose=True)

	next_season_data = {item_name: ItemSeasonData(item_name, POPULARITY_VALUES[item_season_data.predicted_demand], "Average") for item_name, item_season_data in season_data.items()}
	for item_name in next_season_data.keys():
		next_season_data[item_name].determine_pattern()

	for item_name in next_season_data.keys():
		next_season_data[item_name].guess_supply()

	best_plan = find_plans_single_favours(combos, items_by_name, next_season_data, pred_cycle=1)
	best_plan.display(show_mats=True, file_name=path.join(f"week_{current_week_num}", "display", f"next_season_display.txt"))

def save_task(week_num, pred_cycle, task_name, best_plan):
	num_locked_in_combos = 0
	num_locked_in_rest_days = 0
	for i in range(1, pred_cycle + 1 + 1): #look ahead by 1 cycle
		if i in best_plan.rest_days:
			num_locked_in_rest_days += 1
		else:
			num_locked_in_combos += 1
	#save as json
	task_data = dict()
	task_data["name"] = task_name
	task_data["rest_days"] = best_plan.rest_days[:num_locked_in_rest_days]
	task_data["combos"] = combos_to_text_list(best_plan.best_combos[:num_locked_in_combos])

	task_data["full_rest_days"] = best_plan.rest_days
	task_data["full_combos"] = combos_to_text_list(best_plan.best_combos)
	out_name = f"c{pred_cycle}_{task_name}.json"
	write_json(path.join(f"week_{week_num}", "saves", out_name), task_data)

	return out_name

def run_cycle_prediction(combos, items_by_name, week_num, pred_cycle, task_name, locked_in_days=[], locked_in_rest_days=[1], favours=dict(), blacklist=[], only_favours=False, threading=True):
	if len(blacklist) > 0:
		items = load_items(blacklist=blacklist)
		combos = find_all_combos(items, allow_load=False) #use default combos if no blacklist
	season_data = read_season_data(week_num, verbose=True, check_last_season=pred_cycle == 1) 
		
	if only_favours and pred_cycle + 1 in locked_in_rest_days:
		#copying standard preds and adding favours, but the pred cycle was decided to be a rest day
		best_plan = Plan(locked_in_rest_days, locked_in_days, season_data)
	else:
		best_plan = find_plans_single_favours(combos, items_by_name, season_data, pred_cycle,
			locked_in_days=locked_in_days, 
			locked_in_rest_days=locked_in_rest_days,
			favours=favours,
			only_favours=only_favours,
			threading=threading)

	out_name = save_task(week_num, pred_cycle, task_name, best_plan)

	print()
	best_plan.display(show_mats=True, show_copy_code=False, show_rest_days=pred_cycle==4, add_tildes=True, title=f"{task_name}, 6.5 week {week_num} day {pred_cycle}:", file_name=path.join(f"week_{week_num}", "display", f"c{pred_cycle}_{task_name}_display.txt"))

	return out_name

def run_tasks(week_num, pred_cycle):
	if not path.exists(f"week_{week_num}"): #create folder for the week
		print(f"Making folders for new week: {week_num}")
		for subfolder_name in ("display", "images", "saves"):
			makedirs(path.join(f"week_{week_num}", subfolder_name), exist_ok=True)
		with open(path.join(f"week_{week_num}", f"tasks.json"), "w") as f:
			f.write("{\n\t\"Standard\": {}\n}")

		print(f"Folders written, please put cycle snips (c11-c16) into 'week_{week_num}\\images' and then rerun!")
		return

	if path.exists(path.join(f"week_{week_num}", f"cycle{pred_cycle}.csv")): 
		print(f"cycle{pred_cycle}.csv already created, skipping...")
	else: #try to read in the cycle data as screenshots
		extract_cycle_from_snips(week_num, pred_cycle, debug=True, export_season_data=pred_cycle == 1)

	prev_cycle = pred_cycle - 1
	tasks = load_json(path.join(f"week_{week_num}", "tasks.json"))
	saves = listdir(path.join(f"week_{week_num}", "saves"))
	saves_dict = dict()
	for save_name in saves:
		name = path.splitext(save_name)[0]
		if name[0] == "#":
			continue
		cycle_str, task_name = name.split("_")
		cycle = int(cycle_str[-1])
		if task_name not in saves_dict:
			saves_dict[task_name] = dict()
		saves_dict[task_name][cycle] = save_name
	print("tasks:", list(tasks.keys()))

	items = load_items()
	combos = find_all_combos(items, allow_load=True, allow_save=True) #allow save/load since no blacklist
	items_by_name = {item.name: item for item in items}
	print(len(combos))

	for task_name, task_dict in tasks.items():
		if task_name in saves_dict.keys() and pred_cycle in saves_dict[task_name].keys():
			replace = None
			while replace not in ("y", "n", "s"):
				replace = input(f"{saves_dict[task_name][pred_cycle]} already exists, replace? (y/n/s(kip)) ").lower()
			if replace == "n":
				print("exiting... ")
				exit()
			elif replace == "s":
				print("skipping to next task... ")
				continue

		prev_data = None
		if task_name in saves_dict.keys() and prev_cycle in saves_dict[task_name]:
			prev_data = load_json(path.join(f"week_{week_num}", "saves", saves_dict[task_name][prev_cycle]))
			print(f"{task_name}: prev cycle save found ({saves_dict[task_name][prev_cycle]}), loading... ")

		using_standard_combos = False
		if prev_data is None:
			prev_data = task_dict
			print(f"{task_name}: no prev cycle save")

			if "Standard" in saves_dict.keys() and pred_cycle in saves_dict["Standard"]:
				standard_data = load_json(path.join(f"week_{week_num}", "saves", saves_dict["Standard"][pred_cycle]))
				print(f"{task_name}: current cycle Standard save found ({saves_dict['Standard'][pred_cycle]}), loading... ")
				if not any(constraint in task_dict.keys() for constraint in ["blacklist", "combos"]):
					load_standard = "y"#None
					while load_standard not in ("y", "n"):
						load_standard = input(f"use standard combos for new task {task_name}? only one rest day combo will be assessed (y/n) ").lower()
					if load_standard == "n":
						print("not loading standard... ")
					else:
						prev_data["combos"] = standard_data["full_combos"]
						prev_data["rest_days"] = standard_data["full_rest_days"]
						using_standard_combos = True
						print(f"loaded standard, only rest days {prev_data['rest_days']} will be assessed")

		locked_in_days = combos_from_text(prev_data["combos"], items_by_name) if "combos" in prev_data.keys() else []
		locked_in_rest_days = prev_data["rest_days"] if "rest_days" in prev_data.keys() else [1]
		blacklist = task_dict["blacklist"] if "blacklist" in task_dict.keys() else []
		favours = task_dict["favours"] if "favours" in task_dict.keys() else dict()
		favours = {fix_name(name, items_by_name): num for name, num in favours.items()}
		print(f"{task_name}: running task with {len(locked_in_days)} locked in cycles, {locked_in_rest_days} rest days, {len(blacklist)} blacklisted items, and {len(favours)} favours")

		out_name = run_cycle_prediction(combos, items_by_name, week_num=week_num, pred_cycle=pred_cycle, task_name=task_name, locked_in_days=locked_in_days, locked_in_rest_days=locked_in_rest_days, blacklist=blacklist, favours=favours, only_favours=using_standard_combos)
		if task_name == "Standard": #just made a standard pred, index it
			if "Standard" not in saves_dict.keys():
				saves_dict["Standard"] = dict()
			saves_dict["Standard"][pred_cycle] = out_name
		elif "blacklist" not in task_dict.keys() and "Standard" in saves_dict.keys() and pred_cycle in saves_dict["Standard"]:
			standard_data = load_json(path.join(f"week_{week_num}", "saves", saves_dict["Standard"][pred_cycle]))
			file_name = f"c{pred_cycle}_{task_name}.json"
			current_data = load_json(path.join(f"week_{week_num}", "saves", file_name))
			if standard_data["combos"] == current_data["combos"] and standard_data["rest_days"] == current_data["rest_days"]:
				#if we predicted the same stuff as standard and no blacklist, comment out our save so we can just go from standard next cycle
				print(f"commenting out duplicate pred {file_name} -> #{file_name}")
				rename(path.join(f"week_{week_num}", "saves", file_name), path.join(f"week_{week_num}", "saves", f"#{file_name}"))

		# input("\n\npress enter to continue...")

def simulate_day_by_day(week_num, start=1, end=4, locked_in_days=[], locked_in_rest_days=[1], favours=dict()):
	items = load_items()
	combos = find_all_combos(items, allow_load=True, allow_save=True) #allow save/load since no blacklist
	items_by_name = {item.name: item for item in items}
	print(len(combos))

	if start > 1: #try load task
		load_cycle = start - 1
		load_path = path.join(f"week_{week_num}", "saves", f"c{load_cycle}_Sim.json")
		print(f"start > 1, trying to load prev cycle preds... ", end="")
		if path.exists(load_path):
			print(f"found! loading {load_path}")
			prev_data = load_json(load_path)
			locked_in_days = combos_from_text(prev_data["combos"], items_by_name)
			locked_in_rest_days = prev_data["rest_days"]
		else:
			print(f"could not find a save at {load_path}")

	best_plans = []
	for cycle in range(start, end + 1): #cycle 1 (rest day) - cycle 4 (full info avail)
		season_data = read_season_data(week_num, restrict_cycles=list(range(cycle + 1, 8)), verbose=True, check_last_season=cycle == 1)

		best_plan = find_plans_single_favours(combos, items_by_name, season_data, cycle,
			locked_in_days=locked_in_days, 
			locked_in_rest_days=locked_in_rest_days,
			favours=favours) 
		best_plans.append(best_plan)
		#lock in prediction for the next cycle
		if cycle + 1 in best_plan.rest_days:
			print(f"locking in rest for day {cycle + 1}")
			locked_in_rest_days.append(cycle + 1)
		elif cycle < 4:
			locked_in_days.append(best_plan.season_combos[len(locked_in_days)])

	for i, best_plan in enumerate(best_plans, start=start):
		print(f"\n\nPlan, day {i}:")
		save_task(week_num, i, "Sim", best_plan)
		best_plan.display(file_name=path.join(f"week_{week_num}", "display", f"c{i}_Sim.txt"))

def test_actual_supply():
	instances = dict()
	season_paths = [(False, i) for i in range(1, 5)] + [(path.join("archive", "6.4"), i) for i in [1, 2, 3, 4, 5, 6, 7, 9, 10, 11, 12, 13, 14, 15, 16, 17, 19]]
	for path_prefix, week_num in season_paths:
		cycle_season_data = dict()
		print(path_prefix, week_num)
		for cycle in range(1, 5): #cycle 1 (rest day) - cycle 4 (full info avail)
			cycle_season_data[cycle] = read_season_data(week_num, restrict_cycles=list(range(cycle + 1, 8)), path_prefix=path_prefix, verbose=False)

		print(len(cycle_season_data[1].keys()))
		for item_name in cycle_season_data[1].keys():
			for c in range(1, 4):
				possible_patterns = cycle_season_data[c][item_name].possible_patterns
				if len(possible_patterns) == 1 and c != 1:
					continue #already known
				code = str(c) + " " + " ".join([pattern.name for pattern in possible_patterns])
				final_possible_patterns = cycle_season_data[4][item_name].possible_patterns
				assert len(final_possible_patterns) == 1
				if code not in instances.keys():
					instances[code] = dict()
				instances[code][final_possible_patterns[0].name] = instances[code].get(final_possible_patterns[0].name, 0) + 1


	supply_probs = dict()
	for instance_name, outcomes in sorted(instances.items()):
		#print(instance_name, outcomes)
		for outcome, occurrences in outcomes.items():
			if abs(124 - occurrences) < 3:
				outcomes[outcome] = 124
			elif abs(146 - occurrences) < 3:
				outcomes[outcome] = 146
			elif abs(22 - occurrences) < 3:
				outcomes[outcome] = 22

		results_sum = sum(outcomes.values())
		out_instance_name = " ".join(instance_name.split()[1:])
		supply_probs[out_instance_name] = []
		for outcome, occurrences in outcomes.items():
			supply_probs[out_instance_name].append((outcome, occurrences/results_sum))
		print(f"'{out_instance_name}': {supply_probs[out_instance_name]},")

def test_casuals(casuals_text, week_num, pred_cycle):
	items = load_items()
	season_data = read_season_data(week_num, verbose=True, check_last_season=pred_cycle == 1)
	display_season_data(season_data)
	items_by_name = {item.name: item for item in items}

	casuals_text = [line.strip() for line in casuals_text.lstrip().split("\n")]
	cycles = dict()
	cycle = None
	current_combo = []
	for line in casuals_text:
		if len(line) == 1: #cycle
			cycle = int(line)
			cycles[cycle] = []
		elif len(line) == 0: #next workshop
			num_workshops = 3 if len(cycles[cycle]) == 0 else 1
			combo = Combo([current_combo])
			cycles[cycle].append((combo, num_workshops))
			current_combo = []
		else: #item
			item_name = line.split(":")[2].split("(")[0].strip()
			item_name = fix_name(item_name, items_by_name)

			current_combo.append(items_by_name[item_name])

	dummy = Item("Dummy", 24, 0, [], [])
	dummy_combo = Combo([[dummy]])
	season_data["Dummy"] = ItemSeasonData("Dummy", "Low", "Low")
	season_data["Dummy"].set_cycle(1, "Sufficient", "None")
	season_data["Dummy"].determine_pattern()
	season_data["Dummy"].guess_supply(None)
	#print(cycles)
	rest_days = []
	season_combos = []
	for cycle in range(1, 8):
		if len(cycles.keys()) == 0: #all data read
			break
		elif cycle not in cycles.keys():
			rest_days.append(cycle)
		else:
			season_combos.append(cycles[cycle])
			del(cycles[cycle])
	for cycle_index in range(len(season_combos), 5):
		season_combos.append([(dummy_combo, 4)])
	if len(rest_days) < 2:
		rest_days = [1, 7]

	#print(season_combos, rest_days)
	plan = Plan(rest_days, season_combos, season_data)
	plan.display(file_name=path.join(f"week_{week_num}", "display", f"c{pred_cycle}_Casuals.txt"))

def test_value_verbose(week_num, save_name):
	items = load_items()
	season_data = read_season_data(week_num, verbose=True, check_last_season=False)
	items_by_name = {item.name: item for item in items}

	save_data = load_json(path.join(f"week_{week_num}", "saves", save_name))
	season_combos = combos_from_text(save_data["full_combos"], items_by_name)
	rest_days = save_data["rest_days"]
	plan = Plan(rest_days, season_combos, season_data)
	plan.display()

def main():
	# blacklist = [
	# 	#Rank 18
	# 	"Isleworks Fruit Punch",
	# 	"Isleworks Buffalo Bean Salad",
	# 	"Isleworks Peperoncino",
	#	"Isleworks Sweet Popoto Pie"
	# ]

	# test_add_favours()
	# test_actual_supply()
	# blacklist_ingredients = ["Corn", "Buffalo Beans", "Parsnip", "Paprika", "Pumpkin", "Popoto", "Sweet Popoto", "Cabbage", "Leek", "Broccoli", "Tomato", "Watermelon", "Wheat", "Zucchini", "Radish", "Eggplant", "Onion", "Beet", "Isleberry", "Runner Beans"]
	# predict_next_season(4, blacklist, blacklist_ingredients)

	# simulate_day_by_day(week_num=6, start=1, end=4)
	run_tasks(week_num=7, pred_cycle=2)
	# test_value_verbose(week_num=5, save_name="c4_OldStnd.json")

# 	test_casuals(casuals_text = 
# 	"""
# 	2
# :OC_Natron: Natron (4h)
# :OC_GardenScythe: Garden Scythe (6h)
# :OC_SilverEarCuffs: Silver Ear Cuffs (8h)
# :OC_GardenScythe: Garden Scythe (6h)

# :OC_Isloaf: Isloaf (4h)
# :OC_PopotoSalad: Popoto Salad (4h)
# :OC_Isloaf: Isloaf (4h)
# :OC_PopotoSalad: Popoto Salad (4h)
# :OC_Isloaf: Isloaf (4h)
# :OC_PopotoSalad: Popoto Salad (4h)

# 	3
# :OC_Sauerkraut: Sauerkraut (4h)
# :OC_CornFlakes: Corn Flakes (4h)
# :OC_Sauerkraut: Sauerkraut (4h)
# :OC_CornFlakes: Corn Flakes (4h)
# :OC_Sauerkraut: Sauerkraut (4h)
# :OC_CornFlakes: Corn Flakes (4h)

# :OC_Isloaf: Isloaf (4h)
# :OC_BuffaloBeanSalad: Buffalo Bean Salad (4h)
# :OC_HornCraft: Horn (6h)
# :OC_Butter: Butter (4h)
# :OC_HornCraft: Horn (6h)
# 	""", 
# 	week_num=7, pred_cycle=2)


if __name__ == "__main__":
	main()
