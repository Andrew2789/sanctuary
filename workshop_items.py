from os import listdir, path, rename
from random import shuffle
from datetime import datetime
import pytz
NUM_WORKSHOPS = 4
MAX_GROOVE = 45

class Item:
	"""
	Represents a workshop item
	"""
	workshop_mult = {i+1: 1 + 0.1*i for i in range(5)}

	def __init__(self, name, time, value, categories, ingredients):
		self.name = name
		self.time = time
		self.value = value
		self.categories = categories
		self.ingredients = ingredients
		self.connections = 0

	def __eq__(self, other):
		return self.name == other.name

	def __lt__(self, other):
		return self.name < other.name

	def __hash__(self):
		return hash(self.name)

	def __repr__(self):
		return self.name

	def display(self):
		"""
		Returns
		----------
		string
			A descriptive string representation of this item
		"""
		return (f"{self.name}: {self.time}h, {self.value} value, categories: {self.categories}, ingredients: {self.ingredients}")

	def calc_value(self, supply=1.0, demand=1.0, groove=0, workshop_level=5):
		"""
		Calculate the value of this item with a known set of multipliers

		Parameters
		----------
		supply : float, default 1.0
			The supply multiplier (eg. Nonexistent supply = 1.6 multiplier)
		demand : float, default 1.0
			The demand/popularity multiplier (eg. Very High = 1.4 multiplier)
		groove : int, default 0
			The amount of groove accrued before crafted
		workshop_level : int, default 5
			The level of the workshop crafting the item

		Returns
		----------
		int
			The amount of seafarer's cowries earnt by crafting this item once

		"""
		return int(int(self.value*self.workshop_mult[workshop_level]*(1 + 0.01*groove))*supply*demand)

	def shares_category(self, other):
		return any(category in other.categories for category in self.categories)

