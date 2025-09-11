#!/usr/bin/env python3
"""
Robust Example combining RDKit and xtb-python for molecular modeling workflows
This script demonstrates:
1. Creating molecules with RDKit from SMILES
2. Generating 3D conformers with RDKit
3. Safe usage of xtb-python with proper error handling
4. Avoiding common segfault causes

Common segfault causes and solutions:
- Invalid molecular geometries → Add validation
- Memory issues → Use smaller molecules for testing  
- Threading issues → Sequential execution
- Uninitialized variables → Proper initialization
"""

import numpy as np
import sys
import traceback
from rdkit import Chem
from rdkit.Chem import AllChem
from rdkit.Chem import Draw

# Suppress RDKit warnings to reduce noise
from rdkit import RDLogger
rdlogger = RDLogger.logger()
rdlogger.setLevel(RDLogger.ERROR)

# Try to import xtb-python safely
try:
    from xtb.interface import Calculator, Environment
    from xtb.utils import get_method
    from xtb.libxtb import VERBOSITY_MINIMAL
    XTB_AVAILABLE = True
    print("✓ xtb-python imported successfully")
except ImportError as e:
    print(f"✗ xtb-python not available: {e}")
    XTB_AVAILABLE = False

def validate_geometry(positions, min_distance=0.5):
    """
    Validate molecular geometry to prevent segfaults
    Check for atoms that are too close together
    """
    n_atoms = len(positions)
    if n_atoms < 2:
        return True
    
    # Check all pairwise distances
    for i in range(n_atoms):
        for j in range(i + 1, n_atoms):
            dist = np.linalg.norm(positions[i] - positions[j])
            if dist < min_distance:
                print(f"Warning: Atoms {i} and {j} are too close ({dist:.3f} Å)")
                return False
    return True

def safe_rdkit_to_xtb_format(mol):
    """
    Safely convert RDKit molecule to format compatible with xtb-python
    Returns atomic numbers and positions in Angstroms with validation
    """
    try:
        conf = mol.GetConformer()
        positions = []
        numbers = []
        
        for atom in mol.GetAtoms():
            numbers.append(atom.GetAtomicNum())
            pos = conf.GetAtomPosition(atom.GetIdx())
            positions.append([pos.x, pos.y, pos.z])
        
        numbers = np.array(numbers, dtype=int)
        positions = np.array(positions, dtype=float)
        
        # Validate geometry
        if not validate_geometry(positions):
            print("Geometry validation failed - this could cause segfaults")
            return None, None
            
        # Check for reasonable coordinates (not NaN or too large)
        if np.any(np.isnan(positions)) or np.any(np.abs(positions) > 1000):
            print("Invalid coordinates detected")
            return None, None
            
        print(f"Molecule has {len(numbers)} atoms")
        print(f"Coordinate range: {np.min(positions):.2f} to {np.max(positions):.2f} Å")
        
        return numbers, positions
        
    except Exception as e:
        print(f"Error in rdkit_to_xtb_format: {e}")
        return None, None

def xtb_to_rdkit_format(mol, positions):
    """
    Update RDKit molecule with optimized positions from xtb
    """
    conf = mol.GetConformer()
    for i, pos in enumerate(positions):
        conf.SetAtomPosition(i, pos)
    return mol

