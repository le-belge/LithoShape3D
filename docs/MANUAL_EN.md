# LithoShape3D Manual (v0.5.0)

Complete feature guide, explained simply. French version:
[`MANUAL_FR.md`](MANUAL_FR.md).

> The app's interface is currently French-only. Button and menu labels
> below are quoted exactly as they appear on screen, with the English
> explanation next to them.

## Overview

LithoShape3D takes a photo, computes a variable thickness from the
brightness of every pixel, and outputs a 3D-printable file — a lithophane
that reveals the image once backlit. It also handles non-rectangular
shapes, multiple zones combined on a single piece, colored backlit
inserts, and multi-material export for AMS-equipped printers.

## 1. Source image

Everything starts with a photo. The darker a spot, the thicker the
printed material there.

- **"Ouvrir image..."** (Open image) — loads a photo (JPG, PNG...).
- **"Retirer le fond..."** (Remove background) — one-click automatic
  subject cutout.
- **"Retirer le fond (précision manuelle)..."** (Manual background
  removal) *(macOS)* — AI-assisted cutout where you click the subject
  yourself to keep or exclude it.
- **"Cadrer la photo..."** (Crop photo) — crops/zooms the photo inside the
  chosen shape, without touching the original file.
- **Brightness / Contrast / Invert** — fine-tune the render before
  generating. *Invert* swaps light and dark areas.

> **Tip**: a well-contrasted photo with a sharp subject always produces
> better relief than a flat or overexposed image.

## 2. Shapes (Shape Composer)

A piece doesn't have to be a rectangle:

- **Rectangle / Circle / Oval** — basic shapes.
- **Heart / Star** — ready-made decorative shapes.
- **Text** — the piece takes the silhouette of a word or short text,
  movable with the arrow keys.
- **Image / SVG** — use a logo or custom silhouette as the piece's
  outline.
- **Border** — thickness setting to add a frame around the shape.

## 3. Zones & masks

A piece can combine several independent zones, each with its own portion
of the image, its own role, and optionally its own color.

- **"+ Zone" / "Supprimer"** (Add / Delete) — a base "Lithophanie" zone is
  always created automatically when an image is opened.
- **"Éditer le masque..."** (Edit mask) — paint with a brush/eraser, with
  fill, clear, invert and full undo/redo history.
- **AI segmentation** *(macOS)* — a single click on the subject generates
  a precise mask automatically.
- **Reorder zones** — drag a zone in the list to change composition
  order, useful when two zones overlap.

## 4. Geometry & relief

- **Width / Min & max thickness** — real-world dimensions in millimeters.
  Height automatically follows the photo's aspect ratio.
- **Resolution** — level of detail (mm per pixel).
- **Standard / Fine / Draft presets** — ready-made settings.
- **Zone role** — `ReliefMode` (Lithophanie / Relief-amplitude / Solide)
  and `CompositionMode` (Base / Add / Replace).

## 5. Materials & color

Giving a zone a color never changes its relief — the two are deliberately
independent.

- **"Matériau seul"** (Material only) — same relief, different filament
  (useful for AMS).
- **Backlight Insert** *(prototype)* — a cavity behind a thin white skin,
  filled with a colored insert. Settings: skin thickness, insert
  thickness, XY clearance.

> **Still experimental**: Backlight Insert works in the software but
> hasn't been validated across every printer yet.

## 6. Print support

- **None** — flat export, for a frame or a lightbox.
- **Flat / reinforced foot** — a base printed with the piece (reinforced
  adds ribs for stability).

## 7. 3D preview

- **"Générer"** (Generate) — computes the 3D mesh; flagged "stale" if a
  setting changes afterwards.
- **"Zone active" / "Composition"** — selected zone alone, or the final
  piece with all zones combined.
- **"Backlight couleur"** — simulates the backlit look, inserts in their
  true color.
- **Front / Isometric / Reset views** — standard camera navigation.

## 8. Export

- **"Exporter STL..."** — a single file, for a single-material/color
  piece.
- **"Exporter multi-matériaux..."** — a 3MF file (or several STLs as a
  fallback) for a multi-color/insert piece.

## 9. Themes

**"Thème"** menu — your choice is remembered next launch.

- **Dark — Carbon Glow** (default)
- **Light — Litho Lab**

## 10. License

Import, cropping, zones and the 3D preview are free to use. Exporting a
printable file (STL/3MF) requires a license — menu
**"Aide" → "Licence..."** to enter the key you received at purchase.

## Glossary

| Term | Definition |
|---|---|
| Lithophane | A thin relief that reveals an image when lit from behind. |
| Mask | A painted area defining which part of the image belongs to a zone. |
| Mesh | The computed 3D model, before export. |
| Backlight Insert | A colored insert hidden behind a thin white skin, for color backlighting. |
| XY clearance | A small gap left between two parts so they fit together without forcing. |
| AMS | Bambu Lab's multi-filament system, enabling multi-color printing in one pass. |
