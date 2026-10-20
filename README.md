# Simple Prop Attach

A lightweight Blender 5.2 add-on built to eliminate the tedious manual workflow of re-attaching character parts, accessories, and clothing after making root proportion or rig modifications.

> **Disclosure:** This short Python script is 100% AI-generated and human-tested.  (Yes, I know. Less coding for now and more modeling)

## Why This Was Made

This tool was built for my personal workflow to remove the tedium of modifying character proportions or updating a rig. Re-attaching every accessory manually—clearing parents, wiping vertex groups, re-parenting, adding Data Transfer modifiers, moving them to the top, and applying them—is incredibly repetitive.

I made **Simple Prop Attach** to automate this entire sequence into a single click for multiple selected objects at once, and I'm sharing it here in case it helps anyone else facing the same workflow bottleneck.

## Features

* **Batch Processing:** Parent and transfer weights to multiple accessories simultaneously.
* **Transform Preservation:** Keeps accessories in their exact world positions without shifting.
* **Dual Attachment Modes:**
  * **Smooth Deform:** Automatic Data Transfer setup for flexible items (clothing, hair, soft straps).
  * **Rigid Attachment:** Three strategies for hard props (pouches, holsters, armor) to prevent volume collapse and clipping:
    * `Create Socket Bone` *(Recommended)*: Generates a constrained socket bone to eliminate both shrinking and floating.
    * `Weight to Dominant Bone`: 100% weight to the nearest bone (creates no new bones).
    * `Weight to Surface Blend`: Uniform multi-bone weight blending across all vertices (creates no new bones).

## Quick Start

1. Install the script via **Edit > Preferences > Add-ons**.
2. Open the 3D Viewport **N-Panel** (`N`) $\rightarrow$ **Rigging** tab.
3. Select your **Target Rig** and **Body Mesh**.
4. Select your accessory mesh(es), choose your attachment mode, and click **Conform & Attach to Rig**.

## Compatibility

* **Blender Version:** 5.2
* **Author:** ccccharlesjb (AI-generated)
