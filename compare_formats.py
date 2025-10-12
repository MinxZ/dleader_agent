#!/usr/bin/env python3
"""
Compare file sizes between JPG and PNG formats
"""
import matplotlib.pyplot as plt
import numpy as np
import os

def create_sample_plot():
    """Create a sample molecular-style plot"""
    fig, ax = plt.subplots(figsize=(10, 8))

    # Create some sample data that resembles molecular analysis
    molecules = ['Methane', 'Ethane', 'Propane', 'Butane', 'Pentane']
    molecular_weights = [16.04, 30.07, 44.10, 58.12, 72.15]
    logp_values = [1.09, 1.81, 2.36, 2.89, 3.39]

    # Create scatter plot
    scatter = ax.scatter(molecular_weights, logp_values,
                        s=200, alpha=0.7,
                        c=range(len(molecules)), cmap='viridis')

    # Add labels
    for i, mol in enumerate(molecules):
        ax.annotate(mol, (molecular_weights[i], logp_values[i]),
                   xytext=(5, 5), textcoords='offset points',
                   fontsize=12, fontweight='bold')

    ax.set_xlabel('Molecular Weight (g/mol)', fontsize=14)
    ax.set_ylabel('LogP Value', fontsize=14)
    ax.set_title('Molecular Properties Analysis\n(Sample plot for format comparison)',
                fontsize=16, fontweight='bold', pad=20)

    # Add grid
    ax.grid(True, alpha=0.3)

    # Add colorbar
    cbar = plt.colorbar(scatter)
    cbar.set_label('Molecule Index', fontsize=12)

    return fig

def main():
    print("="*60)
    print(" FILE FORMAT SIZE COMPARISON")
    print("="*60)

    # Create the plot
    print("\n📊 Creating sample molecular plot...")
    fig = create_sample_plot()

    # Save in different formats
    formats = [
        ('PNG (no compression)', 'test_plot.png', {'format': 'png', 'dpi': 300, 'bbox_inches': 'tight'}),
        ('JPG (matplotlib)', 'test_plot.jpg', {'format': 'jpeg', 'dpi': 300, 'bbox_inches': 'tight'}),
        ('SVG (vector)', 'test_plot.svg', {'format': 'svg', 'bbox_inches': 'tight'}),
    ]

    print("\n💾 Saving in different formats...")
    results = []

    for name, filename, kwargs in formats:
        fig.savefig(filename, **kwargs)
        if os.path.exists(filename):
            size = os.path.getsize(filename)
            results.append((name, filename, size))
            print(f"   ✅ {name}: {size/1024:.1f} KB")
        else:
            print(f"   ❌ Failed to create {filename}")

    plt.close(fig)

    # Analysis
    print("\n📈 Size Comparison:")
    if results:
        png_size = next((size for name, _, size in results if 'PNG' in name), 0)

        print(f"\n{'Format':<20} {'Size (KB)':<12} {'vs PNG':<12} {'Space Saved'}")
        print("-" * 58)

        for name, filename, size in results:
            size_kb = size / 1024
            if png_size > 0:
                ratio = size / png_size
                saved = (1 - ratio) * 100 if ratio < 1 else 0
                vs_png = f"{ratio:.2f}x"
                saved_str = f"{saved:.1f}%" if saved > 0 else "larger"
            else:
                vs_png = "N/A"
                saved_str = "N/A"

            print(f"{name:<20} {size_kb:<12.1f} {vs_png:<12} {saved_str}")

    print("\n🎯 Recommendation:")
    jpg_size = next((size for name, _, size in results if 'JPG' in name), 0)
    if png_size > 0 and jpg_size > 0:
        savings = (1 - jpg_size/png_size) * 100
        print(f"   Use JPG format for {savings:.1f}% space savings")
        print(f"   Updated prompt now defaults to JPG format for plots")

    svg_size = next((size for name, _, size in results if 'SVG' in name), 0)
    if svg_size > 0:
        print(f"   SVG is best for vector graphics that need to scale")
        print(f"   SVG size: {svg_size/1024:.1f} KB (resolution independent)")

    # Cleanup
    print(f"\n🧹 Cleaning up test files...")
    for _, filename, _ in results:
        if os.path.exists(filename):
            os.remove(filename)
            print(f"   Removed {filename}")

    print(f"\n✅ Format comparison complete!")

if __name__ == "__main__":
    main()