def safe_xtb_calculation(mol, method="GFN2-xTB", charge=0, verbose=False):
    """
    Safely perform xtb calculation with comprehensive error handling
    
    Args:
        mol: RDKit molecule object
        method: xTB method ("GFN2-xTB", "GFN1-xTB", or "GFN0-xTB")  
        charge: Molecular charge
        verbose: Print calculation details
    
    Returns:
        success (bool), energy (float or None), error_message (str)
    """
    if not XTB_AVAILABLE:
        return False, None, "xtb-python not available"
    
    try:
        # Convert RDKit molecule to xtb format with validation
        numbers, positions = safe_rdkit_to_xtb_format(mol)
        
        if numbers is None or positions is None:
            return False, None, "Invalid molecular geometry"
        
        # Check molecule size (avoid very large systems that could cause segfaults)
        if len(numbers) > 500:  # Conservative limit
            return False, None, f"Molecule too large ({len(numbers)} atoms). Limit is 500 atoms."
        
        print(f"Attempting {method} calculation on {len(numbers)} atoms...")
        
        # Create calculator with proper initialization
        calc = None
        try:
            # Get method safely
            xtb_method = get_method(method)
            print(f"Using method: {method}")
            
            # Create calculator - this is where segfaults often occur
            calc = Calculator(xtb_method, numbers, positions, charge=float(charge))
            print("Calculator created successfully")
            
            # Set verbosity
            if not verbose:
                calc.set_verbosity(VERBOSITY_MINIMAL)
            
            # Perform single point calculation
            print("Running single point calculation...")
            results = calc.singlepoint()
            
            # Get energy safely
            energy = results.get_energy()
            print(f"Calculation completed. Energy: {energy:.6f} Hartree")
            
            return True, energy, "Success"
            
        except Exception as calc_error:
            error_msg = f"Calculator error: {str(calc_error)}"
            print(error_msg)
            traceback.print_exc()
            return False, None, error_msg
            
        finally:
            # Cleanup calculator if it exists
            if calc is not None:
                try:
                    del calc
                except:
                    pass
    
    except Exception as e:
        error_msg = f"Unexpected error in xtb calculation: {str(e)}"
        print(error_msg)
        traceback.print_exc()
        return False, None, error_msg

def create_safe_molecule_from_smiles(smiles, add_hs=True, embed_3d=True):
    """
    Safely create and prepare a molecule from SMILES
    """
    try:
        print(f"Creating molecule from SMILES: {smiles}")
        
        # Create molecule
        mol = Chem.MolFromSmiles(smiles)
        if mol is None:
            print(f"Failed to create molecule from SMILES: {smiles}")
            return None
        
        # Add hydrogens if requested
        if add_hs:
            mol = Chem.AddHs(mol)
            print(f"Added hydrogens. Total atoms: {mol.GetNumAtoms()}")
        
        # Generate 3D coordinates if requested
        if embed_3d:
            # Try multiple random seeds if first attempt fails
            for seed in [42, 123, 456, 789]:
                result = AllChem.EmbedMolecule(mol, randomSeed=seed)
                if result == 0:  # Success
                    print(f"3D embedding successful with seed {seed}")
                    
                    # Basic MMFF optimization to clean up geometry
                    try:
                        mmff_result = AllChem.MMFFOptimizeMolecule(mol, maxIters=200)
                        if mmff_result == 0:
                            print("MMFF optimization converged")
                        else:
                            print(f"MMFF optimization did not converge (code: {mmff_result})")
                    except Exception as mmff_error:
                        print(f"MMFF optimization failed: {mmff_error}")
                    
                    break
            else:
                print("All 3D embedding attempts failed")
                return None
        
        return mol
        
    except Exception as e:
        print(f"Error creating molecule: {e}")
        return None

def test_simple_molecules():
    """
    Test xtb-python with simple, well-behaved molecules
    """
    print("Testing Simple Molecules with XTB")
    print("=" * 45)
    
    # Start with very simple molecules
    simple_molecules = [
        ("H2", "H-H"),           # Simplest molecule
        ("H2O", "O"),            # Water  
        ("NH3", "N"),            # Ammonia
        ("CH4", "C"),            # Methane
        ("C2H6", "CC"),          # Ethane
    ]
    
    results = []
    
    for name, smiles in simple_molecules:
        print(f"\n--- Testing {name} ({smiles}) ---")
        
        try:
            # Create molecule safely
            mol = create_safe_molecule_from_smiles(smiles)
            if mol is None:
                print(f"Skipping {name} - molecule creation failed")
                continue
            
            # Test XTB calculation
            success, energy, error_msg = safe_xtb_calculation(mol, verbose=True)
            
            if success:
                print(f"✓ {name}: {energy:.6f} Hartree ({energy * 627.509:.2f} kcal/mol)")
                results.append((name, energy, True))
            else:
                print(f"✗ {name}: {error_msg}")
                results.append((name, None, False))
                
        except Exception as e:
            print(f"✗ {name}: Unexpected error - {e}")
            results.append((name, None, False))
    
    # Summary
    print(f"\n{'='*45}")
    print("SUMMARY:")
    successful = sum(1 for _, _, success in results if success)
    print(f"Successful calculations: {successful}/{len(results)}")
    
    for name, energy, success in results:
        if success:
            print(f"✓ {name}: {energy:.6f} Hartree")
        else:
            print(f"✗ {name}: Failed")
    
    return results

