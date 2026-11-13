# Explode to Points (IngeTrazo Extension)

A simple IngeTrazo extension that converts a selected shape into **selectable points** (one point per unique vertex).

Example: a selected rectangle becomes **4 selectable points** (one at each corner).

## Features

- Creates one selectable point marker per unique vertex from the selection
- Works with selected vertices, edges, faces, and groups/objects
- Option to **delete** or **keep** the original selected object(s)
- Single undo step (`Ctrl+Z`)

  <img width="703" height="308" alt="Points" src="https://github.com/user-attachments/assets/572b8532-9c78-46ef-b899-eb610e1c7a68" />


## Installation

1. Copy `explode_to_points.py` to the IngeTrazo plugins folder (**Extensions → Open plugins folder**).
2. Restart IngeTrazo.

## Usage

1. Select a shape/object.
2. Go to **Extensions → Explode to Points...**
3. Choose whether to **Delete original selected object(s)** (unchecked = keep original).
4. Click **Create Points**.

## Configuration

To change the marker size, edit `POINT_MARKER_SIZE` in `explode_to_points.py` (default: `0.02` m).

## Notes

- Original-object deletion is best-effort depending on selection/context.