class ItemSeasonData:
	"""
	Represents the multipliers for one workshop item over a season
	"""
	def __init__(self, name, popularity, predicted_demand, last_season_pattern=False): 
		self.name = name
		self.supply = [None]*SEASON_LENGTH
		self.demand_shift = [None]*SEASON_LENGTH
		self.popularity = POPULARITY_VALUES.index(popularity)
		self.popularity_mult = POPULARITY_BONUSES[self.popularity]
		self.predicted_demand = POPULARITY_VALUES.index(predicted_demand)

		self.supply_mult_guesses = [None]*SEASON_LENGTH
		self.supply_guesses = [None]*SEASON_LENGTH
		self.possible_patterns = list(PATTERNS.values())
		self.last_season_pattern = last_season_pattern
		self.code = "Not loaded"

	def set_cycle(self, cycle_num: int, supply: str, demand_shift: str):
		"""
		Load supply and demand shift data from a cycle

		Parameters
		----------
		cycle_num : int
			The number of the cycle that is being loaded. Valid range: 1 - 7, inclusive
		supply: str
			The supply value for this cycle, as a string (eg. "Sufficient")
		demand_shift: str
			The demand shift value for this cycle, as a string (eg. "Increasing")
		"""
		self.supply[cycle_num - 1] = SUPPLY_VALUES.index(supply)
		self.demand_shift[cycle_num - 1] = DEMAND_SHIFT_VALUES.index(demand_shift)

	def determine_pattern(self):
		"""
		Narrow down the possible supply patterns for this item as much as possible. 
		Possible patterns are stored in the ItemSeasonData.possible_patterns list
		"""
		if self.supply[0] is None: #no cycle data is loaded, any pattern is possible
			return
		elif self.supply[1] is None: #only cycle 1 data is loaded (shift is unreliable), so patterns are handled differently
			if self.supply[0] == 2: #sufficient supply, could be any pattern apart from C2 peaks
				self.possible_patterns = [pattern for pattern in self.possible_patterns if "2" not in pattern.name]
			else: #insufficient supply, C2W or C2S pattern

				if self.last_season_pattern: #last season patterns are loaded, try to use these:
					last_peak = int(self.last_season_pattern.name[1])
					last_strength = self.last_season_pattern.name[2]
					if last_peak < 7 and last_strength == "S": #c2-6 strong peak
						if self.demand_shift[0] == PATTERNS["C2S"].demand_shift[0]:
							self.possible_patterns = [PATTERNS["C2S"]]
						elif self.demand_shift[0] == PATTERNS["C2W"].demand_shift[0]:
							self.possible_patterns = [PATTERNS["C2W"]]
						else: #unknown, must have produced some of this item last season
							self.possible_patterns = [PATTERNS["C2W"], PATTERNS["C2S"]]
					else: #unknown peak
						self.possible_patterns = [PATTERNS["C2W"], PATTERNS["C2S"]]

				else: #last season patterns weren't loaded
					if self.demand_shift[0] == PATTERNS["C2S"].demand_shift[0]:
						self.possible_patterns = [PATTERNS["C2S"]]
					elif self.demand_shift[0] == PATTERNS["C2W"].demand_shift[0]:
						self.possible_patterns = [PATTERNS["C2W"]]
					else: #demand shift could not match either pattern since cycle 1 demand shift is unreliable. leave both possibilities in in this case
						self.possible_patterns = [PATTERNS["C2W"], PATTERNS["C2S"]]
		else:
			self.demand_shift[0] = None #delete cycle 1 shift data - it is unreliable and should only be used when just cycle 1 is available
			self.supply = [None if supply is None else min(supply, 2) for supply in self.supply] #if supply is surplus or overflowing, reduce it to sufficient for pattern

			cycle_index = 0
			while len(self.possible_patterns) > 1 and cycle_index < SEASON_LENGTH:
				for pattern_index in reversed(range(len(self.possible_patterns))):
					pattern = self.possible_patterns[pattern_index]
					if  (self.supply[cycle_index] is not None and pattern.supply[cycle_index] != self.supply[cycle_index]) or \
						(self.demand_shift[cycle_index] is not None and pattern.demand_shift[cycle_index] != self.demand_shift[cycle_index]):
						# print(f"removing {self.possible_patterns[pattern_index]}")
						del(self.possible_patterns[pattern_index])
				cycle_index += 1

	def consolidate_supply_guesses(self):
		"""Combine supply guesses into a format where same exact supply on each cycle have their probs combined into one"""
		consolidated_supply_guesses = [dict() for c in range(7)]
		cycle_mults = CODE_CYCLE_MULTS.get(self.code, [1.0] * 7)

		for c in range(7):
			for pattern, prob in self.supply_guesses:
				consolidated_supply_guesses[c][pattern.exact_supply[c]] = consolidated_supply_guesses[c].get(pattern.exact_supply[c], 0) + prob*cycle_mults[c]

		consolidated_supply_guesses = [[(exact_supply, prob) for exact_supply, prob in cycle_dict.items()] for cycle_dict in consolidated_supply_guesses]
		
		self.supply_guesses = consolidated_supply_guesses
		self.supply_mult_guesses = [self.supply_mult_guesses[c]*cycle_mults[c] for c in range(7)]

	def guess_supply(self, all_possible_patterns, hours_after_reset=None):
		"""
		Guess supply multipliers and tiers for each cycle based on the possible patterns this item could follow
		"""
		fixed = False
		self.code = " ".join([pattern.name for pattern in self.possible_patterns])
		if len(self.possible_patterns) != 1 and self.code not in OBSERVED_PATTERN_PROBS.keys():
			print(f"===== unknown key '{self.code}' for item {self.name} (supp {self.supply} dem_sh {self.demand_shift}) =====\nattempting to fix... ")
			#this should only be able to happen on c2-4 preds (on c1, nothing has been produced yet. surely it cant stuff up this bad)
			dummy = ItemSeasonData(self.name, POPULARITY_VALUES[self.popularity], POPULARITY_VALUES[self.predicted_demand])
			pred_cycle = 0
			for i in range(SEASON_LENGTH):
				if self.supply[i] is not None:
					pred_cycle += 1
				else:
					break
			if 2 <= pred_cycle <= 4 and hours_after_reset is not None:
				#add all but most recent cycle data to dummy
				dummy.supply = self.supply[:pred_cycle-1] + [None]*(SEASON_LENGTH - (pred_cycle-1))
				dummy.demand_shift = self.demand_shift[:pred_cycle-1] + [None]*(SEASON_LENGTH - (pred_cycle-1))
				dummy.determine_pattern()
				viable_patterns = dummy.possible_patterns
				if hours_after_reset < 4: #nothing had been crafted this cycle when data was taken, demand_shift should be accurate. This should only apply for c3-4 preds (if c2 is measured <4h from reset, nothing has been produced at all)
					for i in reversed(range(len(viable_patterns))):
						if viable_patterns[i].demand_shift[pred_cycle-1] != self.demand_shift[pred_cycle-1]:
							del(viable_patterns[i])
					if len(viable_patterns) == 0:
						print(f"ran out of viable pattens when trying to fix by matching demand shift (hours after reset <4). exiting... ")
						exit()
					new_code = " ".join([pattern.name for pattern in viable_patterns])
					if len(viable_patterns) != 1 and new_code not in OBSERVED_PATTERN_PROBS.keys():
						print(f"tried to fix code to {new_code}, but it's not in the observed patterns :( (hours after reset <4). exiting... ")
						exit()

					old_supply = SUPPLY_VALUES[self.supply[pred_cycle-1]]
					new_supply = SUPPLY_VALUES[viable_patterns[0].supply[pred_cycle-1]] #should be the same for every viable pattern if hours after reset <4
					print(f"fixing code for item {self.name} '{self.code}' -> {new_code} (c{pred_cycle} supply {old_supply} -> {new_supply}) (<4h since reset, confidence high)")
					fixed = True
					self.supply[pred_cycle-1] = viable_patterns[0].supply[pred_cycle-1]
					self.possible_patterns = viable_patterns
					self.code = new_code
				else:
					print(f"spreadsheet was made {hours_after_reset}h after reset (>=4h), you'll have to try fix it manually. the possible peaks (using yesterdays data) are {viable_patterns}. exiting... ")
					exit()

			else:
				print(f"got bad pred cycle ({pred_cycle}) or hours after reset ({hours_after_reset}) is None, couldn't fix. exiting... ")
				exit()

		pred_cycle = 1
		while self.supply[pred_cycle] is not None:
			pred_cycle += 1

		if pred_cycle == 1 and self.last_season_pattern and len(self.possible_patterns) <= 2:
			if len(self.possible_patterns) == 1:
				# already figured out its c2s or c2w in determine_pattern using last seasons data - could be thrown off by last season production though
				self.supply_guesses = [(self.possible_patterns[0], 1.0)]

			else:
				#figure out probs based on how many guaranteed/uncertain
				c2s = all_possible_patterns.get("C2S", 0)
				c2w = all_possible_patterns.get("C2W", 0)
				c2u = all_possible_patterns.get("C2W C2S", 0)
				total = c2s + c2w + c2u
				num_c2s = total/2 - c2s
				num_c2w = total/2 - c2w

				prob_c2s = num_c2s/(num_c2s + num_c2w)

				self.supply_guesses = [(PATTERNS["C2S"], prob_c2s), (PATTERNS["C2W"], 1.0 - prob_c2s)]
				print(self.name, self.supply_guesses)

		elif pred_cycle == 1:
			#use recorded probs for anything, even single possible pattern
			self.supply_guesses = OBSERVED_PATTERN_PROBS[self.code]

		else:
			#single possible patterns are safe, use recorded probs for other stuff
			if len(self.possible_patterns) == 1:
				self.supply_guesses = [(self.possible_patterns[0], 1.0)]
			else:
				self.supply_guesses = OBSERVED_PATTERN_PROBS[self.code]					

		self.supply_mult_guesses = [sum([exact_supply_to_bonus_guess(pattern.exact_supply[c])*prob for pattern, prob in self.supply_guesses]) for c in range(7)]
		#combbine same exact supplies and their probs for each cycle to make combo value much faster
		self.consolidate_supply_guesses()

		return fixed

	def __repr__(self):
		return f"Popularity: {self.popularity}, Possible patterns: {self.possible_patterns}"

