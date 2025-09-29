"""
Example: Minimal Agent Configuration for Image Analysis Only

This example shows how to configure the dleader_agent agent to use only 
image analysis tools without default data lake and packages.
"""

import time

from dleader_agent.agent.a1 import A1


def create_minimal_image_agent():
    """Create an agent configured only for image analysis tasks."""
    
    # Initialize agent without downloading default data lake
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False, 
        llm='claude-sonnet-4-20250514'
    )
    
    # Clear default data lake to avoid distractions
    agent.data_lake_dict = {}
    
    # Keep only essential packages for image processing
    # essential_packages = {
    #     'requests': 'HTTP library for downloading images from URLs',
    #     'base64': 'Encoding/decoding binary data',
    #     'PIL': 'Python Imaging Library for image processing',
    #     'cv2': 'OpenCV for computer vision tasks',
    #     'PyPDF2': 'Python PDF library for eading pdf'
    # }
    # agent.library_content_dict = essential_packages
    
    # Filter module2api to keep only support tools (contains image function)
    image_modules = {
        'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', []),
        'dleader_agent.tool.literature': agent.module2api.get('dleader_agent.tool.literature', [])
    }
    agent.module2api = image_modules
    
    print("✅ Configured minimal agent with:")
    # print(f"   📦 {len(essential_packages)} essential packages")
    # print(f"   🔧 {len(image_modules.get('dleader_agent.tool.support_tools', []))} support tools (including image analysis)")
    # print(f"   📊 {len(agent.data_lake_dict)} data lake items (empty)")
    
    return agent

def example_url_image_analysis():
    """Example using image URL analysis with different modes."""
    
    print("🚀 URL Image Analysis Example")
    print("="*50)
    
    # Create minimal agent
    agent = create_minimal_image_agent()
    
#     for i in range(1, 2):
#         file_path = f'extracted_examples/example_{i}.txt'
#         log, result = agent.go(f"""summarize the {file_path} if there are image url in it, use image analysis tools to transform the url into text first. You can find the crossponding url of image in /home/ubuntu/work/dleader_agent/data/dleader_agent_data/patent_raw/US20220340900A1_images.json.
# For each Modification types(Name, identity, Modification types classification (backbone, sugar, terminal, and conjugates or others))
# We need sequence(identity, and extact AUCG or ATCG sequence from image or text before <---> after pairwise) and <---> Collect all related information about the sequence and Modification types <----> summarize Effect (Properties data)  with original text. 
# for example, we have Toxicity, Binding affinity, Enzyme stability, Delivery, Reduce immune stimulation, Aqueous solubility, you need to think about the property related to them, for example, stability is tm shift, …
# """)
    # for i in range(1, 2):
    # for file_path in ['pdf/300297000_22400AMX01387000_K101_1.pdf', 'pdf/400256000_22800AMX00681_F100_1.pdf']:
    for file_path in ['/home/ubuntu/work/dleader_agent/pdf/300297000_22400AMX01387000_K101_1.pdf']:
        log, result = agent.go(f"""I would like to extract information on whether a drug is a substrate of transporters or not, and whether it inhibits transporters, from the summary of drug review documents (extracts of CTD)
Can you also include the number data, and the original text of evidence(japanese) and description and source with url, the file path is {file_path}. 
focus on these and use the threashold guideline P-gp or BCRP IC50,u

0.1 × (Dose/250 mL) (i.e.,
(Dose/250 mL)/ IC50,u < 10) for orally administered drugs
OATP1B1 or OATP1B3 OAT1, OAT3, OCT2 MATE1/MATE2-K IC50,u > 10 × Cmax, inlet,u

(i.e., Cmax,inlet,u / IC50,u < 0.1)
IC50,u > 10 × Cmax,u (i.e., Cmax,u/ IC50,u < 0.1)
IC50,u > 50 × Cmax,u (i.e., Cmax,u/ IC50,u < 0.02)
Cmax,u is unbound maximal plasma concentration of an inhibitor at steady state after therapeutic dose.

The Ki,u of an inhibitor approaches IC50,u when substrate concentration is much less than Km assuming
competitive inhibition (8).
Cmax,inlet,u is estimated unbound maximum plasma concentration of an inhibitor at liver inlet.
Cmax,inlet,u=fu,p x (Cmax + (Fa×Fg×ka×Dose)/Qh/RB) (36). If unknown, Fa= 1, Fg = 1 and k= 0.1/min can
be used as a worst-case estimate. The fu,p should be set to 1% if the reliability of fu,p measurements <1%
cannot be demonstrated (also refer to Section 2.1.2.1). 
Some of the term is in japanese, like P-gp is represented as hMDR1 or ヒトP糖たん白. You need to first to think about the japanese term or see in the pdf. 
List any transporters not mentioned, because the drug may be a non-substrate of these transporters. write in both japanese and english version table. and write clearly is a substrate of transporters or not, and whether it inhibits transporters in the table, if not mentioned, say not mentioned
If the experimental numerical data is not mentioned or not tested, also say not mentioned. always say not mentioned instead of not test
Next to substrate(yes/no) add three additional columns alongside the Yes/No column. Label them IC50, Km/or.., Numerical Value, and Unit. also do it for transporters(yes/no), 
write in 日本語 for the description and original text and summarize in table
separate substrate and transporters into 2 csv {file_path.replace('.pdf', '_substrate.csv')}, {file_path.replace('.pdf', '_transporters.csv')}
""")
    
        print("📋 Agent Response:")
        print(log, result)
        time.sleep(60)
        with open(file_path.replace('.pdf', '_log.txt'), 'w') as f:
            f.write(str(log))
        with open(file_path.replace('.pdf', '_result.txt'), 'w') as f:
            f.write(str(result))
        
    return log, result

if __name__ == "__main__":
    print("🧬 Minimal dleader_agent Agent - Image Analysis Only")
    print("="*60)
    example_url_image_analysis()