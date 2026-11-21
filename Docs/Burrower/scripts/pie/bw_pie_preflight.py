# bw_pie_preflight.py - inbox script: the read-only checks of bw_pie_test.py (map, classes, settings, BP_Burrower defaults,
# GameMode class info, player debug death, play settings, memory, TEMP actors, log). Changes nothing, does not start PIE.
BW_PREFLIGHT_ONLY = True
exec(compile(open('/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/pie/bw_pie_test.py').read(), 'bw_pie_test.py', 'exec'), globals())
