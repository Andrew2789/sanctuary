from workshop_items import *
from planning import *
import json, cv2
import numpy as np
from os import path, makedirs

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

# if __name__ == "__main__":
# 	max_diff = 0
# 	mean_diff = 0
# 	i = 0
# 	for starting_groove in range(0, 46):
# 		for groove in range(starting_groove+1, starting_groove+5):
# 			for cycle_index in range(5):
# 				proper = guess_groove_value(starting_groove, groove, cycle_index) 
# 				fast = guess_groove_value_fastest(starting_groove, groove, cycle_index) 
# 				diff = abs(fast-proper)
# 				mean_diff = (mean_diff*i + diff)/(i+1)
# 				if diff > max_diff:
# 					print(f"start groove {starting_groove} -> {groove} c{cycle_index} proper {proper} fast {fast} diff {diff}")
# 					max_diff = diff
# 				i += 1


# 	print(f"mean diff {mean_diff}")
# 	print(guess_groove_value(20, 23, 1))
# 	print(guess_groove_value_fast(20, 23, 1))

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
	if "cavalier" in name.lower(): #.title() messes with the 's in cavaliers, so just handle it now
		return "Isleworks Cavalier's Hat"
	elif "hawk" in name.lower():
		return "Isleworks Hawk's Eye Sand"

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

def shorten_name(name):
	if name == "Mammet of the Cycle Award":
		return "Mammet Cycle Award"
	else:
		return name.replace("Isleworks ", "").replace("Island ", "")

CATEGORY_COLOURS = {
	"Preserved Food": (47, 75, 97, 255),
	"Attire": (130, 31, 33, 255),
	"Foodstuffs": (6, 94, 20, 255),
	"Confections": (13, 0, 130, 255),
	"Sundries": (2, 68, 156, 255),
	"Furnishings": (2, 58, 105, 255),
	"Arms": (43, 43, 43, 255),
	"Concoctions": (115, 0, 82, 255),
	"Ingredients": (3, 34, 128, 255),
	"Accessories": (87, 97, 4, 255),
	"Metalworks": (74, 74, 74, 255),
	"Woodworks": (0, 42, 84, 255),
	"Textiles": (73, 0, 115, 255),
	"Creature Creations": (13, 115, 101, 255),
	"Marine Merchandise": (168, 65, 17, 255),
	"Unburied Treasures": (17, 128, 168, 255),
}
BACKGROUND_COL = (51, 47, 42, 255)
BANNER_COL = (26, 24, 21, 255)
TITLE_SIDEBAR_WIDTH = 72
TEXT_SCALE = 0.6
TITLE_SCALE = 0.8
TEXT_OFFSET = 3
BORDER = 2
HOUR_HEIGHT = 12
COLUMN_WIDTH = 240
CATEGORY_WIDTH = 192

def draw_text(image, y_start, height, x_start, width, text, text_scale=1.0, x_off=0, y_off=0, align_left=True, align_top=True, align_centre=False, font=cv2.FONT_HERSHEY_SIMPLEX, thickness=1, colour=(255, 255, 255, 255)):
	text_size = cv2.getTextSize(text, font, text_scale, 1)[0]
	text_x = (0 if align_left else -text_size[0]) + x_off
	text_y = (text_size[1] if align_top else height) + y_off
	if align_centre:
		text_x = width-text_size[0]+x_off
		text_y = text_size[1] + (height-text_size[1])//2 + y_off
	image[y_start:y_start+height, x_start:x_start+width] = cv2.putText(
			image[y_start:y_start+height, x_start:x_start+width], text, (text_x, text_y), font, 
			fontScale=text_scale, color=colour, thickness=thickness, lineType=cv2.LINE_AA)
		
def get_dims(draw_hours, draw_headers, body_cells):
	hour_column_width = 30 + TITLE_SIDEBAR_WIDTH if draw_hours else TITLE_SIDEBAR_WIDTH
	header_height = 30 if draw_headers else 0
	total_height = header_height + HOUR_HEIGHT*body_cells
	total_width = hour_column_width + COLUMN_WIDTH*NUM_WORKSHOPS + CATEGORY_WIDTH #4 workshops + info column

	return hour_column_width, header_height, total_width, total_height

