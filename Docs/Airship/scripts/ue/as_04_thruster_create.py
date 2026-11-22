# as_04_thruster_create.py - step 1 of NS_AirshipThruster: empty system + 3 template emitters (configured by as_04b).
#   JetShell (outer orange flame, SM_Thruster mesh), JetCore (inner hot core, mesh): SingleLoopingParticle (one persistent particle)
#   Puffs (comic smoke puffs from the jet tail, world space): Fountain
AS_FX = {'name': 'NS_AirshipThruster', 'recreate': globals().get('AS_RECREATE', False), 'emitters': [
    ('JetShell', '/Niagara/DefaultAssets/Templates/Emitters/SingleLoopingParticle.SingleLoopingParticle'),
    ('JetCore', '/Niagara/DefaultAssets/Templates/Emitters/SingleLoopingParticle.SingleLoopingParticle'),
    ('Puffs', '/Niagara/DefaultAssets/Templates/Emitters/Fountain.Fountain')]}
import os, unreal
exec(open(os.path.join(os.path.abspath(unreal.Paths.project_dir()), 'Docs/Airship/scripts/ue/as_04a_fx_create.py')).read())
AS_FX = None
