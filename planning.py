from workshop_items import *
import joblib, itertools
from os import path

class Plan:
	def __init__(self, rest_days, season_combos, season_data):
		self.rest_days = rest_days
		self.season_combos = season_combos
		self.earnings_per_cycle = []
		self.best_combos = []

		combo_index = 0
		groove = 0
		self.amounts_produced = dict()
		for cycle in range(1, 8):
			if cycle not in self.rest_days:
				combo_value, best_permutations, groove = cycle_value(season_combos[combo_index], season_data, cycle, groove, self.amounts_produced)
				self.earnings_per_cycle.append(combo_value)
				self.best_combos.append(best_permutations)
				combo_index += 1
		self.value = sum(self.earnings_per_cycle)

	def __repr__(self):
		return f"rest days: {self.rest_days}, value: {self.value}, amounts produced: {self.amounts_produced}"

	def __lt__(self, other):
		return other.value > self.value

	def display(self, show_mats=False, show_copy_code=False, title=None, file_name=None):
		f = None
		if file_name is None:
			out_fn = print
		else:
			f = open(file_name, "w")
			def out_fn(string="", end="\n"):
				print(string, end=end)
				f.write(string + end)

		if title is not None: out_fn(title)
		out_fn(f"Total value {self.value}, rest days {self.rest_days}")
		combo_index = 0
		for cycle in range(1, 8):
			if cycle not in self.rest_days:
				out_fn(f"C{cycle} ({self.earnings_per_cycle[combo_index]}): ", end="")
				for i, (combo, num_workshops) in enumerate(self.best_combos[combo_index]):
					if i != 0: out_fn(f"           ", end="")
					combo_text = str(combo).replace("Isleworks ", "")
					out_fn(f"{num_workshops}x {combo_text}")
				combo_index += 1

		if show_mats:
			out_fn(f"Amounts produced (excluding supply overcap): {self.amounts_produced}")
			materials_needed = dict()
			for cycle_combos in self.best_combos:
				for combo, num_workshops in cycle_combos:
					for item in combo:
						for ingredient, amount in item.ingredients:
							materials_needed[ingredient] = materials_needed.get(ingredient, 0) + amount*num_workshops
			out_fn("Materials needed:")
			out_fn(", ".join([f"{amount}x {ingredient}" for ingredient, amount in sorted(materials_needed.items(), key=lambda x: -x[1])]))

		if show_copy_code:
			out_fn(f"Copy code for locked in days:")
			for cycle_combos in self.best_combos:
				quoted_versions = [([f'{item.name}' for item in combo], num_workshops) for combo, num_workshops in cycle_combos]
				out_fn(f"{quoted_versions},")

		out_fn()
		if f is not None:
			f.close()

class Combo:
	def __init__(self, permutations):
		self.permutations = permutations
		self.id = combo_to_id(permutations[0])
		self.value()
		self.purity = 1/len(set(permutations[0]))

	def value(self, season_data=None, cycle=2, groove_guess=0, num_workshops=3, amounts_produced=None): #find value of permutation 0
		groove_by_hour = calculate_groove_times([(self.permutations[0], num_workshops)], groove_guess)
		self.last_value = combo_value(self.permutations[0], num_workshops, season_data, cycle, groove_by_hour, amounts_produced)
		return self.last_value

	def get_amounts_produced(self, num_workshops):
		amounts_produced = dict()
		for i, item in enumerate(self.permutations[0]):
			efficiency_bonus = get_efficiency_bonus(self.permutations[0], i)
			amounts_produced[item.name] = amounts_produced.get(item.name, 0) + efficiency_bonus*num_workshops
		return amounts_produced

	def __lt__(self, other):
		return other.last_value > self.last_value

	def __repr__(self):
		return f"Combo {self.permutations[0]}, {len(self.permutations)} permutations"

	def __len__(self):
		return len(self.permutations[0])

def get_efficiency_bonus(combo, index):
	if index == 0:
		return 1
	else:
		return 2 if combo[index].shares_category(combo[index-1]) else 1

