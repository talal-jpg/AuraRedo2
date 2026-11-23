# Prop modelling scripts (helm wheel + cannon)

Headless Blender 4.5 scripts that built the props before rigging (copies of
`/mnt/new_partition/BlenderProjects/StylizedAirship/rig/scripts/`):

* `model_helm.py` - pirate steering wheel + pedestal -> `rig/props/Helm.blend`
* `model_cannon.py` - deck cannon on a 4-wheel carriage -> `rig/props/Cannon.blend`
* `uv_layouts.py` - overlap-free UV islands on the shared prop atlas
* `bake_props_comic.py` - bakes the comic-ink line and mask maps into `T_AirshipProps_ComicLines` / `ComicMask`
  (image maps only, no procedural material reaches Unreal) -> `rig/props/AirshipProps.blend`

`../rig_build.py` reads `rig/props/AirshipProps.blend`, which is not in the repo; re-run these scripts to recreate it.
