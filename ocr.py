from pytesseract import Output
import numpy as np
import pytesseract
import cv2
from os import listdir, path
from workshop_items import *

#original src https://pyimagesearch.com/2022/02/28/multi-column-table-ocr/
#windows tesseract binary https://github.com/UB-Mannheim/tesseract/wiki
#tesseract psm resource https://pyimagesearch.com/2021/11/15/tesseract-page-segmentation-modes-psms-explained-how-to-improve-your-ocr-accuracy/

class OCRWord:
	def __init__(self, text, bbox):
		self.text = text
		self.bbox = bbox
		self.x, self.y, self.w, self.h = bbox
		self.max_x = self.x + self.w
		self.max_y = self.y + self.h

class Column:
	def __init__(self, name, start_bound, end_bound, legal_words):
		self.words = []
		self.rows = []
		self.name = name
		self.start_bound = start_bound
		self.end_bound = end_bound
		self.legal_words = legal_words

	def contains(self, word):
		if self.end_bound == -1:
			return self.start_bound <= word.x
		else: 
			return self.start_bound <= word.x < self.end_bound

	def add_word(self, word, debug=False):
		if self.legal_words is None or word.text in self.legal_words:
			self.words.append(word)
		elif debug:
			print("Failed to add member %s: illegal word" % word.text)

	def find_rows(self, dist_thresh=5):
		clusters = []
		for word in self.words:
			avg_y = word.y + word.h/2
			closest_cluster = -1
			closest_dist = float("inf")
			for i, (cluster_y, _) in enumerate(clusters):
				dist = abs(avg_y - cluster_y)
				if dist < closest_dist:
					closest_cluster = i
					closest_dist = dist
			if closest_dist > dist_thresh:
				#make a new cluster
				clusters.append((avg_y, [word]))
			else:
				clusters[closest_cluster][1].append(word)

		clusters = sorted(clusters)
		self.rows = []
		for cluster_y, words in clusters:
			words = sorted(words, key=lambda word: word.x)
			text = " ".join([word.text.replace("Iste", "Isle") for word in words])
			min_x = words[0].x
			min_y = min(words, key=lambda word: word.y).y
			max_x = max(words, key=lambda word: word.max_x).max_x
			max_y = max(words, key=lambda word: word.max_y).max_y
			bbox = (min_x, min_y, max_x - min_x, max_y - min_y)
			self.rows.append(OCRWord(text, bbox))

def write_csv(file_name, relevant_indices, column_names, tables):
	if path.exists(file_name):
		print(f"\n\nWARNING: file {file_name} already exists, not writing...\n\n")
		return
	written = []
	with open(file_name, "w") as f:
		relevant_column_names = [name for i, name in enumerate(column_names) if i in relevant_indices]
		f.write(",".join(relevant_column_names) + "\n")
		for table in tables:
			relevant_columns = [column for i, column in enumerate(table) if i in relevant_indices]
			column_lengths = [len(column.rows) for column in relevant_columns]
			print(column_lengths)
			column_length = column_lengths[0]
			for row in range(column_length):
				text = [column.rows[row].text for column in relevant_columns]
				if text not in written:
					f.write(",".join(text) + "\n")
					written.append(text)
				else:
					print(f"duplicate row {text} skipped")

