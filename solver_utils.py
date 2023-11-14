from workshop_items import *
from planning import *
import json

def ceil(n):
	return int(n+0.99999)

def get_valid_rest_day_combos(locked_in_days, locked_in_rest_days):
	# assume locked rest days have already passed by
	if len(locked_in_rest_days) == 0:
		rest_day_combos = sorted({tuple(sorted((i, j))) for i in range(len(locked_in_days) + 1, 8) for j in range(len(locked_in_days) + 1, 8) if i != j})
	elif len(locked_in_rest_days) == 1:
		i = locked_in_rest_days[0]
		rest_day_combos = sorted({tuple(sorted((i, j))) for j in range(len(locked_in_days) + 2, 8) if i != j})
	else:
		rest_day_combos = [locked_in_rest_days]
	return rest_day_combos

def guess_groove_value(starting_groove, groove, cycle_index):
	remaining_cycles = 4 - cycle_index
	groove_crafts_per_day = 3 #(guessing at 4 crafts per day)
	craft_grooveless_value = 1500*NUM_WORKSHOPS/4 #1500 per workshop, split over 4 items

	final_values = [0, 0]
	for i, new_groove in enumerate((starting_groove, groove)):
		for cycle in range(remaining_cycles):
			final_values[i] += craft_grooveless_value*(1 + 0.01*new_groove) #the first, not efficient item
			for craft in range(groove_crafts_per_day):
				new_groove = min(MAX_GROOVE, new_groove + NUM_WORKSHOPS)
				craft_value = craft_grooveless_value*(1 + 0.01*new_groove)
				final_values[i] += craft_value

	return final_values[1] - final_values[0]

def guess_groove_value_fast(starting_groove, groove, cycle_index):
	groove_diff = groove - starting_groove
	remaining_cycles = 4 - cycle_index
	cycles_to_cap = (MAX_GROOVE - starting_groove+4)//12 #the +4 just minimizes max and mean diff, somehow. by observation only

	return 50*min(remaining_cycles, cycles_to_cap)*groove_diff

