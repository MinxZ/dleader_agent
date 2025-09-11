| **Component Requiring Commercial License** | **Type**         | **Original Location in Codebase**                                    | **Permissive Alternative**                               |
|-------------------------------------------|------------------|-----------------------------------------------------------------------|-----------------------------------------------------------|
| KEGG API                                  | API / Database   | `dleader_agent/tool/database.py: query_kegg`                                | Reactome API (CC-BY 4.0)                                 |
| HOMER                                     | CLI Tool         | `dleader_agent/tool/genomics.py: find_enriched_motifs_with_homer`           | BioPython motifs + JASPAR API (Permissive)               |

| OMIM                                      | Data Source      | `dleader_agent/env_desc.py: data_lake_dict (omim.parquet)`                  | ClinVar API and Monarch Initiative API (Public Domain)   |
| DDInter 2.0                               | Data Source      | `dleader_agent/env_desc.py: data_lake_dict (all ddinter_... files)`         | OpenFDA Adverse Event API (Public Domain)                |
| Human Protein Atlas                       | Data Source      | `dleader_agent/env_desc.py: data_lake_dict (proteinatlas.tsv)`              | Ensembl API or UniProt API (Permissive)                  |
| Guide to PHARMACOLOGY (GtoPdb)            | API / Database   | `dleader_agent/tool/database.py: query_gtopdb`                              | ChEMBL API (Permissive)                                  |