class Pattern:
	"""
	Represents a supply pattern for one item over a season
	"""
	def __init__(self, name, supply, demand_shift, exact_supply, total=7):
		self.name = name
		self.supply = supply
		self.exact_supply = exact_supply
		self.demand_shift = demand_shift
		self.total = total

	def __repr__(self):
		return self.name

	def __lt__(self, other):
		return self.name < other.name

def load_items(file_name=path.join("resources", "items.csv"), blacklist=[], blacklist_ingredients=[]):
	with open(file_name, "r") as f:
		lines = [line.strip().split(",") for line in f.readlines()]
	headers = lines.pop(0)
	items = []
	for line in lines:
		categories = [line[3]]
		if line[4] != "":
			categories.append(line[4])
		ingredients = []
		for i in range(4):
			if line[5 + i*2] != "":
				ingredients.append((line[5 + i*2], int(line[6 + i*2])))
		if line[0] in blacklist: #if name on blacklisted
			print(f"Blacklisted item {line[0]} was not loaded.")
		else:
			item = Item(line[0], int(line[1]), int(line[2]), categories, ingredients)
			if any(ingredient in blacklist_ingredients for ingredient, n in item.ingredients):
				print(f"Blacklisted item {line[0]} was not loaded due to containing blacklisted ingredient(s).")
			else:
				items.append(item)

	return items

