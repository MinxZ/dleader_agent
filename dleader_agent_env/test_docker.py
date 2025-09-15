import os
work_dir = "/home/ubuntu/dleader_agent/chat_sessions/session_20250912_194843_0b7b0376"
pdb_file_path = "/home/ubuntu/dleader_agent/dleader_agent/tool/data/pdb/1E66.pdb"
local_pdb_path = os.path.join(work_dir, "1E66.pdb")

imidacloprid_smiles = "C1=CN=C(N1)N=C(N)NC2=CC=C(C=C2)Cl"

from dleader_agent.tool.pharmacology import run_autosite

# AutoSite用の出力ディレクトリを作成
autosite_output_dir = os.path.join(work_dir, "autosite_results")
os.makedirs(autosite_output_dir, exist_ok=True)

# AutoSiteを実行
autosite_result = run_autosite(
    pdb_file=local_pdb_path,
    output_dir=autosite_output_dir,
    spacing=1.0
)

from dleader_agent.tool.pharmacology import docking_autodock_vina

# ドッキングパラメータ
smiles_list = [imidacloprid_smiles]
box_center = [8.0, 67.0, 65.0]  # 活性部位の中心座標
box_size = [20.0, 20.0, 20.0]   # ドッキングボックスのサイズ

# AutoDock Vinaでドッキングを実行
docking_result = docking_autodock_vina(
    smiles_list=smiles_list,
    receptor_pdb_file=local_pdb_path,
    box_center=box_center,
    box_size=box_size,
    ncpu=2
)

from dleader_agent.tool.pharmacology import run_diffdock_with_smiles

print("DiffDockを使用してドッキングを実行中...")

# DiffDock用の出力ディレクトリを作成
diffdock_output_dir = f"{work_dir}/diffdock_results"
os.makedirs(diffdock_output_dir, exist_ok=True)

# DiffDockでドッキング実行
diffdock_result = run_diffdock_with_smiles(
    pdb_path=local_pdb_path,
    smiles_string=imidacloprid_smiles,
    local_output_dir=diffdock_output_dir,
    use_gpu=False  # CPUモードで実行
)

print("ドッキング結果:")
print(docking_result)