def draw_workshop_headers(image, hour_column_width, header_height):
	for workshop_index in range(NUM_WORKSHOPS):
		cx = hour_column_width + COLUMN_WIDTH*workshop_index
		image[0:header_height-BORDER*2, cx:cx+COLUMN_WIDTH-BORDER*2] = BACKGROUND_COL
		draw_text(image, 0, header_height, cx, COLUMN_WIDTH, f"Workshop {workshop_index+1}", TEXT_SCALE, x_off=TEXT_OFFSET, y_off=(header_height - HOUR_HEIGHT*2)+TEXT_OFFSET-BORDER*2)

def generate_cycle_banner(banner_title, banner_text, draw_hours=True, draw_headers=True, out_name=None, large=True):
	"""Used for eg. C2: Rest or C5: TBD"""
	BODY_CELLS = 3 if large else 3
	hour_column_width, header_height, total_width, total_height = get_dims(draw_hours, draw_headers, BODY_CELLS)
	canvas = np.zeros((total_height, total_width, 4), dtype=np.uint8) #BGRA format

	if draw_hours and large: #add blank hours box
		canvas[header_height:total_height-BORDER, TITLE_SIDEBAR_WIDTH:hour_column_width-BORDER*2] = BACKGROUND_COL

	#title bg
	title_border = BORDER if draw_hours else BORDER*2
	if banner_title:
		canvas[header_height:total_height-BORDER, 0:TITLE_SIDEBAR_WIDTH-title_border] = BACKGROUND_COL

	if draw_headers: draw_workshop_headers(canvas, hour_column_width, header_height)

	#banner bg
	if large:
		for i in range(NUM_WORKSHOPS): canvas[header_height:total_height-BORDER, hour_column_width+i*COLUMN_WIDTH:hour_column_width+(i+1)*COLUMN_WIDTH-BORDER*2] = BANNER_COL
	else:
		canvas[header_height:total_height, hour_column_width:hour_column_width+3*COLUMN_WIDTH-BORDER*2] = BACKGROUND_COL
	#title and banner text
	if large:
		draw_text(canvas, header_height, total_height-header_height, 0, TITLE_SIDEBAR_WIDTH, banner_title, TITLE_SCALE, x_off=-title_border-2, y_off=-2, align_centre=True, thickness=2)
		draw_text(canvas, header_height, total_height-header_height, hour_column_width, NUM_WORKSHOPS*COLUMN_WIDTH, banner_text, TITLE_SCALE, x_off=TEXT_OFFSET, y_off=TEXT_OFFSET*2+1)
	else:
		draw_text(canvas, header_height, total_height-header_height, 0, TITLE_SIDEBAR_WIDTH, banner_title, TEXT_SCALE, x_off=-title_border-2, y_off=-2, align_centre=True, thickness=1)
		if type(banner_text) == str:
			banner_text = [banner_text]
		for i, text in enumerate(banner_text):
			if i == 0:
				draw_text(canvas, header_height, total_height-header_height, hour_column_width+i*COLUMN_WIDTH, NUM_WORKSHOPS*COLUMN_WIDTH, text, TITLE_SCALE, x_off=TEXT_OFFSET, y_off=TEXT_OFFSET*2+2, thickness=2 if i==0 else 1)
			else:
				draw_text(canvas, header_height, total_height-header_height, hour_column_width+i*COLUMN_WIDTH, NUM_WORKSHOPS*COLUMN_WIDTH, text, TEXT_SCALE, x_off=TEXT_OFFSET, y_off=-TEXT_OFFSET*3, align_top=False)

	if out_name is not None:
		cv2.imwrite(out_name, canvas)

	return canvas