def find_items_by_category(items):
	items_by_category = dict()
	for item in items:
		for category in item.categories:
			if category not in items_by_category.keys():
				items_by_category[category] = []
			items_by_category[category].append(item)

	return items_by_category

def aggregate_possible_patterns(season_data):
	all_possible_patterns = dict()
	for item_name, item_season_data in season_data.items():
		possible_patterns = item_season_data.possible_patterns
		code = " ".join([pattern.name for pattern in possible_patterns])
		all_possible_patterns[code] = all_possible_patterns.get(code, 0) + 1
	return all_possible_patterns

def read_season_data(week_num, restrict_cycles=[], verbose=False, path_prefix=False, check_last_season=False):
	last_season_data = None
	if check_last_season and week_num > 1:
		last_season_path = path.join(path_prefix, f"week_{week_num-1}") if path_prefix else f"week_{week_num-1}"
		if path.exists(last_season_path):
			last_season_data = read_season_data(week_num - 1, path_prefix=path_prefix)
		else:
			print(f"Could not get prev season data, folder '{last_season_path}' does not exist.")

	cycle_spreadsheet_path = path.join(path_prefix, f"week_{week_num}") if path_prefix else f"week_{week_num}"
	cycle_spreadsheets = [file_name for file_name in listdir(cycle_spreadsheet_path) if file_name[:5] == "cycle" and file_name[-3:] == "csv"]
	season_spreadsheet = path.join(path_prefix, f"week_{week_num}", "season.csv") if path_prefix else path.join(f"week_{week_num}", "season.csv")
	season_data = dict()
	print(f"reading cycle data from week {week_num}: {cycle_spreadsheets}")
	with open(season_spreadsheet, "r") as f:
		lines = [line.strip().split(",") for line in f.readlines()]
	headers = lines.pop(0)
	for line in lines:
		name, popularity, predicted_demand = line
		last_season_pattern = False
		if last_season_data is not None and name in last_season_data.keys() and len(last_season_data[name].possible_patterns) == 1:
			last_season_pattern = last_season_data[name].possible_patterns[0]
		season_data[name] = ItemSeasonData(name, popularity, predicted_demand, last_season_pattern)

	mtime = path.getmtime(path.join(path_prefix, f"week_{week_num}", cycle_spreadsheets[-1]) if path_prefix else path.join(f"week_{week_num}", cycle_spreadsheets[-1]))
	tz = pytz.timezone('Japan')
	dtime = datetime.fromtimestamp(mtime, tz)
	hours_after_reset = (dtime.hour - 17) % 24
	print(f"modified time of last cycle spreadsheet ({cycle_spreadsheets[-1]}): {hours_after_reset} hours after reset, rounded down ({dtime})")
	for file_name in cycle_spreadsheets:
		cycle_num = int(file_name[5])
		if cycle_num in restrict_cycles:
			if verbose: print(f"Skipped cycle {cycle_num} data")
			continue
		cycle_spreadsheet = path.join(path_prefix, f"week_{week_num}", file_name) if path_prefix else path.join(f"week_{week_num}", file_name)
		with open(cycle_spreadsheet, "r") as f:
			lines = [line.strip().split(",") for line in f.readlines()]
		headers = lines.pop(0)
		for line in lines:
			name, supply, demand_shift = line
			season_data[name].set_cycle(cycle_num, supply, demand_shift)

	for name in season_data.keys():
		# print(name, season_data[name])
		season_data[name].determine_pattern()

	any_fixed = False
	all_possible_patterns = aggregate_possible_patterns(season_data)
	if verbose: print(all_possible_patterns)
	for name in season_data.keys():
		fixed = season_data[name].guess_supply(all_possible_patterns, hours_after_reset)
		if fixed: any_fixed = True

	if any_fixed:
		print(f"fixing {cycle_spreadsheets[-1]}... ")
		fix_path = path.join(path_prefix, f"week_{week_num}", cycle_spreadsheets[-1]) if path_prefix else path.join(f"week_{week_num}", cycle_spreadsheets[-1])
		arch_path = path.join(path_prefix, f"week_{week_num}", "#0" + cycle_spreadsheets[-1]) if path_prefix else path.join(f"week_{week_num}", "#0" + cycle_spreadsheets[-1])
		i = 1
		while path.exists(arch_path):
			arch_path = path.join(path_prefix, f"week_{week_num}", f"#{1}" + cycle_spreadsheets[-1]) if path_prefix else path.join(f"week_{week_num}", f"#{1}" + cycle_spreadsheets[-1])
			i += 1
		rename(fix_path, arch_path)
		with open(fix_path, "w") as f:
			f.write("Product,Supply,Demand Shift\n")
			pred_cycle = int(cycle_spreadsheets[-1][5])
			for item_season_data in season_data.values():
				f.write(",".join([str(x) for x in (item_season_data.name, SUPPLY_VALUES[item_season_data.supply[pred_cycle-1]], DEMAND_SHIFT_VALUES[item_season_data.demand_shift[pred_cycle-1]])]) + "\n")
		print(f"old {fix_path} archived to {arch_path}, new (fixed) version written to {fix_path} (pred cycle {pred_cycle})")

	return season_data

