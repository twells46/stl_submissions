This project is designed to automate the creation of receipts for submitted STL files. There are currently three main scripts:

1. clean_hubspot_dl_names.sh : This cleans up the downloaded filenames.
2. render.py : This uses blender to capture images of the submitted STL. The current iteration is designed to take a single input folder with STLs and dump all the resulting images into a single output folder.
This must have access to `bpy`. The easiest way is to install blender and run like this:
```
blender -b -P ./render.py
```
You could also install `bpy` via `pip`.
3. compose.py : Composes the receipt email and outputs to an `eml` file in, which I import into thunderbird to inspect and send.

Here's my plan for the directory structure:

```
region
	team_num-team_name
		email.txt
		part1.stl
		part2.stl
		part1
			90.png
			180.png
			270.png
			360.png
		part2
			90.png
			180.png
			270.png
			360.png
```

Here's how I'm planning to use it:

1. Download all of the submission for a region into their folder.
This will probably have to be manual because I don't think I can automatically download from Hubspot form submissions -- at least not at our tier.
2. Cleanup all of the filenames. I can automate easily with `cd <region> && fd -e stl -x ./clean_hubspot_dl_names.sh`.
3. Capture renders. I need to decide exactly how, but I need to add args to the render script. I'll probably just factor the current `input_folder` and `output_base` into args.
4. Compose email.
This will probably take the team's directory as the param and will fill in the email from the `email.txt` file, then grab the `270.png` from each directly for the images.
It can also fill the team name and number by parsing the directory name.

Final:

```sh
cd <region>
fd -e stl
```

Generate all renders for a region.
`stdout` is buffered by default and won't appear until that process is done.

```sh
cd <region>
fd -d 1 -x blender -b -P ../render.py -- {}
```
