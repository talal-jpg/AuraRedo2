# Prop modelling scripts (helm wheel, cannon, front turret)

Headless Blender 4.5 scripts that build the props before rigging (copies of
`/mnt/new_partition/BlenderProjects/StylizedAirship/rig/scripts/`; `../props_all.sh` runs them in order):

* `model_helm.py` - pirate steering wheel + pedestal -> `rig/props/Helm.blend` (v3, round 2: wheel 1.40 m across, axle
  1.00 m, sized for the 141.6 cm mech)
* `model_cannon.py` - deck cannon on a 4-wheel carriage -> `rig/props/Cannon.blend` (v3, round 2: bore radius 0.22 m)
* `model_turret.py` - round 2: front machine-gun turret, yaw part `Turret_Base` + pitch part `Turret_Gun` + the
  `Turret_Muzzle` empty -> `rig/props/Turret.blend` (+ `Turret_report.json`: pitch clearance, gunner clearance)
* `uv_layouts.py` - inspection only: rasterises the cannon meshes' UV layouts to `rig/renders/props/uv/`
* `bake_props_comic.py` - assembles Helm + Cannon + Turret into `rig/props/AirshipProps.blend`, packs one overlap-free
  atlas for all of them and bakes the comic-ink line and mask maps into `T_AirshipProps_ComicLines` / `ComicMask`
  (image maps only, no procedural material reaches Unreal)

`../rig_build.py` reads the helm and cannon from `rig/props/AirshipProps.blend`, `../export_turret.py` the turret; the
.blend files are not in the repo, re-run these scripts to recreate them.