SEASON_LENGTH = 7
SUPPLY_VALUES = ["Nonexistent", "Insufficient", "Sufficient", "Surplus", "Overflowing"]
SUPPLY_BONUSES = [1.6, 1.3, 1.0, 0.8, 0.6]
DEMAND_SHIFT_VALUES = ["Plummeting", "Decreasing", "None", "Increasing", "Skyrocketing"]
POPULARITY_VALUES = ["Low", "Average", "High", "Very High"]
POPULARITY_BONUSES = [0.8, 1, 1.2, 1.4]

PATTERNS = [
	Pattern("C2W", [1, 1, 2, 2, 2, 2, 2], [3, 3, 0, 2, 2, 2, 2], [-4,-8,2, 2, 2, 2, 2]),
	Pattern("C2S", [1, 0, 2, 2, 2, 2, 2], [4, 4, 0, 2, 2, 2, 2], [-7,-15,0,0, 0, 0, 0]),
	Pattern("C3W", [2, 1, 1, 2, 2, 2, 2], [2, 3, 3, 0, 2, 2, 2], [0,-4,-8, 2, 2, 2, 2]),
	Pattern("C3S", [2, 1, 0, 2, 2, 2, 2], [2, 4, 4, 0, 2, 2, 2], [0,-7,-15,0, 0, 0, 0]),
	Pattern("C4W", [2, 2, 1, 1, 2, 2, 2], [2, 2, 3, 3, 0, 2, 2], [0, 0,-4,-8, 2, 2, 2]),
	Pattern("C4S", [2, 2, 1, 0, 2, 2, 2], [2, 2, 4, 4, 0, 2, 2], [0, 0,-7,-15,0, 0, 0]),
	Pattern("C5W", [2, 2, 2, 1, 1, 2, 2], [2, 2, 2, 3, 3, 0, 2], [0, 0, 0,-4,-8, 2, 2]),
	Pattern("C5S", [2, 2, 2, 1, 0, 2, 2], [2, 2, 2, 4, 4, 0, 2], [0, 0, 0,-7,-15,0, 0]),
	Pattern("C6W", [2, 1, 2, 2, 1, 1, 2], [2, 3, 1, 3, 3, 3, 0], [0,-1, 4, 0,-4,-8, 2]),
	Pattern("C6S", [2, 1, 2, 2, 1, 0, 2], [2, 3, 0, 4, 4, 4, 0], [0,-1, 7, 0,-7,-15,0]),
	Pattern("C7W", [2, 1, 2, 2, 2, 1, 1], [2, 3, 0, 3, 3, 3, 3], [0,-1, 7, 4, 0,-4,-8], total=8),
	Pattern("C7S", [2, 1, 2, 2, 2, 1, 0], [2, 3, 0, 2, 4, 4, 4], [0,-1, 7, 7,0,-7,-15], total=8),
]
PATTERNS = {pattern.name: pattern for pattern in PATTERNS}

