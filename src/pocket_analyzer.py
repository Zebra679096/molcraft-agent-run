"""Protein Binding Pocket Analyzer for AI Drug Discovery Competition.

Analyzes the target protein's binding site at the given docking center,
extracts pharmacophore features, and provides ligand design recommendations.

Key insight from competition: "protein cavity residue analysis and molecular
conformation analysis are missing" — this module addresses that gap.
"""
import os
import math
import sys
from collections import defaultdict

# ─── Configuration ──────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(PROJECT_ROOT, "data")
PDB_PATH = os.path.join(DATA_DIR, "target.pdb")

DOCKING_CENTER = [18.5, -2.0, 22.0]  # 优化后（H008: 空洞分析+AB测试）
POCKET_RADIUS = 10.0   # Å – residues within this distance from center
INNER_RADIUS = 5.0     # Å – core pocket residues

# ─── Amino Acid Property Tables ─────────────────────────────────────────────
HYDROPHOBIC = {"ALA", "VAL", "LEU", "ILE", "MET", "PHE", "TRP", "PRO"}
AROMATIC = {"PHE", "TYR", "TRP", "HIS"}
POSITIVELY_CHARGED = {"ARG", "LYS", "HIS"}   # HIS can be + at physiological pH
NEGATIVELY_CHARGED = {"ASP", "GLU"}
POLAR_UNCHARGED = {"SER", "THR", "ASN", "GLN", "TYR", "CYS"}
SPECIAL = {"GLY", "PRO", "CYS"}

# H-bond donor/acceptor atoms by residue
HBOND_DONORS = {
    "ARG": ["NE", "NH1", "NH2"],
    "LYS": ["NZ"],
    "ASN": ["ND2"],
    "GLN": ["NE2"],
    "HIS": ["ND1", "NE2"],
    "SER": ["OG"],
    "THR": ["OG1"],
    "TYR": ["OH"],
    "TRP": ["NE1"],
    "CYS": ["SG"],
    # Backbone
    "_BACKBONE_DONOR": ["N"],   # amide NH
}

HBOND_ACCEPTORS = {
    "ARG": ["O"],       # backbone only
    "LYS": ["O"],
    "ASP": ["OD1", "OD2"],
    "GLU": ["OE1", "OE2"],
    "ASN": ["OD1"],
    "GLN": ["OE1"],
    "HIS": ["ND1", "NE2"],  # can be both donor and acceptor
    "SER": ["OG"],
    "THR": ["OG1"],
    "TYR": ["OH"],
    "TRP": ["NE1"],
    "CYS": ["O"],       # backbone
    "MET": ["SD"],      # weak acceptor
    # Backbone
    "_BACKBONE_ACCEPTOR": ["O"],  # carbonyl O
}

# Van der Waals radii for key atoms (Å)
VDW_RADII = {
    "H": 1.20, "C": 1.70, "N": 1.55, "O": 1.52, "S": 1.80, "P": 1.80,
    "F": 1.47, "CL": 1.75, "BR": 1.85, "I": 1.98, "FE": 2.00, "ZN": 1.39,
    "MG": 1.73, "CA": 2.31, "MN": 2.14, "CU": 1.40, "NA": 2.27,
}

# Aromatic ring centroid atom names per residue type
AROMATIC_RING_ATOMS = {
    "PHE": [["CG", "CD1", "CD2", "CE1", "CE2", "CZ"]],
    "TYR": [["CG", "CD1", "CD2", "CE1", "CE2", "CZ"]],
    "TRP": [["CG", "CD1", "CD2", "NE1", "CE2"], ["CE2", "CD2", "CE3", "CZ2", "CZ3", "CH2"]],
    "HIS": [["CG", "ND1", "CD2", "CE1", "NE2"]],
}


# ─── PDB Parsing ────────────────────────────────────────────────────────────

def parse_pdb(filepath):
    """Parse a PDB file, return list of atom dicts."""
    atoms = []
    with open(filepath, "r") as f:
        for line in f:
            if line.startswith("ATOM") or line.startswith("HETATM"):
                atom = {
                    "record": line[0:6].strip(),
                    "serial": int(line[6:11].strip()),
                    "name": line[12:16].strip(),
                    "altloc": line[16].strip(),
                    "resname": line[17:20].strip(),
                    "chain": line[21].strip(),
                    "resnum": int(line[22:26].strip()),
                    "icode": line[26].strip(),
                    "x": float(line[30:38].strip()),
                    "y": float(line[38:46].strip()),
                    "z": float(line[46:54].strip()),
                    "occupancy": float(line[54:60].strip()) if len(line) > 54 else 1.0,
                    "bfactor": float(line[60:66].strip()) if len(line) > 60 else 0.0,
                    "element": line[76:78].strip() if len(line) > 76 else "",
                }
                atoms.append(atom)
    return atoms


# ─── Distance & Geometry ────────────────────────────────────────────────────

def dist(p1, p2):
    """Euclidean distance between two 3D points."""
    return math.sqrt(sum((a - b) ** 2 for a, b in zip(p1, p2)))


def centroid(points):
    """Compute centroid of a list of 3D points."""
    n = len(points)
    return [sum(p[i] for p in points) / n for i in range(3)]


# ─── Pocket Analysis ────────────────────────────────────────────────────────