def guess_groove_value_fastest(starting_groove, groove, cycle_index): #same as above but as one liner
	return 50*min((4 - cycle_index), (MAX_GROOVE - starting_groove+4)//12)*(groove - starting_groove)

if __name__ == "__main__":
	max_diff = 0
	mean_diff = 0
	i = 0
	for starting_groove in range(0, 46):
		for groove in range(starting_groove+1, starting_groove+5):
			for cycle_index in range(5):
				proper = guess_groove_value(starting_groove, groove, cycle_index) 
				fast = guess_groove_value_fastest(starting_groove, groove, cycle_index) 
				diff = abs(fast-proper)
				mean_diff = (mean_diff*i + diff)/(i+1)
				if diff > max_diff:
					print(f"start groove {starting_groove} -> {groove} c{cycle_index} proper {proper} fast {fast} diff {diff}")
					max_diff = diff
				i += 1


	print(f"mean diff {mean_diff}")
	print(guess_groove_value(20, 23, 1))
	print(guess_groove_value_fast(20, 23, 1))

# with open("groove_test.csv", "w") as f:
# 	for x in range(46):
# 		for y in range(x, 46):
# 			for cycle in range(4):
# 				val = guess_groove_value(x, y, cycle)
# 				f.write(f"{x},{y},{cycle},{val}\n")

def combos_to_text_list(all_combos):
	text_list = []
	for cycle_combos in all_combos:
		text_cycle_combos = []
		for combo, num_workshops in cycle_combos:
			text_cycle_combos.append(([item.name for item in combo], num_workshops))
		text_list.append(text_cycle_combos)

	return text_list

def combos_from_text(text_list, items_by_name):
	for cycle_combos in text_list:
		for i, (text_combo, num_workshops) in enumerate(cycle_combos):
			cycle_combos[i] = (combo_from_text(text_combo, items_by_name), num_workshops)

	return text_list

def combo_from_text(text, items_by_name):
	# item_text = [word.strip() for word in text.strip().split(",")]
	items = [items_by_name[item_name] for item_name in text]
	combo = Combo(permutations=[items])
	return combo

def load_json(name):
	with open(name) as f:
		json_data = json.load(f)

	return json_data

def write_json(name, data):
	with open(name, "w") as f:
		json.dump(data, f, indent=4)


#===== Archive =====


def simulate_day_by_day(combos, week_num, start=1, end=4, locked_in_days=[], locked_in_rest_days=[1], favours=[], forced_peaks=None, threading=True):
	best_plans = []
	for cycle in range(start, end + 1): #cycle 1 (rest day) - cycle 4 (full info avail)
		season_data = read_season_data(week_num, restrict_cycles=list(range(cycle + 1, 8)), verbose=True)

		# for item_name, item_season_data in sorted(season_data.items()):
		# 	print(item_name, item_season_data)
			
		best_plan = find_plans(combos, season_data,
			locked_in_days=locked_in_days, 
			locked_in_rest_days=locked_in_rest_days,
			forced_peaks=forced_peaks,
			threading=threading) 
		best_plans.append(best_plan)
		#lock in prediction for the next cycle
		if cycle + 1 in best_plan.rest_days:
			print(f"locking in rest for day {cycle + 1}")
			locked_in_rest_days.append(cycle + 1)
		elif cycle < 4:
			locked_in_days.append(best_plan.season_combos[len(locked_in_days)])

	joblib.dump(best_plans, path.join(f"week_{week_num}", f"sim_days_{start}-{end}.pth"))
	for i, best_plan in enumerate(best_plans, start=start):
		print()
		print(f"Plan, day {i}:")
		best_plan.display(show_mats=True, show_copy_code=True)

# def collapse_indices(cycle_combos, indices):
# 	"""collapse indices down to match cycle combos (eg. (0, 2, 3) -> (0, 0, 1) for a 3, 1 workshop combo)"""
# 	indices = list(indices)
# 	current_sum = 0
# 	for set_index, (_, num_workshops) in enumerate(cycle_combos):
# 		current_sum += num_workshops
# 		for index, combo_index in enumerate(indices):
# 			if combo_index < set_index: #already locked in
# 				continue
# 			elif combo_index < current_sum:
# 				indices[index] = set_index

# 	return indices



def _find_best_crafts_iter(items_by_name, combos, season_data, locked_in_days, rest_days, craft_cycles, verbose=False):
	NUM_COMBOS_TO_CHECK_COARSE = 360000
	#start low then increase?
	NUM_COMBOS_TO_CHECK = 32000

	current_best_combos = locked_in_days[:]
	stove = items_by_name["Isleworks Stove"]
	stove_combo = Combo([[stove, stove, stove, stove]])
	for i in range(len(locked_in_days), 5):
		current_best_combos.append([(stove_combo, 4)]) #add a low value placeholder combo

	current_plan = Plan(rest_days, current_best_combos, season_data)
	combos_by_cycle = dict()
	last_iter_value = 0
	remaining_default_cycles = 5 - len(locked_in_days)
	while current_plan.value > last_iter_value:
		last_iter_value = current_plan.value

		cycle_starting_grooves = {0: 0}
		cycle_starting_amounts_produced = {0: dict()}
		for cycle_index, cycle in enumerate(craft_cycles):
			amounts_produced_instance = cycle_starting_amounts_produced[cycle_index].copy()
			groove = cycle_starting_grooves[cycle_index]

			total_value, cycle_combos, groove = cycle_value(current_best_combos[cycle_index], season_data, cycle, groove, amounts_produced_instance)
			cycle_starting_grooves[cycle_index + 1] = groove
			cycle_starting_amounts_produced[cycle_index + 1] = amounts_produced_instance

		best_replacements = [] #(value, combo, combo_rank, cycle_index, replace_indices)
		for cycle_index, cycle in enumerate(craft_cycles):
			if cycle_index < len(locked_in_days):
				continue

			cycle_best_replacements = []

			#can skip this if we're just considering all anyway
			start_time = time()
			ranked_combos = combos_by_cycle.get(cycle, combos)[:]
			for combo in ranked_combos:
				starting_groove = cycle_starting_grooves[cycle_index]
				value = combo.value(season_data, cycle, starting_groove, amounts_produced=cycle_starting_amounts_produced[cycle_index])
				groove_value = 0
				if starting_groove < MAX_GROOVE:
					groove_value = guess_groove_value(starting_groove, starting_groove + len(combo.permutations[0]) - 1, cycle_index) #assuming unbroken combo = len-1 groove gain 

					#try without groove add/debug check groove add?
				combo.last_value = value + groove_value

			ranked_combos = sorted(ranked_combos, key=lambda combo: combo.last_value)
			if cycle not in combos_by_cycle.keys():
				combos_by_cycle[cycle] = ranked_combos[-NUM_COMBOS_TO_CHECK_COARSE:]
			ranked_combos = ranked_combos[-NUM_COMBOS_TO_CHECK:]
			if verbose: print(f"c{cycle} combo time: {time() - start_time:.2f}s\t", end="")

			#create list of jobs and then parellelize? oonly single best needs to be saved, or best from each chunk
			start_time = time()
			if remaining_default_cycles > 0:
				nums_to_replace = [4] #while theres still whole default cycles, go for full replacement of all workshops
			else:
				nums_to_replace = range(1, 5) #replace 1-4 workshops

			iterator = []
			for num_workshops_replace in nums_to_replace:
				all_replace_indices = set(itertools.combinations(get_possible_indices(current_best_combos[cycle_index]), num_workshops_replace))
				iterator += [(num_workshops_replace, replace_indices) for replace_indices in all_replace_indices]

			for combo_rank, combo in enumerate(ranked_combos):
				for num_workshops_replace, replace_indices in iterator:
					test_cycle = current_best_combos[:]
					test_cycle[cycle_index] = current_best_combos[cycle_index][:]
					remove_combos(test_cycle[cycle_index], replace_indices, sorted=True)
					test_cycle[cycle_index].append((combo, num_workshops_replace)) #add our new combo

					edited_plan = Plan(rest_days, test_cycle, season_data)
					net_value = edited_plan.value - current_plan.value

					cycle_best_replacements.append((net_value, combo, combo_rank, cycle_index, replace_indices))

			if verbose: print(f"replacements time: {time() - start_time:.2f}s")
			cycle_best_replacements.sort(key=lambda item: item[0])

			best_replacements += cycle_best_replacements[-1:]

		best_replacements.sort(key=lambda item: item[0])
		total_value, combo, cycle_index, replace_indices = best_replacements[-1]
		remaining_default_cycles -= 1

		if total_value > 0:
			remove_combos(current_best_combos[cycle_index], replace_indices, sorted=True)
			current_best_combos[cycle_index].append((combo, len(replace_indices)))
			current_plan = Plan(rest_days, current_best_combos, season_data)

			if verbose: 
				print(f"score {total_value} cycle {craft_cycles[cycle_index]}")
				current_plan.display()
		else:
			print("No improvement, exiting... ")

	final_plan = Plan(rest_days, current_best_combos, season_data)

	return final_plan



def add_favours(favours, favour_combos, season_data, pred_cycle, craft_cycles, plan, pool=None, verbose=False):
	NUM_COMBOS_TO_CHECK = 8192
	favour_incentive = 128 #increase as needed

	COMBO_CHUNK_SIZE = 1024
	REPLACEMENTS_CHUNK_SIZE = 256

	current_best_combos = plan.best_combos[:]
	remaining_favours = favours.copy()

	while any(value > 0 for favour_name, value in remaining_favours.items()):
		cycle_starting_grooves = {0: 0}
		cycle_starting_amounts_produced = {0: dict()}
		for cycle_index, cycle in enumerate(craft_cycles):
			amounts_produced_instance = cycle_starting_amounts_produced[cycle_index].copy()
			groove = cycle_starting_grooves[cycle_index]

			total_value, cycle_combos, groove = cycle_value(current_best_combos[cycle_index], season_data, cycle, groove, amounts_produced_instance)
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
		cycle_valued_comboes = dict()
		combo_chunks = []
		for cycle_index, cycle in enumerate(craft_cycles):
			if cycle <= pred_cycle:
				continue

			for name in favours.keys():
				if remaining_favours[name] > 0:
					combo_chunks += [(cycle_index, cycle, favour_combos[name][i*COMBO_CHUNK_SIZE:(i+1)*COMBO_CHUNK_SIZE]) for i in range(ceil(len(favour_combos[name])/COMBO_CHUNK_SIZE))]

			# ranked_favour_combos = []
			# for name in favours.keys():
			# 	if remaining_favours[name] > 0:
			# 		for combo in favour_combos[name]:
			# 			score = combo.value(season_data, cycle, cycle_starting_grooves[cycle_index], amounts_produced=cycle_starting_amounts_produced[cycle_index])
			# 			incentive = get_amt_favours_produced(combo, favours, capped=True)
			# 			incentive_sum = sum(incentive.values())*favour_incentive
			# 			#combo.last_value += incentive_sum
			# 			ranked_favour_combos.append((score + incentive_sum, combo))
			# cycle_valued_comboes[cycle_index] = ranked_favour_combos

		if pool is None:
			processed_chunks = [add_favours_combo_value_chunk(param_chunk, cycle, cycle_index, favours, favour_incentive, cycle_starting_grooves, cycle_starting_amounts_produced, season_data) for (cycle_index, cycle, param_chunk) in combo_chunks]
		else:
			arg_sets = [(param_chunk, cycle, cycle_index, favours, favour_incentive, cycle_starting_grooves, cycle_starting_amounts_produced, season_data) for (cycle_index, cycle, param_chunk) in combo_chunks]
			processed_chunks = pool.starmap(add_favours_combo_value_chunk, arg_sets)

		for cycle_index, valued_comboes in processed_chunks:
			cycle_valued_comboes[cycle_index] = cycle_valued_comboes.get(cycle_index, []) + valued_comboes

		all_params = []
		for cycle_index in cycle_valued_comboes.keys():
			cycle_valued_comboes[cycle_index].sort(key=lambda x: x[0])
			cycle_valued_comboes[cycle_index] = cycle_valued_comboes[cycle_index][-NUM_COMBOS_TO_CHECK:]
			for combo_rank, (coarse_score, combo) in enumerate(reversed(cycle_valued_comboes[cycle_index])):
				all_params += [(cycle_index, i, combo, combo_rank) for i in range(len(current_best_combos[cycle_index]))]

		if pool is None:
			best_replacement = add_favours_replacements_chunk(all_params, current_best_combos, favours, favour_incentive, remaining_favours, season_data, plan)
		else:
			arg_sets = [(all_params[i*REPLACEMENTS_CHUNK_SIZE:(i+1)*REPLACEMENTS_CHUNK_SIZE], current_best_combos, favours, favour_incentive, remaining_favours, season_data, plan) for i in range(ceil(len(all_params)/REPLACEMENTS_CHUNK_SIZE))]
			best_replacement = sorted(pool.starmap(add_favours_replacements_chunk, arg_sets), key=lambda x: x[0])[-1]

			# ranked_favour_combos = sorted(ranked_favour_combos, key=lambda favour_combo: favour_combo.last_value)
			# ranked_favour_combos = ranked_favour_combos[-NUM_COMBOS_TO_CHECK:]

			# for combo_rank, combo in enumerate(reversed(ranked_favour_combos)):
			# 	test_cycle = current_best_combos[:]
			# 	for i, (cycle_combos, num_workshops) in enumerate(current_best_combos[cycle_index]):
			# 		test_cycle[cycle_index] = current_best_combos[cycle_index][:]
			# 		removed_favours = get_amt_favours_produced(test_cycle[cycle_index][i][0], favours, capped=False)
			# 		remove_one_combo(test_cycle[cycle_index], i)
			# 		test_cycle[cycle_index].append((combo, 1)) #add our new combo x1

			# 		edited_plan = Plan(plan.rest_days, test_cycle, season_data)
			# 		net_value = edited_plan.value - plan.value
			# 		added_favours = get_amt_favours_produced(combo, favours, capped=False)
			# 		net_favours = {name: added_favours[name] - removed_favours[name] for name in favours.keys() if added_favours[name] - removed_favours[name] != 0}
			# 		net_favours_capped = dict()
			# 		for name in net_favours.keys():
			# 			if remaining_favours[name] >= 0: #we dont want to lose any - cant exceed cap but can go negative
			# 				net_favours_capped[name] = min(remaining_favours[name], net_favours[name])
			# 			elif net_favours[name] - remaining_favours[name] < 0: #if we had a surplus but removed so much to need more again
			# 				net_favours_capped[name] = net_favours[name] - remaining_favours[name]
			# 			else:
			# 				net_favours_capped[name] = 0

			# 			if remaining_favours[name] != 1 and remaining_favours[name] - net_favours[name] == 1: #we reduced it to only 1 left, bad
			# 				net_favours_capped[name] -= 1 #apply a penalty of 1

			# 		incentive_sum = sum(net_favours_capped.values()) * favour_incentive

			# 		value = net_value + incentive_sum
			# 		if value > best_replacement[0]:
			# 			best_replacement = (value, net_value, incentive_sum, net_favours, combo, combo_rank, cycle_index, i)

		total_value, net_value, incentive_sum, net_favours, combo, combo_rank, cycle_index, replace_index = best_replacement
		if incentive_sum == 0 or sum(net_favours.values()) < 0: #no progress was made towards remaining favours - either replaced by same, or replaced with something that produced less favour items
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