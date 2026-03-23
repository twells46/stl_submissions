# STL Submissions

Small utility repo for turning STL form submissions into receipt emails.

The workflow is simple:

1. Put each region's submissions in its own folder.
2. Normalize STL filenames.
3. Render preview images for each part.
4. Generate a receipt `.eml` for each team.

## Required Layout

At the top level, this repo is organized by region:

```text
<region>/
  <team-number>-<team-name>/
```

Each team directory must look like this:

```text
<region>/
  <team-number>-<team-name>/
    email.txt
    part_one.stl
    part_two.stl
    part_one/
      .render.tsv
      90.png
      180.png
      270.png
      360.png
    part_two/
      .render.tsv
      90.png
      180.png
      270.png
      360.png
    receipt-<team-number>.eml
```

## Naming Rules

- Region folders can be named however you want. This repo already uses names like `Oklahoma` and `New_England`.
- Team folders must be named `<team-number>-<team-name>`.
- `compose.py` parses the team number and team name from the folder name, so the dash matters.
- `email.txt` is required and should contain exactly the recipient email address.
- STL files must live directly in the team folder.
- Render folders must match each STL stem exactly. Example: `8_Tooth.stl` renders into `8_Tooth/`.
- The receipt file defaults to `receipt-<team-number>.eml`.

## Scripts

### `clean_hubspot_dl_names.sh`

Normalizes downloaded STL filenames.

- If a HubSpot-style filename ends with `-stl_file-<part name>-<id>.stl`, it strips the prefix and suffix.
- Spaces are converted to underscores.
- Files that already look clean are skipped.

Examples:

```sh
./clean_hubspot_dl_names.sh path/to/file.stl
./clean_hubspot_dl_names.sh --dry-run path/to/file.stl
./clean_hubspot_dl_names.sh --force path/to/file.stl
```

### `render.py`

Renders each STL in one team directory into PNG previews using Blender's Python environment.

Defaults:

- Angles: `90 180 270 360`
- Image size: `480x480`
- Output location: the same team directory

`compose.py` expects the `270.png` render for every part by default, so don't skip that angle unless you also change the compose step.

Examples:

```sh
blender --background --python render.py -- Oklahoma/11-KIPR
blender --background --python render.py -- Oklahoma/11-KIPR --dry-run
blender --background --python render.py -- Oklahoma/11-KIPR --force
```

### `compose.py`

Builds a receipt email for one team and writes it as an `.eml` file.

It:

- reads the recipient from `email.txt`
- reads all `*.stl` files in the team folder
- pulls the matching rendered image for each part
- embeds those images into the email
- writes `receipt-<team-number>.eml` unless `--output` is provided

Examples:

```sh
python compose.py Oklahoma/11-KIPR
python compose.py Oklahoma/11-KIPR --dry-run
python compose.py Oklahoma/11-KIPR --force
```

## Workflow

### 1. Create the region folder

Drop raw submission files into a region directory, with one team folder per team.

If you keep a roster file like `teams.tsv`, treat it as reference only. The scripts do not read it.

### 2. Clean STL filenames

Run the cleanup script on downloaded STL files so the part names are stable and readable.

For a whole region:

```sh
cd Oklahoma
fd -e stl -x ../clean_hubspot_dl_names.sh
```

Preview only:

```sh
cd Oklahoma
fd -e stl -x ../clean_hubspot_dl_names.sh --dry-run
```

### 3. Render previews

Run Blender once per team directory.

For a whole region:

```sh
cd Oklahoma
fd -td -d 1 . -x blender --background --python ../render.py -- {}
```

The renderer skips up-to-date outputs and tracks the expected render state in `.render.tsv` inside each part folder.

### 4. Generate receipts

Compose one `.eml` per team after renders are in place.

For one team:

```sh
python compose.py Oklahoma/11-KIPR
```

For a whole region:

```sh
cd Oklahoma
fd -td -d 1 . -x python ../compose.py {}
```

Open the generated `.eml` files in your mail client, inspect them, then send.

## Requirements

- Bash for `clean_hubspot_dl_names.sh`
- Python 3 for `compose.py`
- Blender with `bpy` available for `render.py`

## Failure Modes

- Team folder missing the dash format: `compose.py` exits.
- Missing `email.txt`: `compose.py` exits.
- No STL files in a team folder: `render.py` and `compose.py` exit.
- Missing render image for a part: `compose.py` exits.
- Filename cleanup collision: `clean_hubspot_dl_names.sh` exits unless `--force` is used.