def cycle_to_image(cycle_name, cycle_combos, draw_hours=True, draw_headers=True, out_name=None, earnings=0):
	BODY_CELLS = 12

	hour_column_width, header_height, total_width, total_height = get_dims(draw_hours, draw_headers, BODY_CELLS)
	canvas = np.zeros((total_height, total_width, 4), dtype=np.uint8) #BGRA format

	def draw_cell(y, x, h, left_colour, right_colour=None, text="", bottom=False, thickness=1, right_text=""):
		cy = header_height + y*HOUR_HEIGHT
		cx = hour_column_width + COLUMN_WIDTH*x
		cy_end = cy+HOUR_HEIGHT*h-BORDER if bottom else cy+HOUR_HEIGHT*h
		canvas[cy:cy_end, cx:cx+COLUMN_WIDTH-BORDER*2] = left_colour
		if right_colour: canvas[cy:cy_end, cx+COLUMN_WIDTH//2:cx+COLUMN_WIDTH-BORDER*2] = right_colour

		# for sep in range(2, h, 2):
		# 	canvas[cy+HOUR_HEIGHT*sep:cy+HOUR_HEIGHT*sep+BORDER, cx+BORDER*12:cx+COLUMN_WIDTH-BORDER*14] = (0, 0, 0, 0)

		draw_text(canvas, cy, HOUR_HEIGHT*h, cx, COLUMN_WIDTH, text, TEXT_SCALE, x_off=TEXT_OFFSET, y_off=TEXT_OFFSET)
		# draw_text(canvas, cy, HOUR_HEIGHT*h, cx, COLUMN_WIDTH, right_text, 1.0, x_off=COLUMN_WIDTH-TEXT_OFFSET-BORDER*2, y_off=TEXT_OFFSET*2, align_left=False, colour=(0, 0, 0, 0), thickness=2)
		faded_colour = right_colour if right_colour is not None else left_colour
		faded_colour = list(faded_colour)[:3] + [120]
		draw_text(canvas, cy, HOUR_HEIGHT*h, cx, COLUMN_WIDTH, right_text, 1.6, x_off=-TEXT_OFFSET*2, y_off=-TEXT_OFFSET+1, align_centre=True, colour=faded_colour, thickness=3)

	def draw_workshop(workshop_index, workshop_combo, duplicate=False, values=None):
		combo_category_freqs = dict()
		for item in workshop_combo:
			for category in item.categories:
				combo_category_freqs[category] = combo_category_freqs.get(category, 0) + 1

		sorted_freqs = sorted(combo_category_freqs.items(), key=lambda x: -x[1])
		pref_slot1 = sorted_freqs[0][0]
		pref_slot2 = sorted_freqs[1][0] if len(sorted_freqs) > 1 else None
		time = 0
		for i, item in enumerate(workshop_combo):
			if len(item.categories) == 1: #nice and easy
				left_category = item.categories[0]
				right_category = item.categories[0]
			else: #2 categories
				if pref_slot1 in item.categories:
					left_category = pref_slot1
					right_category = item.categories[0 if item.categories[1] == pref_slot1 else 1]
				elif pref_slot2 in item.categories:
					right_category = pref_slot2
					left_category = item.categories[0 if item.categories[1] == pref_slot2 else 1]
				else:
					left_category = item.categories[0]
					right_category = item.categories[1]
			draw_cell(time//2, workshop_index, item.time//2, CATEGORY_COLOURS[left_category], CATEGORY_COLOURS[right_category], "" if duplicate else f"{shorten_name(item.name)}", right_text="" if item.time <= 4 else f"{item.time}", bottom=True)
			time += item.time

		if duplicate:
			cx = hour_column_width + COLUMN_WIDTH*workshop_index
			canvas[header_height:header_height+12*HOUR_HEIGHT, cx:cx+COLUMN_WIDTH] = cv2.arrowedLine(canvas[header_height:header_height+12*HOUR_HEIGHT, cx:cx+COLUMN_WIDTH], 
				(COLUMN_WIDTH-BORDER*20, 6*HOUR_HEIGHT-BORDER), (BORDER*20, 6*HOUR_HEIGHT-BORDER), (255, 255, 255, 255), thickness=3, tipLength=0.2)  

	#draw hour labels
	if draw_hours:
		for y in range(0, BODY_CELLS, 2):
			cy = header_height + y*HOUR_HEIGHT
			canvas[cy:cy+HOUR_HEIGHT*2-BORDER, TITLE_SIDEBAR_WIDTH:hour_column_width-BORDER*2] = BACKGROUND_COL
			draw_text(canvas, cy, HOUR_HEIGHT*2, TITLE_SIDEBAR_WIDTH, hour_column_width-TITLE_SIDEBAR_WIDTH, str(y*2), TEXT_SCALE, x_off=hour_column_width-TITLE_SIDEBAR_WIDTH-BORDER*2, y_off=TEXT_OFFSET, align_left=False)
			
	workshop_combos = []
	for cycle_combo, num_workshops in cycle_combos:
		for _ in range(num_workshops):
			workshop_combos.append(cycle_combo)

	#draw cycle title + earnings
	title_border = BORDER if draw_hours else BORDER*2
	canvas[header_height:total_height-BORDER, 0:TITLE_SIDEBAR_WIDTH-title_border] = BACKGROUND_COL
	draw_text(canvas, header_height, total_height-header_height, 0, TITLE_SIDEBAR_WIDTH, cycle_name, TITLE_SCALE, x_off=-title_border-2, y_off=-14, align_centre=True, thickness=2)
	draw_text(canvas, header_height, total_height-header_height, 0, TITLE_SIDEBAR_WIDTH, f"{earnings}", TEXT_SCALE, x_off=-title_border-2, y_off=12, align_centre=True, thickness=1)

	#draw main columns
	if draw_headers: draw_workshop_headers(canvas, hour_column_width, header_height)
	for workshop_index in range(NUM_WORKSHOPS): 
		draw_workshop(workshop_index, workshop_combos[workshop_index], duplicate=workshop_index > 0 and workshop_combos[workshop_index] == workshop_combos[workshop_index-1])

	#get category counts
	current_row = 0
	all_used_categories = dict()
	for workshop_combo in workshop_combos:
		for item in workshop_combo:
			for category in item.categories:
				all_used_categories[category] = all_used_categories.get(category, 0) + 1

	if out_name is not None:
		cv2.imwrite(out_name, canvas)

	return canvas, all_used_categories

def load_saved_plan(week_num, save_name, display=True):
	items = load_items()
	season_data = read_season_data(week_num, verbose=False, check_last_season=False)
	items_by_name = {item.name: item for item in items}

	file_path = path.join(f"week_{week_num}", "saves", save_name)
	print(f"loading {file_path}... ")
	save_data = load_json(file_path)
	season_combos = combos_from_text(save_data["full_combos"], items_by_name)
	rest_days = save_data["full_rest_days"]
	plan = Plan(rest_days, season_combos, season_data)
	if display: plan.display()
	return plan

def plan_to_image(week_num, pred_cycle, task_name, show_rest_days=True, draw_hours=False, draw_workshop_header=False, vert_title=True, plan=None):
	if plan is None:
		plan = load_saved_plan(week_num, f"c{pred_cycle}_{task_name}.json", display=False)

	cycle_index = 0
	images = []
	banner_text = [f"6.5 W{week_num} C{pred_cycle}", f"Agenda: {task_name}"]
	if pred_cycle >= 4:
		banner_text.append(f"Total: {plan.value}")
	title_banner = generate_cycle_banner("", banner_text, draw_hours, draw_headers=False, large=False)
	if vert_title:
		hour_column_width, _, _, _ = get_dims(draw_hours, False, 0)
		title = np.zeros((HOUR_HEIGHT*(10 if pred_cycle >= 4 else 8), CATEGORY_WIDTH, 4), dtype=np.uint8) #BGRA format
		title[HOUR_HEIGHT*0:HOUR_HEIGHT*3, :CATEGORY_WIDTH] = title_banner[:,hour_column_width:hour_column_width+CATEGORY_WIDTH]
		title[HOUR_HEIGHT*3+BORDER*3:HOUR_HEIGHT*6, :CATEGORY_WIDTH] = BACKGROUND_COL
		title[HOUR_HEIGHT*4:HOUR_HEIGHT*6, :CATEGORY_WIDTH] = title_banner[HOUR_HEIGHT:,hour_column_width+COLUMN_WIDTH:hour_column_width+COLUMN_WIDTH+CATEGORY_WIDTH]
		if pred_cycle >= 4: #total
			title[HOUR_HEIGHT*6:HOUR_HEIGHT*8, :CATEGORY_WIDTH] = title_banner[HOUR_HEIGHT:,hour_column_width+COLUMN_WIDTH*2:hour_column_width+COLUMN_WIDTH*2+CATEGORY_WIDTH]

	else: #horiz title
		images.append(title_banner)
	headers_done = not draw_workshop_header
	all_used_categories = dict()
	for cycle in range(1, 8):
		if pred_cycle < 4 and cycle > pred_cycle + 1:
			images.append(generate_cycle_banner(f"C{cycle}", f"TBD (C{min(4, cycle-1)})", draw_hours, draw_headers=False))
		elif cycle in plan.rest_days:
			if show_rest_days:
				images.append(generate_cycle_banner(f"C{cycle}", "Rest", draw_hours, draw_headers=not headers_done))
				headers_done = True
		else:
			image, used_categories = cycle_to_image(f"C{cycle}", plan.best_combos[cycle_index], draw_hours, draw_headers=not headers_done, earnings=plan.earnings_per_cycle[cycle_index])
			images.append(image)
			for category, freq in used_categories.items():
				all_used_categories[category] = all_used_categories.get(category, 0) + freq
			headers_done = True
			cycle_index += 1


	total_width = images[0].shape[1] #should be same for all images
	total_height = sum(image.shape[0] for image in images) + BORDER*2*(len(images)-1)
	canvas = np.zeros((total_height, total_width, 4), dtype=np.uint8) #BGRA format
	current_y = 0
	for image in images:
		canvas[current_y:current_y+image.shape[0], :] = image
		current_y += image.shape[0] + BORDER*2

	all_used_categories = sorted(all_used_categories.items(), key=lambda x: -x[1])
	category_canvas = np.zeros((HOUR_HEIGHT*2*(len(all_used_categories)+1), CATEGORY_WIDTH, 4), dtype=np.uint8) #BGRA format
	category_canvas[0:2*HOUR_HEIGHT-BORDER, 0:CATEGORY_WIDTH] = BACKGROUND_COL
	draw_text(category_canvas, 0, 2*HOUR_HEIGHT, 0, CATEGORY_WIDTH, "Categories:", TEXT_SCALE, x_off=TEXT_OFFSET, y_off=TEXT_OFFSET)
	for i, (category_name, freq) in enumerate(all_used_categories, start=1):
		cy = i*2*HOUR_HEIGHT
		category_canvas[cy:cy+2*HOUR_HEIGHT, 0:CATEGORY_WIDTH] = CATEGORY_COLOURS[category_name]
		draw_text(category_canvas, cy, 2*HOUR_HEIGHT, 0, CATEGORY_WIDTH, category_name, TEXT_SCALE, x_off=TEXT_OFFSET, y_off=TEXT_OFFSET)

	if vert_title:
		combined_canvas = np.zeros((category_canvas.shape[0]+title.shape[0], CATEGORY_WIDTH, 4), dtype=np.uint8) #BGRA format
		combined_canvas[:title.shape[0], :] = title
		combined_canvas[title.shape[0]:, :] = category_canvas
		y_start = (canvas.shape[0] - combined_canvas.shape[0])//2
		canvas[:,CATEGORY_WIDTH + 2*BORDER:] = canvas[:,:-CATEGORY_WIDTH-2*BORDER] #move main stuff to the right
		canvas[:,:CATEGORY_WIDTH + 2*BORDER] = (0, 0, 0, 0)
		canvas[y_start:y_start+combined_canvas.shape[0],:CATEGORY_WIDTH] = combined_canvas
	else:
		y_start = (canvas.shape[0] - category_canvas.shape[0])//2
		canvas[y_start:y_start+category_canvas.shape[0],-CATEGORY_WIDTH:] = category_canvas

	canvas = canvas[0:canvas.shape[0]-BORDER,:]

	out_path = path.join(f"week_{week_num}", "display_images")
	makedirs(out_path, exist_ok=True)
	out_path = path.join(out_path, f"c{pred_cycle}_{task_name}.png")
	print(f"exporting {total_width}x{total_height} image to {out_path}... ")
	cv2.imwrite(out_path, canvas)