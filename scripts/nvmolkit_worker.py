#!/usr/bin/env python3
"""Fixed nvMolKit GPU operations. Receives one validated JSON request on stdin."""
import json
import sys


def run(request):
    from rdkit import Chem
    from nvmolkit.fingerprints import MorganFingerprintGenerator
    import nvmolkit
    smiles = request["smiles"]
    mols = [Chem.MolFromSmiles(value) for value in smiles]
    if any(mol is None for mol in mols):
        raise ValueError("invalid SMILES")
    operation = request["operation"]
    base = {"operation":operation,"smiles":smiles,"nvmolkit_version":nvmolkit.__version__,
            "evidence":"computed_gpu_result_not_experimental_validation"}
    if operation == "conformers":
        from rdkit.Chem.rdDistGeom import ETKDGv3
        from nvmolkit.embedMolecules import EmbedMolecules
        mols = [Chem.AddHs(mol) for mol in mols]
        params = ETKDGv3(); params.useRandomCoords = True
        params.randomSeed = request.get("seed", 42)
        EmbedMolecules(mols, params, confsPerMolecule=request.get("conformers_per_molecule", 1),
                       maxIterations=-1)
        base["molblocks"] = [[Chem.MolToMolBlock(mol,confId=conf.GetId())
                              for conf in mol.GetConformers()] for mol in mols]
        return base
    fp = MorganFingerprintGenerator(radius=2, fpSize=1024).GetFingerprints(mols)
    if operation == "fingerprints":
        base["radius"] = 2; base["bits"] = 1024
        base["packed_uint32"] = fp.numpy().tolist()
    elif operation == "similarity":
        from nvmolkit.similarity import crossTanimotoSimilarity
        base["metric"] = "tanimoto"
        base["matrix"] = crossTanimotoSimilarity(fp).numpy().tolist()
    elif operation == "cluster":
        from nvmolkit.clustering import fused_butina
        labels, centroids = fused_butina(fp, cutoff=request["cutoff"], return_centroids=True)
        base["method"] = "gpu_fused_butina"
        base["cutoff"] = request["cutoff"]
        base["labels"] = labels.numpy().tolist()
        base["centroids"] = centroids.numpy().tolist()
    else:
        raise ValueError("unsupported nvMolKit operation")
    return base


def main():
    payload = sys.stdin.buffer.read(65537)
    if len(payload) > 65536: raise ValueError("input too large")
    result = run(json.loads(payload))
    encoded = json.dumps(result,allow_nan=False)
    if len(encoded.encode()) > 8*1024*1024: raise ValueError("result too large")
    print(encoded)


if __name__ == "__main__": main()
