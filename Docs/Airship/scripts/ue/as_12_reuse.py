# as_12_reuse.py - rebuild CR_Airship in place (MODE 'reuse': every node removed and rebuilt, variables kept). Use it
# when delete-and-recreate is refused (the asset is in use, e.g. by rig test instances or ABP_Airship).
# Run: inbox.sh 12r Docs/Airship/scripts/ue/as_12_reuse.py 900
AS12_MODE = 'reuse'
exec(open('/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_12_control_rig.py').read())
