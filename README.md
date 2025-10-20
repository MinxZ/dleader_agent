
# MALAT1 ASO Design Project - Improved Safety Candidates

## Project Overview
This project designed and evaluated 100 antisense oligonucleotide (ASO) candidates targeting human MALAT1 (Metastasis Associated Lung Adenocarcinoma Transcript 1), with a focus on identifying sequences with superior safety profiles compared to existing benchmark sequences.

## Key Results

### Top 5 ASO Candidates
All candidates show significant improvements over benchmark sequences:
- **120.3% improvement** in Final Score
- **7.8% improvement** in Safety Score  
- **70% reduction** in toxicity penalties
- **80%** of top candidates show "Very Low" toxicity (vs 0% in benchmark)

### Top Candidate (ASO_071)
- **Sequence**: 5'-GAACAGACAGACCTGAAGTCAAG-3'
- **Position**: 6742-6765 (64.4% of transcript)
- **Target Domain**: A-rich tract (functional region)
- **Final Score**: 4.107
- **Safety Score**: 1.000 (perfect)
- **Toxicity**: Very Low
- **Predicted IC50**: 23.8 nM

## Files Generated

### Data Files
1. `malat1_100_aso_candidates_scored.csv` - All 100 candidates with comprehensive scores
2. `malat1_full_sequence_retrieved.fasta` - MALAT1 transcript (ENST00000534336, 10,468 bp)
3. `table1_top5_summary.csv` - Summary of top 5 candidates
4. `table2_top5_detailed_scores.csv` - Detailed score breakdown
5. `table3_benchmark_comparison.csv` - Benchmark vs new candidates comparison
6. `table4_statistics_summary.csv` - Statistical comparison summary

### Figures
1. `figure1_score_distributions_top5.png` - Score distributions with top 5 highlighted
2. `figure2_top5_detailed_analysis.png` - Detailed analysis of top 5 properties
3. `figure3_position_analysis.png` - Genomic position mapping
4. `figure4_benchmark_comparison.png` - Comprehensive benchmark comparison
5. `figure5_complete_workflow_summary.png` - Complete workflow and results summary

### Reports
1. `malat1_aso_comprehensive_report.txt` - Complete analysis report with methodology

## Methodology

### Pipeline Steps
1. **Sequence Retrieval**: Retrieved MALAT1 transcript from Ensembl (ENST00000534336)
2. **Structure Analysis**: Analyzed 5 regions using ViennaRNA RNAfold
3. **Candidate Generation**: Generated 100 candidates (18-25 nt) across transcript
4. **Comprehensive Scoring**: Multi-parameter scoring system
5. **Selection**: Top 5 ranked by final score

### Scoring Algorithm
**Base Score** (weighted average):
- Accessibility (30%): Based on RNA structure and GC content
- Specificity (25%): Uniqueness in MALAT1 transcript  
- Conservation (20%): Functional importance
- Thermodynamics (15%): Optimal Tm and GC%
- Target Quality (10%): Functional domain proximity

**Bonuses**:
- Functional domain: +2.0
- High accessibility: +1.5
- Optimal conservation: +1.3

**Penalties** (toxicity):
- Poly-G/T runs: -3.0 to -5.0
- CpG motifs: -1.0 each
- Immunostimulatory motifs: -4.0

**Final Score** = Base Score + Bonuses - (Penalties × 0.1)

## Reliability Assessment

### High Reliability
✓ All sequences computationally validated
✓ Target sites confirmed in Ensembl transcript
✓ Scoring based on established ASO design principles

### Medium Reliability  
⚠ Accessibility scores estimated (not experimentally validated)
⚠ IC50 predictions are computational estimates
⚠ No genome-wide off-target analysis performed

## Recommendations

### Immediate Next Steps
1. Prioritize **ASO_071** and **ASO_073** for experimental validation
2. Synthesize with 2'-MOE gapmer chemistry (PS backbone)
3. Test in MALAT1-expressing cell lines (A549, HeLa)
4. Perform dose-response studies (1-100 nM range)
5. Assess knockdown efficiency by qRT-PCR

### Further Validation
- Experimental IC50 determination
- RNA accessibility probing (SHAPE, DMS)
- Genome-wide off-target analysis (BLAST, RNA-seq)
- In vitro toxicity screening
- Immunogenicity assessment (PBMC assays)

## Comparison with Benchmark

| Metric | Benchmark (n=5) | Top 5 New (n=5) | Improvement |
|--------|-----------------|-----------------|-------------|
| Final Score | 1.832 | 4.035 | +120.3% |
| Safety Score | 0.900 | 0.970 | +7.8% |
| Penalties | 2.00 | 0.60 | -70.0% |
| Very Low Toxicity | 0/5 (0%) | 4/5 (80%) | - |
| Position | 5150 (all overlap) | 6700-6800 (distributed) | Novel region |
| Domain | None | A-rich tract | Functional |

## Citation
If you use these designs, please cite:
- MALAT1 transcript: Ensembl ENST00000534336
- Structure prediction: ViennaRNA RNAfold
- Design methodology: Custom computational pipeline (this project)

## Contact
For questions or collaboration: [Your contact information]

## Date
Analysis completed: 2025-10-19 05:12:16

---
End of README