OBSERVED_PATTERN_PROBS = {
	'C2S': [('C2S', 0.6305732484076433), ('C2W', 0.36942675159235666)],
	'C2W': [('C2W', 1.0)],
	'C2W C2S': [('C2W', 0.5), ('C2S', 0.5)],
	'C3W C3S C4W C4S C5W C5S C6W C6S C7W C7S': [('C4W', 0.09657320872274143), ('C3S', 0.09657320872274143), ('C6S', 0.09657320872274143), ('C4S', 0.09657320872274143), ('C7S', 0.11370716510903427), ('C7W', 0.11370716510903427), ('C5W', 0.09657320872274143), ('C6W', 0.09657320872274143), ('C5S', 0.09657320872274143), ('C3W', 0.09657320872274143)],
	'C3W C6W C6S C7W C7S': [('C6S', 0.18674698795180722), ('C7S', 0.21987951807228914), ('C7W', 0.21987951807228914), ('C6W', 0.18674698795180722), ('C3W', 0.18674698795180722)],
	'C4W C4S C5W C5S': [('C4W', 0.25), ('C4S', 0.25), ('C5W', 0.25), ('C5S', 0.25)],
	'C5W C5S': [('C5W', 0.5), ('C5S', 0.5)],
	'C6S C7W C7S': [('C6S', 0.2980769230769231), ('C7S', 0.35096153846153844), ('C7W', 0.35096153846153844)],
}
OBSERVED_PATTERN_PROBS = {code: [(PATTERNS[name], prob) for name, prob in value] for code, value in OBSERVED_PATTERN_PROBS.items()}

CODE_CYCLE_MULTS = {
	#pred cycle 1
	'C3W C3S C4W C4S C5W C5S C6W C6S C7W C7S': [1, 1, 1.25, 1.25, 1.25, 1.25, 1.25],
	#pred cycle 2
	'C3W C6W C6S C7W C7S': [1, 1, 1, 1, 1, 1.15, 1.15],
	'C4W C4S C5W C5S': [1, 1, 1, 1.1, 1.15, 1, 1],
	#pred cycle 3
	#'C5W C5S': [1, 1, 1, 1, 1.0, 1, 1],
	'C6S C7W C7S': [1, 1, 1, 1, 1, 1.1, 1.1],
}

def exact_supply_to_bonus(exact_supply):
	if exact_supply <= -9:
		return 1.6
	elif exact_supply <= -1:
		return 1.3
	elif exact_supply <= 7:
		return 1.0
	elif exact_supply <= 15:
		return 0.8
	else:
		return 0.6

def exact_supply_to_bonus_guess(exact_supply):
	if exact_supply <= -9:
		return 1.6 - 0.3*(exact_supply+16)/8
	elif exact_supply <= -1:
		return 1.3 - 0.3*(exact_supply+8)/8
	elif exact_supply <= 7:
		return 1.0 - 0.2*(exact_supply)/8
	elif exact_supply <= 15:
		return 0.8 - 0.2*(exact_supply-8)/8
	else:
		return 0.6


def test(week_num=3):
	# read_cycle_data_from_website(week_num)

	# season_data = read_season_data(week_num)
	# for item_name, item_season_data in season_data.items():
	# 	print(item_name, item_season_data)

	for exact_supply in range(-16, 17):
		print(exact_supply, exact_supply_to_bonus_guess(exact_supply))

if __name__ == "__main__":
	test()