class PocketAnalyzer:
    """Comprehensive protein binding pocket analyzer."""

    def __init__(self, pdb_path, center, pocket_radius=10.0, inner_radius=5.0):
        self.pdb_path = pdb_path
        self.center = center
        self.pocket_radius = pocket_radius
        self.inner_radius = inner_radius
        self.atoms = parse_pdb(pdb_path)
        self.results = {}

    def run_full_analysis(self):
        """Run all analyses and return comprehensive results."""
        print("=" * 70)
        print("PROTEIN BINDING POCKET ANALYSIS")
        print("=" * 70)
        print(f"\nPDB file: {self.pdb_path}")
        print(f"Docking center: {self.center}")
        print(f"Pocket radius: {self.pocket_radius} Å")
        print(f"Inner radius: {self.inner_radius} Å")
        print(f"Total atoms in PDB: {len(self.atoms)}")

        self._identify_pocket_residues()
        self._classify_residues()
        self._analyze_hbonds()
        self._analyze_aromatic()
        self._analyze_charged()
        self._detect_metals_waters()
        self._analyze_pocket_shape()
        self._pharmacophore_analysis()
        self._ligand_recommendations()

        return self.results

    def _identify_pocket_residues(self):
        """Find all residues within pocket_radius of the docking center."""
        print("\n" + "=" * 70)
        print("1. POCKET RESIDUE IDENTIFICATION")
        print("=" * 70)

        residue_atoms = defaultdict(list)
        for atom in self.atoms:
            key = (atom["resname"], atom["chain"], atom["resnum"])
            d = dist([atom["x"], atom["y"], atom["z"]], self.center)
            residue_atoms[key].append((atom, d))

        # Find residues with at least one atom within pocket_radius
        self.pocket_residues = {}
        self.inner_residues = {}
        self.residue_min_dist = {}

        for key, atom_list in residue_atoms.items():
            min_d = min(d for _, d in atom_list)
            self.residue_min_dist[key] = min_d
            if min_d <= self.pocket_radius:
                self.pocket_residues[key] = atom_list
            if min_d <= self.inner_radius:
                self.inner_residues[key] = atom_list

        print(f"\nResidues within {self.pocket_radius} Å of docking center: {len(self.pocket_residues)}")
        print(f"Residues within {self.inner_radius} Å (core pocket): {len(self.inner_residues)}")

        # Sort by distance and display
        sorted_res = sorted(self.pocket_residues.items(), key=lambda x: self.residue_min_dist[x[0]])

        print(f"\n{'Residue':<12} {'Chain':<6} {'Min Dist (Å)':<14} {'CA Dist (Å)':<14} {'Zone'}")
        print("-" * 60)
        for key, atom_list in sorted_res:
            resname, chain, resnum = key
            min_d = self.residue_min_dist[key]
            zone = "CORE" if min_d <= self.inner_radius else "OUTER"

            # Find CA atom distance
            ca_dist = "N/A"
            for atom, d in atom_list:
                if atom["name"] == "CA":
                    ca_dist = f"{d:.2f}"
                    break

            print(f"{resname:>3} {resnum:<6} {chain:<6} {min_d:<14.2f} {ca_dist:<14} {zone}")

        self.results["pocket_residues"] = {
            f"{k[0]}_{k[1]}_{k[2]}": {
                "min_dist": self.residue_min_dist[k],
                "zone": "CORE" if self.residue_min_dist[k] <= self.inner_radius else "OUTER",
                "n_atoms": len(v)
            }
            for k, v in self.pocket_residues.items()
        }

    def _classify_residues(self):
        """Classify pocket residues by hydrophobicity and type."""
        print("\n" + "=" * 70)
        print("2. RESIDUE CLASSIFICATION")
        print("=" * 70)

        hydrophobic_res = []
        hydrophilic_res = []
        aromatic_res = []
        charged_pos = []
        charged_neg = []
        polar_res = []
        special_res = []

        for key in self.pocket_residues:
            resname = key[0]
            min_d = self.residue_min_dist[key]
            label = f"{resname}{key[2]}"

            if resname in HYDROPHOBIC:
                hydrophobic_res.append((label, min_d))
            if resname in AROMATIC:
                aromatic_res.append((label, min_d))
            if resname in POSITIVELY_CHARGED:
                charged_pos.append((label, min_d))
            if resname in NEGATIVELY_CHARGED:
                charged_neg.append((label, min_d))
            if resname in POLAR_UNCHARGED:
                polar_res.append((label, min_d))
            if resname not in HYDROPHOBIC and resname not in POLAR_UNCHARGED and resname not in POSITIVELY_CHARGED and resname not in NEGATIVELY_CHARGED:
                # GLY, PRO, etc.
                hydrophilic_res.append((label, min_d))
            if resname in SPECIAL:
                special_res.append((label, min_d))

        # A residue can be both hydrophobic and polar (like TYR)
        # Also count hydrophilic = all non-hydrophobic residues
        all_hydrophobic = set()
        all_hydrophilic = set()
        for key in self.pocket_residues:
            resname = key[0]
            label = f"{resname}{key[2]}"
            if resname in HYDROPHOBIC:
                all_hydrophobic.add(label)
            else:
                all_hydrophilic.add(label)

        print(f"\nHydrophobic residues ({len(all_hydrophobic)}):")
        for label, d in sorted(hydrophobic_res, key=lambda x: x[1]):
            print(f"  {label:<10} ({d:.2f} Å)")

        print(f"\nHydrophilic residues ({len(all_hydrophilic)}):")
        for label, d in sorted(hydrophilic_res, key=lambda x: x[1]):
            print(f"  {label:<10} ({d:.2f} Å)")

        print(f"\nAromatic residues ({len(aromatic_res)}):")
        for label, d in sorted(aromatic_res, key=lambda x: x[1]):
            print(f"  {label:<10} ({d:.2f} Å)")

        print(f"\nPositively charged ({len(charged_pos)}):")
        for label, d in sorted(charged_pos, key=lambda x: x[1]):
            print(f"  {label:<10} ({d:.2f} Å)")

        print(f"\nNegatively charged ({len(charged_neg)}):")
        for label, d in sorted(charged_neg, key=lambda x: x[1]):
            print(f"  {label:<10} ({d:.2f} Å)")

        print(f"\nPolar uncharged ({len(polar_res)}):")
        for label, d in sorted(polar_res, key=lambda x: x[1]):
            print(f"  {label:<10} ({d:.2f} Å)")

        # Compute hydropathy ratio
        n_hydrophobic = len(all_hydrophobic)
        n_total = len(self.pocket_residues)
        ratio = n_hydrophobic / n_total if n_total > 0 else 0

        print(f"\nHydropathy ratio: {n_hydrophobic}/{n_total} = {ratio:.1%}")
        if ratio > 0.5:
            print("  → POCKET IS HYDROPHOBIC-DOMINANT: Ligand should have significant hydrophobic character")
        else:
            print("  → POCKET IS HYDROPHILIC-DOMINANT: Ligand should have significant polar character")

        self.results["classification"] = {
            "hydrophobic": [l for l, _ in hydrophobic_res],
            "hydrophilic": list(all_hydrophilic),
            "aromatic": [l for l, _ in aromatic_res],
            "positive_charge": [l for l, _ in charged_pos],
            "negative_charge": [l for l, _ in charged_neg],
            "polar": [l for l, _ in polar_res],
            "hydropathy_ratio": ratio,
        }

    def _analyze_hbonds(self):
        """Identify key H-bond donors and acceptors in the pocket."""
        print("\n" + "=" * 70)
        print("3. HYDROGEN BOND DONORS AND ACCEPTORS")
        print("=" * 70)

        donors = []
        acceptors = []

        for key, atom_list in self.pocket_residues.items():
            resname, chain, resnum = key
            for atom, d in atom_list:
                atom_name = atom["name"]
                coord = [atom["x"], atom["y"], atom["z"]]
                d_to_center = dist(coord, self.center)

                # Check if this atom is a backbone H-bond participant
                if atom_name == "N" and resname != "PRO":  # backbone NH (donor)
                    donors.append({
                        "residue": f"{resname}{resnum}",
                        "atom": atom_name,
                        "type": "backbone",
                        "coord": coord,
                        "dist_to_center": d_to_center
                    })
                elif atom_name == "O" and atom["element"] != "S":  # backbone carbonyl O (acceptor)
                    acceptors.append({
                        "residue": f"{resname}{resnum}",
                        "atom": atom_name,
                        "type": "backbone",
                        "coord": coord,
                        "dist_to_center": d_to_center
                    })

                # Check side chain donors
                if resname in HBOND_DONORS and atom_name in HBOND_DONORS[resname]:
                    donors.append({
                        "residue": f"{resname}{resnum}",
                        "atom": atom_name,
                        "type": "sidechain",
                        "coord": coord,
                        "dist_to_center": d_to_center
                    })

                # Check side chain acceptors
                if resname in HBOND_ACCEPTORS and atom_name in HBOND_ACCEPTORS[resname]:
                    acceptors.append({
                        "residue": f"{resname}{resnum}",
                        "atom": atom_name,
                        "type": "sidechain",
                        "coord": coord,
                        "dist_to_center": d_to_center
                    })

        # Sort by distance to center
        donors.sort(key=lambda x: x["dist_to_center"])
        acceptors.sort(key=lambda x: x["dist_to_center"])

        print(f"\nH-bond DONORS ({len(donors)}):")
        print(f"{'Residue':<12} {'Atom':<6} {'Type':<12} {'Dist to Center (Å)'}")
        print("-" * 50)
        for d in donors:
            print(f"{d['residue']:<12} {d['atom']:<6} {d['type']:<12} {d['dist_to_center']:.2f}")

        print(f"\nH-bond ACCEPTORS ({len(acceptors)}):")
        print(f"{'Residue':<12} {'Atom':<6} {'Type':<12} {'Dist to Center (Å)'}")
        print("-" * 50)
        for a in acceptors:
            print(f"{a['residue']:<12} {a['atom']:<6} {a['type']:<12} {a['dist_to_center']:.2f}")

        # Key donors/acceptors (within 6 Å of center)
        key_donors = [d for d in donors if d["dist_to_center"] <= 6.0]
        key_acceptors = [a for a in acceptors if a["dist_to_center"] <= 6.0]

        print(f"\nKEY donors within 6 Å of center: {len(key_donors)}")
        print(f"KEY acceptors within 6 Å of center: {len(key_acceptors)}")

        self.results["hbond_donors"] = donors
        self.results["hbond_acceptors"] = acceptors
        self.results["key_donors"] = key_donors
        self.results["key_acceptors"] = key_acceptors

    def _analyze_aromatic(self):
        """Find aromatic residues capable of pi-stacking/pi-cation interactions."""
        print("\n" + "=" * 70)
        print("4. AROMATIC RESIDUES & PI-STACKING ANALYSIS")
        print("=" * 70)

        aromatic_interactions = []

        for key, atom_list in self.pocket_residues.items():
            resname = key[0]
            if resname not in AROMATIC_RING_ATOMS:
                continue

            # Get all atoms of this residue
            atom_dict = {}
            for atom, d in atom_list:
                atom_dict[atom["name"]] = [atom["x"], atom["y"], atom["z"]]

            # Compute ring centroids
            for ring_atom_names in AROMATIC_RING_ATOMS[resname]:
                ring_points = []
                for aname in ring_atom_names:
                    if aname in atom_dict:
                        ring_points.append(atom_dict[aname])

                if len(ring_points) >= 5:  # need at least 5 of 6 atoms
                    ring_center = centroid(ring_points)
                    d_to_pocket = dist(ring_center, self.center)

                    ring_info = {
                        "residue": f"{resname}{key[2]}",
                        "ring_atoms": ring_atom_names,
                        "centroid": ring_center,
                        "dist_to_center": d_to_pocket,
                    }
                    aromatic_interactions.append(ring_info)

        aromatic_interactions.sort(key=lambda x: x["dist_to_center"])

        print(f"\nAromatic rings in pocket ({len(aromatic_interactions)}):")
        for ai in aromatic_interactions:
            print(f"  {ai['residue']:<10} ring centroid at ({ai['centroid'][0]:.1f}, {ai['centroid'][1]:.1f}, {ai['centroid'][2]:.1f}) "
                  f"— {ai['dist_to_center']:.2f} Å from center")

        # Check for edge-to-face vs face-to-face geometry
        print("\nPi-stacking potential analysis:")
        for i, ai1 in enumerate(aromatic_interactions):
            for ai2 in aromatic_interactions[i + 1:]:
                d = dist(ai1["centroid"], ai2["centroid"])
                if d < 7.0:
                    print(f"  {ai1['residue']} ↔ {ai2['residue']}: centroid distance = {d:.2f} Å")
                    if d < 5.0:
                        print(f"    → STRONG pi-stacking possible (parallel displaced or sandwich)")
                    else:
                        print(f"    → Moderate pi-stacking / T-shaped interaction possible")

        self.results["aromatic_interactions"] = aromatic_interactions

    def _analyze_charged(self):
        """Analyze charged residues and electrostatic environment."""
        print("\n" + "=" * 70)
        print("5. CHARGED RESIDUE & ELECTROSTATIC ANALYSIS")
        print("=" * 70)

        charged_groups = []

        for key, atom_list in self.pocket_residues.items():
            resname = key[0]

            if resname in POSITIVELY_CHARGED:
                # Find charged atom
                for atom, d in atom_list:
                    if resname == "ARG" and atom["name"] in ("NH1", "NH2", "NE"):
                        charged_groups.append({
                            "residue": f"{resname}{key[2]}",
                            "atom": atom["name"],
                            "charge": "+1",
                            "coord": [atom["x"], atom["y"], atom["z"]],
                            "dist_to_center": dist([atom["x"], atom["y"], atom["z"]], self.center)
                        })
                    elif resname == "LYS" and atom["name"] == "NZ":
                        charged_groups.append({
                            "residue": f"{resname}{key[2]}",
                            "atom": atom["name"],
                            "charge": "+1",
                            "coord": [atom["x"], atom["y"], atom["z"]],
                            "dist_to_center": dist([atom["x"], atom["y"], atom["z"]], self.center)
                        })
                    elif resname == "HIS" and atom["name"] in ("ND1", "NE2"):
                        charged_groups.append({
                            "residue": f"{resname}{key[2]}",
                            "atom": atom["name"],
                            "charge": "+0.5",  # partially charged
                            "coord": [atom["x"], atom["y"], atom["z"]],
                            "dist_to_center": dist([atom["x"], atom["y"], atom["z"]], self.center)
                        })

            elif resname in NEGATIVELY_CHARGED:
                for atom, d in atom_list:
                    if resname == "ASP" and atom["name"] in ("OD1", "OD2"):
                        charged_groups.append({
                            "residue": f"{resname}{key[2]}",
                            "atom": atom["name"],
                            "charge": "-0.5",  # delocalized across both oxygens
                            "coord": [atom["x"], atom["y"], atom["z"]],
                            "dist_to_center": dist([atom["x"], atom["y"], atom["z"]], self.center)
                        })
                    elif resname == "GLU" and atom["name"] in ("OE1", "OE2"):
                        charged_groups.append({
                            "residue": f"{resname}{key[2]}",
                            "atom": atom["name"],
                            "charge": "-0.5",
                            "coord": [atom["x"], atom["y"], atom["z"]],
                            "dist_to_center": dist([atom["x"], atom["y"], atom["z"]], self.center)
                        })

        charged_groups.sort(key=lambda x: x["dist_to_center"])

        print(f"\nCharged groups in pocket ({len(charged_groups)}):")
        for cg in charged_groups:
            print(f"  {cg['residue']:<10} {cg['atom']:<6} charge={cg['charge']:<6} "
                  f"dist_to_center={cg['dist_to_center']:.2f} Å")

        # Net charge assessment
        pos_count = sum(1 for c in charged_groups if float(c["charge"]) > 0)
        neg_count = sum(1 for c in charged_groups if float(c["charge"]) < 0)
        # Approximate net charge (simplified)
        pos_charge = sum(float(c["charge"]) for c in charged_groups if float(c["charge"]) > 0)
        neg_charge = sum(float(c["charge"]) for c in charged_groups if float(c["charge"]) < 0)

        print(f"\nApproximate electrostatic environment:")
        print(f"  Positive charge groups: {pos_count} (total +{pos_charge:.1f})")
        print(f"  Negative charge groups: {neg_count} (total {neg_charge:.1f})")
        print(f"  Net approximate charge: {pos_charge + neg_charge:+.1f}")

        if pos_charge + neg_charge > 0.5:
            print("  → Pocket is POSITIVELY charged → Ligand should have acidic/negative groups (COO⁻, SO₃⁻)")
        elif pos_charge + neg_charge < -0.5:
            print("  → Pocket is NEGATIVELY charged → Ligand should have basic/positive groups (NH₃⁺, guanidinium)")
        else:
            print("  → Pocket is roughly NEUTRAL → Ligand needs balanced polarity")

        self.results["charged_groups"] = charged_groups
        self.results["net_charge_approx"] = pos_charge + neg_charge

    def _detect_metals_waters(self):
        """Detect metal ions and water molecules."""
        print("\n" + "=" * 70)
        print("6. METAL IONS & WATER MOLECULES")
        print("=" * 70)

        metals = []
        waters = []
        hetatms = []

        for atom in self.atoms:
            if atom["record"] == "HETATM":
                d = dist([atom["x"], atom["y"], atom["z"]], self.center)
                if d <= self.pocket_radius:
                    hetatms.append((atom, d))
                    if atom["resname"] == "HOH":
                        waters.append((atom, d))
                    elif atom["element"] in ("FE", "ZN", "MG", "CA", "MN", "CU", "NA", "K"):
                        metals.append((atom, d))

        if metals:
            print(f"\nMetal ions found ({len(metals)}):")
            for atom, d in metals:
                print(f"  {atom['resname']} {atom['name']} at ({atom['x']:.2f}, {atom['y']:.2f}, {atom['z']:.2f}) "
                      f"— {d:.2f} Å from center")
        else:
            print("\nNo metal ions found in pocket.")

        if waters:
            print(f"\nWater molecules found ({len(waters)}):")
            for atom, d in waters:
                print(f"  HOH at ({atom['x']:.2f}, {atom['y']:.2f}, {atom['z']:.2f}) "
                      f"— {d:.2f} Å from center")
        else:
            print("No water molecules found in pocket.")

        if hetatms:
            print(f"\nAll HETATM records in pocket ({len(hetatms)}):")
            for atom, d in hetatms:
                print(f"  {atom['resname']} {atom['name']} at ({atom['x']:.2f}, {atom['y']:.2f}, {atom['z']:.2f}) "
                      f"— {d:.2f} Å from center")

        self.results["metals"] = [{"resname": a["resname"], "coord": [a["x"], a["y"], a["z"]], "dist": d} for a, d in metals]
        self.results["waters"] = [{"coord": [a["x"], a["y"], a["z"]], "dist": d} for a, d in waters]

    def _analyze_pocket_shape(self):
        """Analyze the shape and size of the binding pocket."""
        print("\n" + "=" * 70)
        print("7. POCKET SHAPE & SIZE ANALYSIS")
        print("=" * 70)

        # Collect all pocket atom coordinates with VDW radii
        pocket_coords = []
        for key, atom_list in self.pocket_residues.items():
            for atom, d in atom_list:
                elem = atom.get("element", "") or atom["name"][0]
                vdw = VDW_RADII.get(elem.upper(), 1.7)
                pocket_coords.append({"coord": [atom["x"], atom["y"], atom["z"]], "vdw": vdw})

        if not pocket_coords:
            print("No pocket atoms found!")
            return

        # Compute bounding box of pocket atoms
        xs = [p["coord"][0] for p in pocket_coords]
        ys = [p["coord"][1] for p in pocket_coords]
        zs = [p["coord"][2] for p in pocket_coords]

        print(f"\nBounding box of pocket atoms:")
        print(f"  X: {min(xs):.2f} to {max(xs):.2f}  (span: {max(xs)-min(xs):.2f} Å)")
        print(f"  Y: {min(ys):.2f} to {max(ys):.2f}  (span: {max(ys)-min(ys):.2f} Å)")
        print(f"  Z: {min(zs):.2f} to {max(zs):.2f}  (span: {max(zs)-min(zs):.2f} Å)")

        # Compute pocket volume estimate (grid-based with VDW shell exclusion)
        # Use a tighter analysis radius for the core cavity
        grid_spacing = 1.0  # Å (coarser grid for speed)
        pocket_volume = 0.0
        cavity_points = []

        # Only check within the docking box (15 Å from center)
        analysis_radius = 15.0

        for ix in range(int(-analysis_radius / grid_spacing), int(analysis_radius / grid_spacing) + 1):
            for iy in range(int(-analysis_radius / grid_spacing), int(analysis_radius / grid_spacing) + 1):
                for iz in range(int(-analysis_radius / grid_spacing), int(analysis_radius / grid_spacing) + 1):
                    px = self.center[0] + ix * grid_spacing
                    py = self.center[1] + iy * grid_spacing
                    pz = self.center[2] + iz * grid_spacing
                    grid_pt = [px, py, pz]

                    # Must be within analysis radius
                    if dist(grid_pt, self.center) > analysis_radius:
                        continue

                    # Check against all pocket atoms with VDW radii
                    is_occupied = False
                    for pa in pocket_coords:
                        d = dist(grid_pt, pa["coord"])
                        if d < pa["vdw"] + 0.5:  # VDW radius + 0.5 Å probe
                            is_occupied = True
                            break

                    # Point must be near at least one atom (within 4 Å of protein surface)
                    # to count as cavity, not bulk solvent
                    near_surface = False
                    for pa in pocket_coords:
                        d = dist(grid_pt, pa["coord"])
                        if d < pa["vdw"] + 4.0:
                            near_surface = True
                            break

                    if not is_occupied and near_surface:
                        pocket_volume += grid_spacing ** 3
                        cavity_points.append(grid_pt)

        # Apply Connolly-like correction factor (grid overestimates)
        pocket_volume_corrected = pocket_volume * 0.7  # empirical correction

        print(f"\nEstimated cavity volume (raw grid): {pocket_volume:.0f} ų")
        print(f"Estimated cavity volume (corrected): {pocket_volume_corrected:.0f} ų")
        print(f"Cavity grid points: {len(cavity_points)}")

        # Analyze cavity shape
        if cavity_points:
            cx = [p[0] for p in cavity_points]
            cy = [p[1] for p in cavity_points]
            cz = [p[2] for p in cavity_points]

            cavity_center = centroid(cavity_points)
            print(f"Cavity centroid: ({cavity_center[0]:.2f}, {cavity_center[1]:.2f}, {cavity_center[2]:.2f})")
            print(f"Cavity extent:")
            print(f"  X: {min(cx):.2f} to {max(cx):.2f}  (span: {max(cx)-min(cx):.2f} Å)")
            print(f"  Y: {min(cy):.2f} to {max(cy):.2f}  (span: {max(cy)-min(cy):.2f} Å)")
            print(f"  Z: {min(cz):.2f} to {max(cz):.2f}  (span: {max(cz)-min(cz):.2f} Å)")

            d_offset = dist(cavity_center, self.center)
            print(f"Offset of cavity center from docking center: {d_offset:.2f} Å")

            # Determine pocket shape classification
            spans = [max(cx)-min(cx), max(cy)-min(cy), max(cz)-min(cz)]
            max_span = max(spans)
            min_span = min(spans)
            aspect = max_span / min_span if min_span > 0 else 999

            if aspect < 1.5:
                shape = "GLOBULAR/SPHERICAL"
            elif aspect < 2.5:
                shape = "ELONGATED/OVAL"
            else:
                shape = "GROOVE/TUNNEL"

            print(f"\nShape aspect ratio: {aspect:.2f} → {shape}")

            # Molecular weight estimate based on corrected cavity volume
            # Rule of thumb: ~18-20 ų per heavy atom for drug-like molecules
            # Ligand typically fills 50-70% of cavity volume
            fill_fraction = 0.6  # typical ligand fills ~60% of pocket
            ligand_volume = pocket_volume_corrected * fill_fraction
            est_heavy_atoms = int(ligand_volume / 19)  # ~19 ų per heavy atom
            est_mw = est_heavy_atoms * 13.0  # average heavy atom weight ~13 Da

            print(f"\nEstimated ligand size (assuming {fill_fraction:.0%} cavity fill):")
            print(f"  Ligand volume: ~{ligand_volume:.0f} ų")
            print(f"  Heavy atoms: ~{est_heavy_atoms}")
            print(f"  Molecular weight: ~{est_mw:.0f} Da")
            print(f"\n  NOTE: For Vina docking with 30Å box, drug-like molecules (MW 200-500 Da)")
            print(f"        with 15-35 heavy atoms are typical. The pocket is large enough")
            print(f"        to accommodate molecules up to ~MW {min(est_mw, 500):.0f} Da.")

        self.results["pocket_shape"] = {
            "volume": pocket_volume_corrected,
            "volume_raw": pocket_volume,
            "shape": shape if cavity_points else "unknown",
            "bounding_box": {
                "x": [min(xs), max(xs)],
                "y": [min(ys), max(ys)],
                "z": [min(zs), max(zs)]
            },
            "estimated_heavy_atoms": est_heavy_atoms if cavity_points else 0,
            "estimated_mw": est_mw if cavity_points else 0,
        }

    def _pharmacophore_analysis(self):
        """Derive pharmacophore features a ligand should have."""
        print("\n" + "=" * 70)
        print("8. PHARMACOPHORE FEATURE ANALYSIS")
        print("=" * 70)

        features = []

        # 1. H-bond features
        key_donors = self.results.get("key_donors", [])
        key_acceptors = self.results.get("key_acceptors", [])

        if key_donors:
            # Protein has donors → ligand needs acceptors
            print("\n◆ H-BOND: Protein has donors → LIGAND NEEDS ACCEPTORS")
            for d in key_donors[:5]:
                print(f"  Protein donor: {d['residue']} {d['atom']} at {d['dist_to_center']:.2f} Å from center")
            features.append({
                "type": "H-bond acceptor",
                "reason": f"Protein has {len(key_donors)} H-bond donors in core pocket",
                "priority": "HIGH" if len(key_donors) >= 3 else "MEDIUM",
                "suggested_groups": ["carbonyl O", "ether O", "pyridine N", "nitro O", "sulfonyl O"]
            })

        if key_acceptors:
            # Protein has acceptors → ligand needs donors
            print("\n◆ H-BOND: Protein has acceptors → LIGAND NEEDS DONORS")
            for a in key_acceptors[:5]:
                print(f"  Protein acceptor: {a['residue']} {a['atom']} at {a['dist_to_center']:.2f} Å from center")
            features.append({
                "type": "H-bond donor",
                "reason": f"Protein has {len(key_acceptors)} H-bond acceptors in core pocket",
                "priority": "HIGH" if len(key_acceptors) >= 3 else "MEDIUM",
                "suggested_groups": ["NH (amine)", "OH (alcohol)", "NH₂ (amine)", "NH (amide)", "NH (imidazole)"]
            })

        # 2. Aromatic features
        aromatic = self.results.get("aromatic_interactions", [])
        if aromatic:
            print(f"\n◆ PI-STACKING: {len(aromatic)} aromatic rings in pocket → LIGAND NEEDS AROMATIC GROUPS")
            for ai in aromatic:
                print(f"  {ai['residue']} ring at {ai['dist_to_center']:.2f} Å from center")
            features.append({
                "type": "Aromatic ring",
                "reason": f"{len(aromatic)} aromatic residues in pocket enable pi-stacking",
                "priority": "HIGH" if any(a["dist_to_center"] < 6.0 for a in aromatic) else "MEDIUM",
                "suggested_groups": ["phenyl", "pyridine", "indole", "benzimidazole", "naphthalene"]
            })

        # 3. Charge features
        charged = self.results.get("charged_groups", [])
        net_charge = self.results.get("net_charge_approx", 0)
        if charged:
            pos_groups = [c for c in charged if float(c["charge"]) > 0]
            neg_groups = [c for c in charged if float(c["charge"]) < 0]
            if pos_groups:
                print(f"\n◆ IONIC: {len(pos_groups)} positive groups → LIGAND NEEDS NEGATIVE/ACIDIC GROUPS")
                features.append({
                    "type": "Negative charge / Acidic group",
                    "reason": f"{len(pos_groups)} positively charged groups (ARG/LYS/HIS)",
                    "priority": "HIGH",
                    "suggested_groups": ["carboxylic acid (COOH→COO⁻)", "sulfonamide", "tetrazole", "phosphonate"]
                })
            if neg_groups:
                print(f"\n◆ IONIC: {len(neg_groups)} negative groups → LIGAND NEEDS POSITIVE/BASIC GROUPS")
                features.append({
                    "type": "Positive charge / Basic group",
                    "reason": f"{len(neg_groups)} negatively charged groups (ASP/GLU)",
                    "priority": "HIGH",
                    "suggested_groups": ["amine (NH₂→NH₃⁺)", "guanidinium", "pyridinium", "imidazolium"]
                })

        # 4. Hydrophobic features
        classification = self.results.get("classification", {})
        hydropathy = classification.get("hydropathy_ratio", 0)
        if hydropathy > 0.4:
            print(f"\n◆ HYDROPHOBIC: Hydropathy ratio = {hydropathy:.1%} → LIGAND NEEDS HYDROPHOBIC GROUPS")
            features.append({
                "type": "Hydrophobic moiety",
                "reason": f"Pocket is {hydropathy:.0%} hydrophobic",
                "priority": "HIGH" if hydropathy > 0.5 else "MEDIUM",
                "suggested_groups": ["alkyl chains", "cycloalkyl", "halogenated aromatics", "tert-butyl", "isopropyl"]
            })

        # 5. Pocket size → ligand size constraint
        shape_info = self.results.get("pocket_shape", {})
        est_heavy = shape_info.get("estimated_heavy_atoms", 0)
        est_mw = shape_info.get("estimated_mw", 0)
        # Cap at drug-like range
        practical_mw = min(est_mw, 500) if est_mw > 0 else 350
        practical_heavy = min(est_heavy, 35) if est_heavy > 0 else 25
        if est_heavy > 0:
            print(f"\n◆ SIZE: Pocket can accommodate ligands up to ~{practical_mw:.0f} Da, ~{practical_heavy} heavy atoms")
            features.append({
                "type": "Size constraint",
                "reason": f"Cavity volume supports up to ~{practical_heavy} heavy atoms",
                "priority": "MEDIUM",
                "suggested_groups": [f"MW 200-{practical_mw:.0f} Da, {10}-{practical_heavy} heavy atoms"]
            })

        print(f"\n{'='*70}")
        print("PHARMACOPHORE SUMMARY")
        print("=" * 70)
        for i, feat in enumerate(features, 1):
            print(f"\n{i}. {feat['type']} [{feat['priority']} PRIORITY]")
            print(f"   Reason: {feat['reason']}")
            print(f"   Suggested: {', '.join(feat['suggested_groups'])}")

        self.results["pharmacophore"] = features

    def _ligand_recommendations(self):
        """Generate specific ligand design recommendations based on all analyses."""
        print("\n" + "=" * 70)
        print("9. LIGAND DESIGN RECOMMENDATIONS")
        print("=" * 70)

        classification = self.results.get("classification", {})
        charged = self.results.get("charged_groups", [])
        aromatic = self.results.get("aromatic_interactions", [])
        key_donors = self.results.get("key_donors", [])
        key_acceptors = self.results.get("key_acceptors", [])
        shape = self.results.get("pocket_shape", {})
        net_q = self.results.get("net_charge_approx", 0)

        print("\n◆ RECOMMENDED SCAFFOLD TYPES:")

        # Determine scaffold based on pocket character
        pos_groups = [c for c in charged if float(c["charge"]) > 0]
        neg_groups = [c for c in charged if float(c["charge"]) < 0]

        scaffolds = []

        # Check for strong ionic interactions
        if pos_groups:
            print("\n  1. CARBOXYLATE-CONTAINING SCAFFOLDS (to interact with ARG/LYS)")
            print("     • Quinazoline-4-carboxylic acid")
            print("     • Indole-2-carboxylic acid")
            print("     • Benzimidazole-5-carboxylic acid")
            print("     • Pyridine-carboxylic acid (picolinic acid derivatives)")
            print("     • Tetrazole-benzene (bioisostere of carboxylic acid)")
            scaffolds.extend([
                "c1ccc2c(c1)ncnc2C(=O)O",          # quinazoline-COOH
                "c1ccc2c(c1)[nH]c2C(=O)O",          # indole-COOH
                "c1ccc2c(c1)nccn2C(=O)O",           # quinoxaline-COOH
                "c1cc(cnc1)C(=O)O",                  # pyridine-COOH
                "c1ccc(cc1)c2nnnn2",                 # phenyl-tetrazole
            ])

        if neg_groups:
            print("\n  2. AMINE-CONTAINING SCAFFOLDS (to interact with ASP/GLU)")
            print("     • Aminobenzimidazole")
            print("     • Aminopyridine / aminopyrimidine")
            print("     • Guanidinium-benzene")
            print("     • Diaminopurine analogs")
            scaffolds.extend([
                "c1ccc2c(c1)nccn2N",               # amino-quinoxaline
                "c1ccc2c(c1)nc(n2)N",               # amino-quinazoline
                "c1cc(cnc1)N",                       # amino-pyridine
                "N=c1nc2ccccc2n1N",                  # guanidino-benzimidazole
            ])

        # Aromatic scaffolds
        if aromatic:
            print("\n  3. AROMATIC/PI-STACKING SCAFFOLDS")
            print("     • Multi-ring fused systems (quinazoline, quinoxaline, indole)")
            print("     • Biphenyl / naphthalene derivatives")
            print("     • Benzothiazole / benzoxazole")
            scaffolds.extend([
                "c1ccc2c(c1)ncnc2",                  # quinazoline
                "c1ccc2c(c1)nccn2",                  # quinoxaline
                "c1ccc2c(c1)scn2",                   # benzothiazole
                "c1ccc2c(c1)ocn2",                   # benzoxazole
                "c1ccc2c(c1)[nH]cn2",                # benzimidazole
                "c1ccc(cc1)c2ccccc2",                # biphenyl
            ])

        # Hydrophobic scaffolds
        hydrophobic_res = classification.get("hydrophobic", [])
        if len(hydrophobic_res) > 3:
            print("\n  4. HYDROPHOBIC SCAFFOLDS")
            print("     • Halogenated aromatics (F, Cl substituents)")
            print("     • Cycloalkyl-aromatic hybrids")
            print("     • tert-butyl / isopropyl substituted rings")
            scaffolds.extend([
                "c1cc(c(cc1F)Cl)c2ccccc2",          # fluoro-chloro biphenyl
                "c1ccc2c(c1)CCCC2",                  # tetralin
                "CC(C)c1ccc(cc1)C(=O)O",            # tBu-benzoic acid
            ])

        # Print specific SMILES recommendations
        print("\n\n◆ TOP RECOMMENDED LIGAND SMILES (for seeding generator):")
        print("-" * 70)
        # Deduplicate
        seen = set()
        unique_scaffolds = []
        for s in scaffolds:
            if s not in seen:
                seen.add(s)
                unique_scaffolds.append(s)

        for i, smi in enumerate(unique_scaffolds[:20], 1):
            print(f"  {i:2d}. {smi}")

        # Key strategic advice
        print("\n\n◆ STRATEGIC INSIGHTS FOR IMPROVING VINA SCORE:")
        print("-" * 70)

        if net_q > 0.5:
            print("""
  ★ CRITICAL: The pocket is POSITIVELY charged.
    → Include carboxylic acid (-COOH) or tetrazole groups in ligands
    → These form strong salt bridges with ARG/LYS residues
    → Carboxylate-guanidinium interaction ≈ -3 to -5 kcal/mol alone!
    → This is likely the #1 missing feature causing poor docking scores""")

        if net_q < -0.5:
            print("""
  ★ CRITICAL: The pocket is NEGATIVELY charged.
    → Include amine (-NH₂) or guanidinium groups in ligands
    → These form strong salt bridges with ASP/GLU residues
    → Ammonium-carboxylate interaction ≈ -3 to -5 kcal/mol alone!
    → This is likely the #1 missing feature causing poor docking scores""")

        if aromatic:
            print(f"""
  ★ IMPORTANT: {len(aromatic)} aromatic rings found in pocket.
    → Ligand MUST have aromatic rings for pi-stacking
    → Pi-stacking contributes ~-1 to -2 kcal/mol per interaction
    → Use planar, multi-ring systems aligned with pocket aromatic rings""")

        if key_donors or key_acceptors:
            print(f"""
  ★ IMPORTANT: {len(key_donors)} H-bond donors and {len(key_acceptors)} H-bond acceptors in core pocket.
    → Each good H-bond ≈ -1 to -3 kcal/mol
    → Ensure ligand geometry matches donor/acceptor positions
    → Directionality matters: O-H···O and N-H···O geometries""")

        # Conformation analysis advice
        print("""
  ★ CONFORMATION ANALYSIS (competition insight):
    → Random SMILES generation produces random 3D conformations
    → Vina optimizes pose but starting conformation matters
    → Use ETKDGv3 for better initial conformer generation
    → Consider multiple conformer docking (ensemble docking)
    → Rigid aromatic cores with flexible linkers improve sampling""")

        self.results["recommended_scaffolds"] = unique_scaffolds

    def get_pocket_summary(self):
        """Return a concise dict summary for programmatic use."""
        return {
            "n_pocket_residues": len(self.pocket_residues),
            "n_inner_residues": len(self.inner_residues),
            "classification": self.results.get("classification", {}),
            "pharmacophore": self.results.get("pharmacophore", []),
            "charged_groups": self.results.get("charged_groups", []),
            "aromatic_interactions": self.results.get("aromatic_interactions", []),
            "key_donors_count": len(self.results.get("key_donors", [])),
            "key_acceptors_count": len(self.results.get("key_acceptors", [])),
            "net_charge": self.results.get("net_charge_approx", 0),
            "pocket_volume": self.results.get("pocket_shape", {}).get("volume", 0),
            "recommended_scaffolds": self.results.get("recommended_scaffolds", []),
        }


# ─── Main ───────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    analyzer = PocketAnalyzer(
        pdb_path=PDB_PATH,
        center=DOCKING_CENTER,
        pocket_radius=POCKET_RADIUS,
        inner_radius=INNER_RADIUS,
    )
    results = analyzer.run_full_analysis()

    # Save summary
    print("\n\n" + "=" * 70)
    print("POCKET SUMMARY (for programmatic use)")
    print("=" * 70)
    import json
    summary = analyzer.get_pocket_summary()
    # Convert non-serializable types
    def make_serializable(obj):
        if isinstance(obj, dict):
            return {k: make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [make_serializable(v) for v in obj]
        elif isinstance(obj, tuple):
            return [make_serializable(v) for v in obj]
        elif isinstance(obj, float):
            return round(obj, 3)
        else:
            return obj

    summary = make_serializable(summary)
    print(json.dumps(summary, indent=2))

    # Save to JSON file
    output_path = os.path.join(PROJECT_ROOT, "output", "pocket_analysis.json")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(summary, f, indent=2)
    print(f"\nAnalysis saved to: {output_path}")
