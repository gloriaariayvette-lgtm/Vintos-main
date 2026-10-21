"""Bounded invocation of the installed native instruments on retained Lab artifacts."""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import uuid

TOOLS = Path(os.environ.get('CHEM_LAB_TOOLS', '~/.vintos/tools/chemistry-lab')).expanduser()
OPERATIONS = {'protein_mpnn':'sequence.design', 'rfdiffusion':'backbone.generate', 'openmm':'structure.relax_ca'}


def menu():
    return {'protein_mpnn':{'operation':'sequence.design','files':['sourced PDB artifact'], 'samples':'1..2'},
            'rfdiffusion':{'operation':'backbone.generate','files':[], 'length':'10..80','steps':'2..10'},
            'openmm':{'operation':'structure.relax_ca','files':['sourced PDB artifact'],'steps':'1..50',
                      'model':'C-alpha elastic network; energies are not atomistic binding energies'}}


def _integer(request, name, default, low, high):
    value = request.get(name, default)
    if type(value) is not int or not low <= value <= high: raise ValueError('invalid '+name)
    return value


def run(request, *, runner=subprocess.run):
    import lab_instruments as instruments
    skill = request.get('skill')
    if request.get('operation') != OPERATIONS.get(skill): raise ValueError('unknown native operation')
    files = request.get('files') or []
    allowed = set(instruments.artifacts('structure', 50))
    if skill != 'rfdiffusion' and (len(files) != 1 or files[0] not in allowed or not files[0].endswith('.pdb')):
        raise ValueError('one retained PDB artifact required')
    if skill == 'rfdiffusion' and files: raise ValueError('this bounded backbone operation takes no files')
    paths = [(instruments.LAB/f).resolve() for f in files]
    if any(not p.is_relative_to(instruments.ARTIFACTS.resolve()) or p.is_symlink() for p in paths):
        raise ValueError('native inputs must remain inside Lab artifacts')
    output = instruments.ARTIFACTS/skill/uuid.uuid4().hex[:16]
    output.mkdir(parents=True)
    if skill == 'protein_mpnn':
        root = Path(os.environ.get('CHEM_LAB_PROTEINMPNN_ROOT','~/protein-tools/ProteinMPNN')).expanduser()
        argv = [str(TOOLS/'proteinmpnn/bin/python'), str(root/'protein_mpnn_run.py'),
                '--pdb_path', str(paths[0]), '--out_folder', str(output), '--num_seq_per_target',
                str(_integer(request,'samples',1,1,2)), '--batch_size','1','--sampling_temp','0.1','--seed','37']
    elif skill == 'rfdiffusion':
        checkpoint = os.environ.get('CHEM_LAB_RFD3_CHECKPOINT', str(TOOLS/'checkpoints/foundry/rfd3_latest.ckpt'))
        argv = [str(TOOLS/'foundry/bin/rfd3'),'design','out_dir='+str(output),'inputs=null',
                '+specification.length='+str(_integer(request,'length',40,10,80)), 'ckpt_path='+checkpoint,
                'diffusion_batch_size=1','n_batches=1','inference_sampler.num_timesteps='+str(_integer(request,'steps',10,2,10)),
                'low_memory_mode=True','skip_existing=False']
    else:
        argv = [str(TOOLS/'openmm/bin/python'), __file__, '--openmm',str(paths[0]),str(output),
                str(_integer(request,'steps',20,1,50))]
    done = runner(argv, capture_output=True, text=True, timeout=600, check=False,
                  env={**os.environ, 'TMPDIR':str(output), 'PYTHONDONTWRITEBYTECODE':'1'})
    if done.returncode:
        raise RuntimeError('native '+skill+' failed: '+done.stderr[-300:])
    artifacts = [p for p in output.rglob('*') if p.is_file()]
    expected = '.fa' if skill == 'protein_mpnn' else '.cif.gz' if skill == 'rfdiffusion' else '.json'
    if not any(p.name.endswith(expected) for p in artifacts): raise RuntimeError('native result artifact absent')
    return {'ok':True,'instrument':skill,'operation':OPERATIONS[skill],
            'inputs':[{'file':str(p.relative_to(instruments.LAB)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in paths],
            'files':[{'file':str(p.relative_to(instruments.LAB)), 'sha256':hashlib.sha256(p.read_bytes()).hexdigest()} for p in artifacts],
            'result':json.loads((output/'result.json').read_text()) if skill == 'openmm' else {},
            'truth_status':'computed_model_output_not_biological_validation'}


def _openmm(pdb, folder, steps):
    import openmm as mm
    from openmm import unit as u
    positions=[];residues=[]
    for line in Path(pdb).read_text().splitlines():
        if line.startswith('ATOM') and line[12:16].strip()=='CA' and line[16:17] in (' ','A'):
            residues.append((line[21:22],int(line[22:26])))
            positions.append(tuple(float(line[i:i+8])*0.1 for i in (30,38,46)))
    if not 2 <= len(positions) <= 1000: raise ValueError('2..1000 C-alpha atoms required')
    system=mm.System(); bonds=mm.HarmonicBondForce()
    for _ in positions: system.addParticle(12.0)
    for i in range(len(positions)-1):
        if residues[i+1] == (residues[i][0],residues[i][1]+1):bonds.addBond(i,i+1,0.38,1000.0)
    if bonds.getNumBonds()==0:raise ValueError('no consecutive C-alpha residues')
    system.addForce(bonds);integrator=mm.VerletIntegrator(0.001*u.picoseconds)
    context=mm.Context(system,integrator,mm.Platform.getPlatformByName('Reference'));context.setPositions(positions)
    before=context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(u.kilojoule_per_mole)
    mm.LocalEnergyMinimizer.minimize(context,maxIterations=int(steps))
    after=context.getState(getEnergy=True).getPotentialEnergy().value_in_unit(u.kilojoule_per_mole)
    Path(folder,'result.json').write_text(json.dumps({'ca_atoms':len(positions),'energy_before_kj_mol':before,
        'energy_after_kj_mol':after,'model':'C-alpha harmonic consecutive-neighbour model, no atomistic or binding claim'}))


if __name__=='__main__' and sys.argv[1:2]==['--openmm']:
    _openmm(*sys.argv[2:])
