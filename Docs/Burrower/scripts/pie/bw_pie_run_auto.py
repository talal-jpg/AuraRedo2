# bw_pie_run_auto.py - inbox script: the PIE test with the automatic first spawn (bw_pie_config_auto.json: bEnabled on,
# FirstSpawnDelay 6 s) instead of Aura.Burrower.SpawnNow. Everything else as bw_pie_test.py.
BW_CONFIG = '/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/pie/bw_pie_config_auto.json'
exec(compile(open('/mnt/new_partition/UnrealProjects/_BurrowerWork/Docs/Burrower/scripts/pie/bw_pie_test.py').read(), 'bw_pie_test.py', 'exec'), globals())
