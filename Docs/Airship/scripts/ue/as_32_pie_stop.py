# as_32_pie_stop.py - inbox: ends an active as_30 run (restores the in-memory settings, stops its own PIE, removes TEMP_AS_Capture).
AS31_STOP = True
exec(open('/mnt/new_partition/UnrealProjects/_AirshipWork/Docs/Airship/scripts/ue/as_31_pie_status.py').read())
AS31_STOP = False
