#!/bin/bash
# Added by dleader_agent setup
# Remove any old paths first to avoid duplicates
PATH=$(echo $PATH | tr ':' '\n' | grep -v "dleader_agent_tools/bin" | tr '\n' ':' | sed 's/:$//')
export PATH="/home/ubuntu/dleader_agent/dleader_agent_env/dleader_agent_tools/bin:$PATH"