def safe_installation_check():
    """
    Check if xtb-python is properly installed and working
    """
    print("XTB-Python Installation Check")
    print("=" * 35)
    
    if not XTB_AVAILABLE:
        print("✗ xtb-python is not installed")
        print("\nTo install xtb-python:")
        print("conda install -c conda-forge xtb-python")
        return False
    
    try:
        # Test basic imports
        from xtb.interface import Calculator, Environment
        from xtb.utils import get_method
        print("✓ Core modules imported successfully")
        
        # Test method access
        method = get_method("GFN2-xTB")
        print("✓ GFN2-xTB method accessible")
        
        # Test very simple calculation (H2)
        numbers = np.array([1, 1])
        positions = np.array([[0.0, 0.0, 0.0], [0.0, 0.0, 0.74]])
        
        print("Testing minimal H2 calculation...")
        calc = Calculator(method, numbers, positions)
        calc.set_verbosity(VERBOSITY_MINIMAL)
        
        results = calc.singlepoint()
        energy = results.get_energy()
        
        print(f"✓ Basic calculation successful: {energy:.6f} Hartree")
        print("✓ xtb-python is working correctly")
        
        return True
        
    except Exception as e:
        print(f"✗ Installation check failed: {e}")
        traceback.print_exc()
        return False

def troubleshooting_guide():
    """
    Provide troubleshooting information for common issues
    """
    print("\nTROUBLESHOOTING GUIDE")
    print("=" * 50)
    print("Common segfault causes and solutions:")
    print()
    print("1. INSTALLATION ISSUES:")
    print("   - Use conda-forge: conda install -c conda-forge xtb-python")
    print("   - Check Python version compatibility")
    print("   - Verify shared libraries are available")
    print()
    print("2. MOLECULAR GEOMETRY ISSUES:")
    print("   - Atoms too close together (< 0.5 Å)")
    print("   - Invalid coordinates (NaN, infinity)")
    print("   - Very large molecules (> 500 atoms)")
    print()
    print("3. MEMORY ISSUES:")
    print("   - Reduce molecule size")
    print("   - Check available RAM")
    print("   - Close other applications")
    print()
    print("4. KNOWN LIMITATIONS:")
    print("   - Some methods don't work with PBC")  
    print("   - Threading issues with multiple calculators")
    print("   - Certain molecular charges may be problematic")
    print()
    print("5. DEBUGGING STEPS:")
    print("   - Start with simple molecules (H2, H2O)")
    print("   - Use verbose=True for detailed output")
    print("   - Check geometry with validate_geometry()")
    print("   - Try different xtb methods (GFN0, GFN1, GFN2)")

if __name__ == "__main__":
    print("RDKit + xtb-python: Robust Integration Example")
    print("=" * 55)
    
    # Step 1: Check installation
    if not safe_installation_check():
        troubleshooting_guide()
        sys.exit(1)
    
    # Step 2: Test with simple molecules
    print(f"\n{'='*55}")
    results = test_simple_molecules()
    
    # Step 3: Show troubleshooting if any failures
    if any(not success for _, _, success in results):
        troubleshooting_guide()
    else:
        print(f"\n{'='*55}")
        print("All tests passed! xtb-python is working correctly.")
        print("\nYou can now safely use xtb-python for larger molecules:")
        print("- Organic molecules up to ~100 atoms")
        print("- Small proteins/peptides") 
        print("- Drug-like molecules")
        print("- Always validate geometry before calculation")
        
    print(f"\n{'='*55}")
    print("Tips to avoid segfaults:")
    print("• Always use safe_xtb_calculation() function")
    print("• Validate molecular geometries") 
    print("• Start with small test molecules")
    print("• Use proper error handling")
    print("• Check coordinates for NaN/infinity values")