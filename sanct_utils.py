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

def remove_one_combo(cycle_combos, i):
	if cycle_combos[i][1] == 1: #will be none left
		del(cycle_combos[i])
	else:
		cycle_combos[i] = (cycle_combos[i][0], cycle_combos[i][1] - 1) #decrease its num workshops by 1

def remove_combos(cycle_combos, indices, sorted=False):
	"""sorted: indices sorted in ascending order?"""
	if not sorted: indices = sorted(indices)
	for i in reversed(indices):
		remove_one_combo(cycle_combos, i)

def get_possible_indices(cycle_combos):
	"""get possible indices for a set of cycle combos, eg for 3,1 it'll return [0, 0, 0, 1]"""
	possible_indices = []
	for i, (combo, num_workshops) in enumerate(cycle_combos):
		possible_indices += [i]*num_workshops
	return possible_indices

def get_amt_favours_produced(combo, favours, capped, num_workshops=1):
	"""
	capped: whether to only return produced amts if not exceeding the amt needed
	"""
	incentive = dict()
	if type(combo) is Combo:
		combo = combo.permutations[0]

	combo_amts_produced = dict()
	for i, item in enumerate(combo):
		efficiency_bonus = get_efficiency_bonus(combo, i)
		combo_amts_produced[item.name] = combo_amts_produced.get(item.name, 0) + efficiency_bonus*num_workshops

	for name in favours.keys():
		amt_made = combo_amts_produced.get(name, 0)
		if capped and favours[name] > 0 and amt_made > 0:
			incentive[name] = min(amt_made, favours[name])
		else:
			incentive[name] = amt_made

	return incentive

def display_season_data(season_data):
	by_code = dict()
	for item_season_data in season_data.values():
		if item_season_data.code not in by_code.keys():
			by_code[item_season_data.code] = dict()
		by_code[item_season_data.code][item_season_data.popularity] = by_code[item_season_data.code].get(item_season_data.popularity, []) + [item_season_data]

	print(f"Season data:")
	for code in sorted(by_code.keys()):
		print(f"{code} (mults {[round(x, 2) for x in by_code[code][list(by_code[code].keys())[0]][0].supply_mult_guesses]}):")
		for popularity in by_code[code].keys():
			print(f"  {POPULARITY_BONUSES[popularity]:.1f}x pop: {[item_season_data.name.replace('Isleworks ', '') for item_season_data in by_code[code][popularity]]}")

def fix_name(name, items_by_name):
	name_title = name.strip().title()
	if name_title in items_by_name.keys():
		return name_title
	elif "Isleworks " + name_title in items_by_name.keys():
		return "Isleworks " + name_title
	elif "Island " + name_title in items_by_name.keys():
		return "Island " + name_title
	elif "Isleberry " + name_title in items_by_name.keys():
		return "Isleberry " + name_title
	elif name_title == "Mammet Of The Cycle Award":
		return "Mammet of the Cycle Award"
	else:
		raise ValueError(f"unknown craft name {name}")