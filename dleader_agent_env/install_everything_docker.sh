git clone -b image_agent --single-branch https://github.com/MinxZ/dleader_agent.git

install conda 
wget https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
Yes

bash setup.sh

paste .env


conda install -c conda-forge pdbfixer openbabel openmm -y
# Install pip packages
pip install colorama configargparse h5py numpy "ray[default]>=2.0" rdkit pandas scikit-learn scipy tqdm
pip install pyscreener

# Alternative: Install from bioconda
conda install -c bioconda mgltools -y 
conda install -c bioconda autodock-vina -y

echo 'alias python=python3' >> ~/.bashrc
echo 'alias pip=pip3' >> ~/.bashrc

find /home -name "*prepare_receptor*" 2>/dev/null
find /usr -name "*prepare_receptor*" 2>/dev/null
find $CONDA_PREFIX -name "*prepare_receptor*" 2>/dev/null

# If found, create a symlink
# Example: if found at /path/to/prepare_receptor4.py
sudo ln -s /path/to/prepare_receptor4.py /usr/local/bin/prepare_receptor
which prepare_receptor || which prepare_receptor4.py

# If prepare_receptor4.py exists but not prepare_receptor, create wrapper
if command -v prepare_receptor4.py &> /dev/null && ! command -v prepare_receptor &> /dev/null; then
    ln -s $(which prepare_receptor4.py) $CONDA_PREFIX/bin/prepare_receptor
    echo "Created prepare_receptor wrapper"
fi

conda remove pillow libtiff libjpeg-turbo --force -y
# Clear conda cache
conda clean --all -y
# Reinstall from conda-forge (more reliable)
conda install -c conda-forge pillow libtiff libjpeg-turbo -y
# Test if it works
python -c "import PIL; print('PIL works')"

python agent_interface_jp.py