def calculate_groove_times(combos, starting_groove):
	groove_by_hour = [starting_groove for i in range(25)]
			
	for combo, num_workshops in combos:
		hour = 0
		for i, item in enumerate(combo):
			efficiency_bonus = get_efficiency_bonus(combo, i)
			if efficiency_bonus == 2:
				for j in range(hour, len(groove_by_hour)):
					groove_by_hour[j] = min(MAX_GROOVE, groove_by_hour[j] + num_workshops)
			hour += item.time

	return groove_by_hour

def get_current_groove(groove_by_hour, combo, item_index):
	start_time = sum(item.time for item in combo[:item_index])
	return groove_by_hour[start_time]

def cycle_value(cycle_combos, season_data, cycle, starting_groove, amounts_produced=None, verbose=False):
	if amounts_produced is None:
		amounts_produced = dict()

	out_cycle_combos = []
	possiblities = []
	for combo_object, num_workshops in cycle_combos:
		if type(combo_object) is list:
			out_cycle_combos.append((combo_object, num_workshops)) 
		elif starting_groove == MAX_GROOVE or len(combo_object.permutations) == 1: # if groove is already maxed, order doesn't matter
			out_cycle_combos.append((combo_object.permutations[0], num_workshops)) 
		else:
			possiblities.append([(permutation, num_workshops) for permutation in combo_object.permutations])

	flat_possiblities = itertools.product(*possiblities) if len(possiblities) > 0 else []
	best_value = -1
	best_cycle_combos = out_cycle_combos
	for i, possibility in enumerate(flat_possiblities):
		possible_out_cycle_combos = out_cycle_combos[:]
		for permutation, num_workshops in possibility:
			possible_out_cycle_combos.append((permutation, num_workshops))

		groove_by_hour = calculate_groove_times(possible_out_cycle_combos, starting_groove)
		test_value = combo_value(possible_out_cycle_combos, 0, season_data, cycle, groove_by_hour, amounts_produced.copy())
		if test_value > best_value:
			best_value = test_value
			best_cycle_combos = possible_out_cycle_combos

	groove_by_hour = calculate_groove_times(best_cycle_combos, starting_groove)
	total_value = combo_value(best_cycle_combos, 0, season_data, cycle, groove_by_hour, amounts_produced) #send in the real amounts_produced this time to be edited

	return total_value, best_cycle_combos, groove_by_hour[-1]

def combo_value(combo, num_workshops, season_data, cycle, groove_by_hour, amounts_produced=None, verbose=False):
	if type(combo[0]) in (list, tuple): #got cycle_combos format
		cycle_combos = combo
		iterator = []
		for combo, num_workshops in cycle_combos:
			time = 0
			for i, item in enumerate(combo):
				iterator.append([time, get_efficiency_bonus(combo, i), num_workshops, item])
				time += item.time
		iterator.sort()
		for i in reversed(range(len(iterator)-1)):
			if iterator[i][3] == iterator[i+1][3] and iterator[i][0] == iterator[i+1][0] and iterator[i][1] == iterator[i+1][1]: #if item and time and eff bonus are equal, merge
				iterator[i][2] += iterator[i+1][2] #add num of workshops and discard the copy
				del(iterator[i+1])
	else:
		cycle_combos = None
		iterator = []
		current_time = 0
		for i, item in enumerate(combo):
			iterator.append((current_time, get_efficiency_bonus(combo, i), num_workshops, item))
			current_time += item.time

	if amounts_produced is None:
		amounts_produced = dict()

	# verbose = False
	combo_value = 0
	for time, efficiency_bonus, num_workshops, item in iterator:
		demand = season_data[item.name].popularity_mult if season_data is not None else 1
		groove = groove_by_hour[time + item.time-1]

		value_before = combo_value
		if season_data is None:
			combo_value += item.calc_value(exact_supply_to_bonus(0), demand, groove)*num_workshops*efficiency_bonus
		else:
			supply_guesses = season_data[item.name].supply_guesses[cycle-1]
			add_amount = amounts_produced.get(item.name, 0)
			for exact_supply, prob in supply_guesses:
				combo_value += item.calc_value(exact_supply_to_bonus(exact_supply + add_amount), demand, groove)*num_workshops*efficiency_bonus * prob


		amounts_produced[item.name] = amounts_produced.get(item.name, 0) + num_workshops*efficiency_bonus
		if verbose:
			short_name = item.name.replace("Isleworks ", "")
			print(f"C{cycle} {time}h {exact_supply}ES int(int(1.{groove}G*{item.value}V*1.4W) * {exact_supply_to_bonus(exact_supply)}S*{demand}D)*{efficiency_bonus}E*{short_name} x {num_workshops} = {combo_value-value_before}   after amt={amounts_produced.get(item.name, 0)}")
	if verbose: print()
	return int(combo_value)