def extract_cycle_from_screenshots(week_num, cycle_num, x_crop=0, debug=False, export_season_data=True):
	SCREENSHOT_FOLDER = "C:\\Users\\Andrew\\Documents\\My Games\\FINAL FANTASY XIV - A Realm Reborn\\screenshots"
	screenshot_names = listdir(SCREENSHOT_FOLDER)
	dated_screenshots = [(path.getmtime(path.join(SCREENSHOT_FOLDER, image_name)), image_name) for image_name in screenshot_names]
	dated_screenshots.sort()
	# dated_screenshots = dated_screenshots[:-1] #TODO - remove this testing line
	images = [cv2.imread(path.join(SCREENSHOT_FOLDER, image_name))[314:652, :960] for time, image_name in dated_screenshots[-6:]]
	for i in range(len(images)): #crop top and bottom
		image = cv2.cvtColor(images[i], cv2.COLOR_BGR2GRAY)
		crop_top = 0
		while np.amin(image[crop_top, :]) < 80:
			crop_top += 1
		if crop_top > 15: #found a whole row, leave it
			crop_top = 0

		crop_bottom = -1
		while np.amin(image[crop_bottom, :]) < 80:
			crop_bottom -= 1
		if crop_bottom < -15: #found a whole row, leave it
			crop_bottom = -1

		if crop_bottom != -1:
			images[i] = images[i][crop_top:crop_bottom]
		else:
			images[i] = images[i][crop_top:]

		if debug:
			print(crop_top, crop_bottom)
			cv2.imshow("Output", images[i])
			cv2.waitKey(0)

	_extract_cycle(week_num, cycle_num, images, x_crop, debug, export_season_data)

def extract_cycle_from_snips(week_num, cycle_num, x_crop=0, debug=False, export_season_data=True):
	image_names = listdir(path.join(f"week_{week_num}", "images"))
	image_names = [image_name for image_name in image_names if image_name[0] == "c" and image_name[1] == str(cycle_num)]
	print(image_names)
	images = [cv2.imread(path.join(f"week_{week_num}", "images", image_name))[:,x_crop:] for image_name in image_names]
	_extract_cycle(week_num, cycle_num, images, x_crop, debug, export_season_data)

def _extract_cycle(week_num, cycle_num, images, x_crop=0, debug=False, export_season_data=True):
	np.random.seed(42)
	#crop = 25 for excluding first icon
	columns_bounds = [x - x_crop for x in (0, 250, 470, 650, 830)] + [-1]
	column_names = ["Product", "Popularity", "Supply", "Demand Shift", "Predicted Demand"]
	tiers = ["Low", "Average", "High", "Very"]
	legal_words = [None, tiers, SUPPLY_VALUES, DEMAND_SHIFT_VALUES, tiers]

	tables = []
	for image in images:
		image[:, 265:290] = image[:, 240:265] #block out smileys before 2nd column (popularity)
		image[:, 805:833] = image[:, 777:805] #block out smileys before final column (predicted demand/pop)
		columns = [Column(column_names[i], columns_bounds[i], columns_bounds[i+1], legal_words[i]) for i in range(len(column_names))]

		# set the PSM mode to detect sparse text, and then localize text in the table
		results = pytesseract.image_to_data(cv2.cvtColor(image, cv2.COLOR_BGR2RGB),	config="--psm 3", output_type=Output.DICT)

		for i in range(len(results["text"])):
			confidence = int(results["conf"][i])
			# filter out weak confidence text localizations
			if confidence > 10:
				# extract the bounding box coordinates of the text region from the current result
				word = OCRWord(results["text"][i], [results[key][i] for key in ("left", "top", "width", "height")])
				for column in columns:
					if column.contains(word):
						column.add_word(word, debug=debug)
						break

		for column in columns:
			column.find_rows()
			color = np.random.randint(0, 255, size=(3,), dtype="int")
			color = [int(c) for c in color]

			if debug:
				for word in column.rows:
					x, y, w, h = word.bbox
					cv2.rectangle(image, (x, y), (x + w, y + h), color, 2)

		# show the output image after performing multi-column OCR
		if debug:
			cv2.imshow("Output", image)
			cv2.waitKey(0)

		tables.append(columns)
	cv2.destroyAllWindows()

	if export_season_data:
		write_csv(path.join(f"week_{week_num}", "season.csv"), [0, 1, 4], column_names, tables)

	write_csv(path.join(f"week_{week_num}", f"cycle{cycle_num}.csv"), [0, 2, 3], column_names, tables)

if __name__ == "__main__":
	extract_cycle_from_snips(week_num=6, cycle_num=2, debug=True, export_season_data=False)
	# extract_cycle_from_screenshots(week_num=5, cycle_num=10, debug=True, export_season_data=False)
