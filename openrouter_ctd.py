"""
Simple text-based agent using OpenRouter with Qwen model
"""

import os
import time

from dleader_agent.agent.a1 import A1


def create_openrouter_text_agent():
    """Create an agent configured for text-based Q&A using OpenRouter."""

    # Initialize agent with OpenRouter Qwen model
    agent = A1(
        use_tool_retriever=True,
        download_data_lake=False,
        # llm='qwen/qwen3-vl-235b-a22b-thinking',
        llm='qwen/qwen3-max',
        source='OpenRouter',  # Specify OpenRouter as the source
        api_key=os.getenv("OPENROUTER_API_KEY", "")
    )



    # Clear default data lake
    agent.data_lake_dict = {}

    # Keep literature tools for scientific text analysis
    text_modules = {
        'dleader_agent.tool.support_tools': agent.module2api.get('dleader_agent.tool.support_tools', []),
        'dleader_agent.tool.literature': agent.module2api.get('dleader_agent.tool.literature', [])
    }
    agent.module2api = text_modules

    print("✅ Configured OpenRouter text agent with Qwen model")
    return agent


if __name__ == "__main__":
    print("🧬 OpenRouter Text Agent with Qwen Model")
    print("="*60)

    # Make sure API key is set
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key:
        print("⚠️  OPENROUTER_API_KEY not found in environment variables")
        print("Please set it with:")
        print("  export OPENROUTER_API_KEY='your-openrouter-api-key'")
        print("\nYou can get an API key from: https://openrouter.ai/keys")
        exit(1)

    print(f"✅ API Key found (length: {len(api_key)} chars)")
    print()

    # Example usage with the Qwen model via OpenRouter
    question = "introduce rna"

    # You can change the question to anything you want
    # question = "what is DNA?"
    # question = "explain protein synthesis"
    # question = "describe CRISPR technology"

    agent = create_openrouter_text_agent()
    for file_path in ['/home/ubuntu/dleader_agent_ctd/pdf/D04127.pdf']:
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