def combo_to_id(combo):
	string_id = "_".join(["".join(item.name.split()[1:]) for item in [combo[0]] + sorted(combo[1:])])
	return string_id

def find_combo(items, items_by_category, starting_item, remaining_time, start_efficient):
	if remaining_time < 4:
		return [[starting_item]]

	combos = []
	next_candidates = set()
	if start_efficient and remaining_time == 12: #this item was comboed, so can do uncomboed next item
		next_candidates = set(items)
	else:
		for category in starting_item.categories:
			next_candidates.update(items_by_category[category])
			# for item in items_by_category[category]:
			# 	next_candidates.add(item)

	for next_item in next_candidates:
		if next_item == starting_item:
			continue

		next_efficient = next_item.shares_category(starting_item)
		combo_remaining_time = remaining_time - next_item.time
		if combo_remaining_time == 0 or combo_remaining_time >= 4:
			if start_efficient or remaining_time > 8 or next_item.time == 8: #if inefficient next, must have long enough to also combo off it before end
				if next_efficient or next_item.time == 4:
					combos += find_combo(items, items_by_category, next_item, combo_remaining_time, next_efficient)

	return [[starting_item] + combo for combo in combos]

def find_all_combos(items, remaining_time=24, verbose=False, allow_load=True, allow_save=False):
	items_by_category = find_items_by_category(items)
	if items[0].connections == 0: # connections have not been initialized
		for category, category_items in items_by_category.items():
			for item in category_items:
				item.connections += sum([other.value/other.time for other in category_items if other != item])
	if verbose:
		for item in items:
			print(item.name, item.connections)

	combo_path = path.join("resources", "combos.pth")
	if path.exists(combo_path) and allow_load:
		print("loading combos.. ", end="")
		combos = joblib.load(combo_path)
		print("done")
		return combos

	combos = []
	for item in items:
		combos += find_combo(items, items_by_category, item, remaining_time - item.time, False)

	combos_by_id = dict()
	for combo in combos:
		combo_id = combo_to_id(combo)
		if combo_id not in combos_by_id.keys():
			combos_by_id[combo_id] = []
		combos_by_id[combo_id].append(combo)

	combos = [Combo(permutations) for combo_id, permutations in combos_by_id.items()]
	# combos = [combo for combo in combos if combo.last_value > 1800]

	if allow_save:
		joblib.dump(combos, combo_path)

	return combos

if __name__ == "__main__":
	items = load_items()
	combos = sorted(find_all_combos(items, allow_load=True))
	print(len(combos))
	for combo in combos:
		if combo.permutations[0][0].name == "Isleworks Fruit Punch" and combo.permutations[0][-1].name == "Isleberry Jam":
			print(combo, len(combo.permutations))
			# for permutation in combo.permutations:
			# 	print(permutation)
			# print()
		# if len(combo.permutations[0]) == 4 and combo.permutations[0][1].name == "Isleworks Garnet Rapier" and combo.permutations[0][3].name == "Isleworks Garnet Rapier":
		# 	print(combo, len(combo.permutations))
		# 	for permutation in combo.permutations:
		# 		print(permutation)
		# 	print()

	exit()
	for combo in combos[:5] + combos[-5:]:
		print(combo)

	i = 0
	while combos[i].last_value < 1600:
		i += 1

	print(i, len(combos), i/len(combos))
	values = [combo.last_value for combo in combos]

	import matplotlib.pyplot as plt
	_ = plt.hist(values, bins='auto')  # arguments are passed to np.histogram
	plt.title("Histogram with 'auto' bins")
	plt.show()