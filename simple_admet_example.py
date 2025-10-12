#!/usr/bin/env python3
"""
Simple ADMET Prediction Example using dleader_agent

This script demonstrates how to use the dleader_agent library to predict
ADMET (Absorption, Distribution, Metabolism, Excretion, and Toxicity)
properties for chemical compounds.

Example compound: Ibuprofen (CC(C)CC1=CC=C(C=C1)C(C)C(=O)O)
"""

from dleader_agent.tool.pharmacology import predict_admet_properties


def main():
    """Run ADMET prediction for a sample compound."""

    # Example SMILES string for Ibuprofen
    # You can replace this with any valid SMILES string
    compound_smiles = "CC(C)CC1=CC=C(C=C1)C(C)C(=O)O"

    print("=" * 60)
    print("ADMET Prediction Example using dleader_agent")
    print("=" * 60)
    print(f"\nCompound SMILES: {compound_smiles}")
    print("(This is Ibuprofen)")
    print("\nPredicting ADMET properties...\n")

    # Predict ADMET properties
    # You can use either "MPNN" (default) or "Morgan" model type
    result = predict_admet_properties(
        smiles_list=[compound_smiles],
        ADMET_model_type="MPNN"  # Options: "MPNN" or "Morgan"
    )

    # Display results
    print(result)

    print("\n" + "=" * 60)
    print("Prediction complete!")
    print("=" * 60)


if __name__ == "__main__":
    main()